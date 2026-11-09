"use server";

import { revalidatePath, revalidateTag } from "next/cache";
import { redirect } from "next/navigation";
import { login, logout, requireAdmin } from "@/lib/admin";
import { cookies } from "next/headers";
import { BOOK_COOKIE, viewedBook, type Book } from "@/lib/book";
import { bookTag, db, getLive, getPolicy } from "@/lib/db";
import { LEVELS, levelTitle } from "@/lib/hr";
import type { Policy } from "@/lib/types";

// Every action here changes how the desk runs. The bot reads these tables at
// the start of each run (every ~2 minutes), so changes apply almost immediately.
// Each acts on the book being viewed (Real or Pretend tab); the kill switch is always the real book's.

const now = () => new Date().toISOString();

async function event(book: Book, kind: string, strategy: string | null, detail: Record<string, unknown>) {
  await db(book)`INSERT INTO events (ts, strategy, kind, detail)
    VALUES (${now()}, ${strategy}, ${kind}, ${JSON.stringify({ ...detail, by: "admin" })})`;
}

async function ensureEmployee(book: Book, key: string) {
  await db(book)`INSERT INTO employees (key, updated_at) VALUES (${key}, ${now()}) ON CONFLICT (key) DO NOTHING`;
}

function done(paths: string[] = ["/"]) {
  // Drop the dashboard's kept copies (lib/db.ts sturdy()) so the change shows straight away
  for (const b of ["real", "pretend", "shared"] as const) revalidateTag(bookTag(b));
  for (const p of paths) revalidatePath(p);
}

export async function loginAction(_: unknown, form: FormData) {
  if (!(await login(String(form.get("password") ?? "")))) return { error: "Wrong password" };
  redirect(String(form.get("next") || "/"));
}

export async function logoutAction() {
  await logout();
  redirect("/");
}

export async function suspendEmployee(key: string, days: number | null, reason: string) {
  await requireAdmin();
  const book = await viewedBook();
  await ensureEmployee(book, key);
  const until = days ? new Date(Date.now() + days * 86_400_000).toISOString() : "9999-12-31T00:00:00+00:00";
  await db(book)`UPDATE employees SET status = 'suspended', suspended_until = ${until}, updated_at = ${now()} WHERE key = ${key}`;
  await event(book, "hr", key, { action: "suspended", until: days ? until : "indefinitely", why: reason || "manager's call" });
  done(["/", `/employee/${key}`]);
}

export async function reinstateEmployee(key: string) {
  await requireAdmin();
  const book = await viewedBook();
  await db(book)`UPDATE employees SET status = 'active', suspended_until = NULL, strikes = 0, updated_at = ${now()} WHERE key = ${key}`;
  await event(book, "hr", key, { action: "reinstated" });
  done(["/", `/employee/${key}`]);
}

export async function fireEmployee(key: string, reason: string) {
  await requireAdmin();
  const book = await viewedBook();
  await ensureEmployee(book, key);
  await db(book)`UPDATE employees SET status = 'fired', suspended_until = NULL, updated_at = ${now()} WHERE key = ${key}`;
  await event(book, "hr", key, { action: "fired", why: reason || "manager's call" });
  done(["/", `/employee/${key}`]);
}

export async function rehireEmployee(key: string) {
  await requireAdmin();
  const book = await viewedBook();
  await db(book)`UPDATE employees SET status = 'active', suspended_until = NULL, strikes = 0, level = 0,
    updated_at = ${now()} WHERE key = ${key}`;
  await event(book, "hr", key, { action: "rehired", to: "Intern" });
  done(["/", `/employee/${key}`]);
}

export async function setLevel(key: string, level: number) {
  await requireAdmin();
  const book = await viewedBook();
  const clamped = Math.max(0, Math.min(level, LEVELS.length - 1));
  const rows = await db(book)`SELECT level FROM employees WHERE key = ${key}`;
  const before = rows[0]?.level ?? 1;
  await db(book)`UPDATE employees SET level = ${clamped}, updated_at = ${now()} WHERE key = ${key}`;
  await event(book, "hr", key, { action: clamped > before ? "promoted" : "demoted", to: levelTitle(clamped) });
  done(["/", `/employee/${key}`]);
}

export async function setAutotune(key: string, on: boolean) {
  await requireAdmin();
  const book = await viewedBook();
  await db(book)`UPDATE employees SET autotune = ${on ? 1 : 0}, updated_at = ${now()} WHERE key = ${key}`;
  await event(book, "admin", key, { action: on ? "autotune on" : "autotune off" });
  done([`/employee/${key}`]);
}

export async function saveSettings(key: string, changes: Record<string, unknown>, reset: boolean) {
  await requireAdmin();
  const book = await viewedBook();
  const rows = await db(book)`SELECT params FROM employees WHERE key = ${key}`;
  const current = rows.length ? JSON.parse(rows[0].params || "{}") : {};
  const next = reset ? {} : { ...current, ...changes };
  await db(book)`UPDATE employees SET params = ${JSON.stringify(next)}, updated_at = ${now()} WHERE key = ${key}`;
  await event(book, "admin", key, reset ? { action: "settings reset to defaults" } : { action: "settings changed", changes });
  done([`/employee/${key}`]);
}

export async function setNote(key: string, note: string) {
  await requireAdmin();
  const book = await viewedBook();
  await db(book)`UPDATE employees SET note = ${note.slice(0, 500) || null}, updated_at = ${now()} WHERE key = ${key}`;
  done([`/employee/${key}`]);
}

