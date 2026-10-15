"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { login, logout, requireAdmin } from "@/lib/admin";
import { db, getPolicy } from "@/lib/db";
import { LEVELS, levelTitle } from "@/lib/hr";
import type { Policy } from "@/lib/types";

// Every action here changes how the desk runs. The bot reads these tables at
// the start of each run (every ~2 minutes), so changes apply almost immediately.

const now = () => new Date().toISOString();

async function event(kind: string, strategy: string | null, detail: Record<string, unknown>) {
  await db()`INSERT INTO events (ts, strategy, kind, detail)
    VALUES (${now()}, ${strategy}, ${kind}, ${JSON.stringify({ ...detail, by: "admin" })})`;
}

async function ensureEmployee(key: string) {
  await db()`INSERT INTO employees (key, updated_at) VALUES (${key}, ${now()}) ON CONFLICT (key) DO NOTHING`;
}

function done(paths: string[] = ["/"]) {
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
  await ensureEmployee(key);
  const until = days ? new Date(Date.now() + days * 86_400_000).toISOString() : "9999-12-31T00:00:00+00:00";
  await db()`UPDATE employees SET status = 'suspended', suspended_until = ${until}, updated_at = ${now()} WHERE key = ${key}`;
  await event("hr", key, { action: "suspended", until: days ? until : "indefinitely", why: reason || "manager's call" });
  done(["/", `/employee/${key}`]);
}

export async function reinstateEmployee(key: string) {
  await requireAdmin();
  await db()`UPDATE employees SET status = 'active', suspended_until = NULL, strikes = 0, updated_at = ${now()} WHERE key = ${key}`;
  await event("hr", key, { action: "reinstated" });
  done(["/", `/employee/${key}`]);
}

export async function fireEmployee(key: string, reason: string) {
  await requireAdmin();
  await ensureEmployee(key);
  await db()`UPDATE employees SET status = 'fired', suspended_until = NULL, updated_at = ${now()} WHERE key = ${key}`;
  await event("hr", key, { action: "fired", why: reason || "manager's call" });
  done(["/", `/employee/${key}`]);
}

export async function rehireEmployee(key: string) {
  await requireAdmin();
  await db()`UPDATE employees SET status = 'active', suspended_until = NULL, strikes = 0, level = 0,
    updated_at = ${now()} WHERE key = ${key}`;
  await event("hr", key, { action: "rehired", to: "Intern" });
  done(["/", `/employee/${key}`]);
}

export async function setLevel(key: string, level: number) {
  await requireAdmin();
  const clamped = Math.max(0, Math.min(level, LEVELS.length - 1));
  const rows = await db()`SELECT level FROM employees WHERE key = ${key}`;
  const before = rows[0]?.level ?? 1;
  await db()`UPDATE employees SET level = ${clamped}, updated_at = ${now()} WHERE key = ${key}`;
  await event("hr", key, { action: clamped > before ? "promoted" : "demoted", to: levelTitle(clamped) });
  done(["/", `/employee/${key}`]);
}

export async function setAutotune(key: string, on: boolean) {
  await requireAdmin();
  await db()`UPDATE employees SET autotune = ${on ? 1 : 0}, updated_at = ${now()} WHERE key = ${key}`;
  await event("admin", key, { action: on ? "autotune on" : "autotune off" });
  done([`/employee/${key}`]);
}

export async function saveSettings(key: string, changes: Record<string, unknown>, reset: boolean) {
  await requireAdmin();
  const rows = await db()`SELECT params FROM employees WHERE key = ${key}`;
  const current = rows.length ? JSON.parse(rows[0].params || "{}") : {};
  const next = reset ? {} : { ...current, ...changes };
  await db()`UPDATE employees SET params = ${JSON.stringify(next)}, updated_at = ${now()} WHERE key = ${key}`;
  await event("admin", key, reset ? { action: "settings reset to defaults" } : { action: "settings changed", changes });
  done([`/employee/${key}`]);
}

export async function setNote(key: string, note: string) {
  await requireAdmin();
  await db()`UPDATE employees SET note = ${note.slice(0, 500) || null}, updated_at = ${now()} WHERE key = ${key}`;
  done([`/employee/${key}`]);
}

export async function grantBonus(key: string, amount: number, reason: string) {
  await requireAdmin();
  const policy = await getPolicy();
  if (!Number.isFinite(amount) || amount === 0) return { error: "Enter an amount" };
  if (amount > policy.reserve) return { error: `The reserve only has $${policy.reserve.toFixed(2)}` };
  policy.reserve -= amount;
  await db()`INSERT INTO transfers (ts, season, strategy, amount, reason)
    VALUES (${now()}, ${policy.season}, ${key}, ${amount}, ${reason || "manager's bonus"})`;
  await writePolicy(policy);
  await event("hr", key, { action: amount > 0 ? "bonus" : "budget cut", amount, why: reason });
  done(["/", `/employee/${key}`, "/settings"]);
}

async function writePolicy(policy: Policy) {
  await db()`INSERT INTO settings (key, updated_at, data) VALUES ('desk', ${now()}, ${JSON.stringify(policy)})
    ON CONFLICT (key) DO UPDATE SET updated_at = excluded.updated_at, data = excluded.data`;
}

export async function updatePolicy(changes: Partial<Omit<Policy, "pool">> & { autotune?: Partial<Policy["autotune"]>; pool?: Partial<Policy["pool"]> }) {
  await requireAdmin();
  const policy = await getPolicy();
  const { autotune, pool, ...rest } = changes;
  Object.assign(policy, rest);
  if (autotune) Object.assign(policy.autotune, autotune);
  if (pool) Object.assign(policy.pool, pool);
  await writePolicy(policy);
  await event("admin", null, { action: "desk rules changed", changes });
  done(["/settings", "/"]);
}

export async function requestRetune() {
  await requireAdmin();
  const policy = await getPolicy();
  policy.autotune.requested_at = now();
  await writePolicy(policy);
  await event("admin", null, { action: "retune requested" });
  done(["/settings"]);
}

export async function startNewSeason(reserve: number) {
  await requireAdmin();
  const policy = await getPolicy();
  policy.season += 1;
  policy.last_review = now();
  policy.reserve = Number.isFinite(reserve) && reserve >= 0 ? reserve : policy.reserve;
  await writePolicy(policy);
  await event("season", null, { action: "new season", season: policy.season });
  done(["/", "/settings"]);
}

/** The real-money kill switch: no new orders, waiting ones cancelled on the bot's next run. */
export async function haltTrading(reason: string) {
  await requireAdmin();
  const data = { halted: true, reason: reason || "stopped from the website", by: "website", at: now() };
  await db()`INSERT INTO settings (key, updated_at, data) VALUES ('trading', ${now()}, ${JSON.stringify(data)})
    ON CONFLICT (key) DO UPDATE SET updated_at = excluded.updated_at, data = excluded.data`;
  await event("trading", null, { action: "halted", reason: data.reason });
  done(["/settings", "/"]);
}

/** Allow real trading again; the bot re-checks its books against Kalshi from scratch. */
export async function resumeTrading() {
  await requireAdmin();
  const data = { halted: false, resumed_by: "website", at: now() };
  await db()`INSERT INTO settings (key, updated_at, data) VALUES ('trading', ${now()}, ${JSON.stringify(data)})
    ON CONFLICT (key) DO UPDATE SET updated_at = excluded.updated_at, data = excluded.data`;
  await db()`UPDATE status SET data = '{}', updated_at = ${now()} WHERE key = '_live_books'`;
  await event("trading", null, { action: "resumed" });
  done(["/settings", "/"]);
}