export async function grantBonus(key: string, amount: number, reason: string) {
  await requireAdmin();
  const book = await viewedBook();
  const policy = await getPolicy(book);
  if (!Number.isFinite(amount) || amount === 0) return { error: "Enter an amount" };
  if (amount > policy.reserve) return { error: `The reserve only has $${policy.reserve.toFixed(2)}` };
  policy.reserve -= amount;
  await db(book)`INSERT INTO transfers (ts, season, strategy, amount, reason)
    VALUES (${now()}, ${policy.season}, ${key}, ${amount}, ${reason || "manager's bonus"})`;
  await writePolicy(book, policy);
  await event(book, "hr", key, { action: amount > 0 ? "bonus" : "budget cut", amount, why: reason });
  done(["/", `/employee/${key}`, "/settings"]);
}

/**
 * Put a Training employee on real money mid-season, no new season (desk/hr.py hire): the bot adds them and
 * their markets on its next run, as an Intern with $0 of the pool, betting from the shared pool.
 */
export async function hireOnReal(key: string) {
  await requireAdmin();
  const [policy, live] = await Promise.all([getPolicy("real"), getLive("real")]);
  if (!live) return { error: "No real book" };
  if (live.employees.some((x) => x.key === key) || policy.hired?.includes(key)) return { error: "Already on real money" };
  // A coin specialist needs the real book's price feed to fetch their coin (desk.real.yaml crypto_symbols)
  const coin = key.startsWith("maker_") ? key.slice(6) : null;
  if (coin && !live.employees.some((x) => x.key === `maker_${coin}`))
    return { error: `The real book doesn't fetch ${coin.toUpperCase()} prices yet: ask Claude to add it first` };
  policy.hired = [...(policy.hired ?? []), key];
  await writePolicy("real", policy);
  await db("real")`INSERT INTO employees (key, level, status, updated_at) VALUES (${key}, 0, 'active', ${now()})
    ON CONFLICT (key) DO UPDATE SET level = 0, status = 'active', suspended_until = NULL, strikes = 0,
      updated_at = excluded.updated_at`;
  await event("real", "hr", key, { action: "hired", level: "Intern", why: "moved from Training" });
  done(["/", `/employee/${key}`]);
}

async function writePolicy(book: Book, policy: Policy) {
  await db(book)`INSERT INTO settings (key, updated_at, data) VALUES ('desk', ${now()}, ${JSON.stringify(policy)})
    ON CONFLICT (key) DO UPDATE SET updated_at = excluded.updated_at, data = excluded.data`;
}

export async function updatePolicy(changes: Partial<Omit<Policy, "pool">> & { autotune?: Partial<Policy["autotune"]>; pool?: Partial<Policy["pool"]> }) {
  await requireAdmin();
  const book = await viewedBook();
  const policy = await getPolicy(book);
  const { autotune, pool, ...rest } = changes;
  Object.assign(policy, rest);
  if (autotune) Object.assign(policy.autotune, autotune);
  if (pool) Object.assign(policy.pool, pool);
  await writePolicy(book, policy);
  await event(book, "admin", null, { action: "desk rules changed", changes });
  done(["/settings", "/"]);
}

export async function requestRetune() {
  await requireAdmin();
  const book = await viewedBook();
  const policy = await getPolicy(book);
  policy.autotune.requested_at = now();
  await writePolicy(book, policy);
  await event(book, "admin", null, { action: "retune requested" });
  done(["/settings"]);
}

export async function startNewSeason(reserve: number) {
  await requireAdmin();
  const book = await viewedBook();
  const policy = await getPolicy(book);
  policy.season += 1;
  policy.last_review = now();
  policy.reserve = Number.isFinite(reserve) && reserve >= 0 ? reserve : policy.reserve;
  await writePolicy(book, policy);
  await event(book, "season", null, { action: "new season", season: policy.season });
  done(["/", "/settings"]);
}

/** The real-money kill switch: no new orders, waiting ones cancelled on the bot's next run. */
export async function haltTrading(reason: string, long = false) {
  await requireAdmin();
  const book: Book = "real";
  const data = { halted: true, reason: reason || "stopped from the website", by: "website", at: now(), ...(long && { long: true }) };
  await db(book)`INSERT INTO settings (key, updated_at, data) VALUES ('trading', ${now()}, ${JSON.stringify(data)})
    ON CONFLICT (key) DO UPDATE SET updated_at = excluded.updated_at, data = excluded.data`;
  await event(book, "trading", null, { action: "halted", reason: data.reason, long });
  done(["/settings", "/"]);
}

/** Allow real trading again; the bot re-checks its books against Kalshi from scratch. */
export async function resumeTrading() {
  await requireAdmin();
  const book: Book = "real";
  const data = { halted: false, resumed_by: "website", at: now() };
  await db(book)`INSERT INTO settings (key, updated_at, data) VALUES ('trading', ${now()}, ${JSON.stringify(data)})
    ON CONFLICT (key) DO UPDATE SET updated_at = excluded.updated_at, data = excluded.data`;
  await db(book)`UPDATE status SET data = '{}', updated_at = ${now()} WHERE key = '_live_books'`;
  await event(book, "trading", null, { action: "resumed" });
  done(["/settings", "/"]);
}

/** The Real / Pretend tabs: remember which book this visitor is looking at. */
export async function pickBook(book: Book) {
  (await cookies()).set(BOOK_COOKIE, book === "real" ? "real" : "pretend",
    { path: "/", maxAge: 365 * 86_400, sameSite: "lax", httpOnly: true, secure: true });
  revalidatePath("/", "layout");
}

