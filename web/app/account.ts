"use server";

import type { AuthenticationResponseJSON, RegistrationResponseJSON } from "@simplewebauthn/server";
import { randomBytes } from "node:crypto";
import { revalidatePath, revalidateTag } from "next/cache";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { isAdmin, logout } from "@/lib/admin";
import { BOOK_COOKIE, getOffice, viewedBook } from "@/lib/book";
import { bookTag, db, home, isOffice, type Book } from "@/lib/db";
import { checkLogin, loginOptions, registrationOptions, saveRegistration } from "@/lib/passkeys";
import { currentUser, endSession, inviteHash, officeOf, setSigned, startSession, takeSigned } from "@/lib/session";
import { MODE_COOKIE, MODE_PREF, THEME_COOKIE, THEME_PREF, parseMode, parseTheme } from "@/lib/theme";
import { kalshiBalance, lockKey, tidyPem } from "@/lib/vault";

// Logins, joining, friends' offices (lib/session.ts). Every action returns { error } for the page to show
// rather than throwing, so a friend sees a plain sentence, not an error screen.

type Result<T = object> = ({ ok: true } & T) | { ok: false; error: string };
const fail = (e: unknown): { ok: false; error: string } => ({ ok: false, error: e instanceof Error ? e.message : String(e) });
const JOIN = "desk_join";
const agent = async () => (await headers()).get("user-agent");

/** A device name for the passkey list ("iPhone", "Windows"), from the browser's own description. */
function device(ua: string | null): string | null {
  if (!ua) return null;
  for (const [re, name] of [[/iPhone/, "iPhone"], [/iPad/, "iPad"], [/Android/, "Android"], [/Macintosh/, "Mac"],
                            [/Windows/, "Windows"], [/CrOS/, "Chromebook"], [/Linux/, "Linux"]] as const) {
    if (re.test(ua)) return name;
  }
  return null;
}

async function remember(userId: number) {
  await startSession(userId, await agent());
  // Their look and colours follow them to a new device
  const rows = await home()`SELECT prefs FROM public.users WHERE id = ${userId}`;
  const prefs = rows[0]?.prefs ?? {}, jar = await cookies(), year = { path: "/", maxAge: 365 * 86_400, sameSite: "lax" as const };
  if (prefs[THEME_PREF]) jar.set(THEME_COOKIE, parseTheme(prefs[THEME_PREF]), year);
  if (prefs[MODE_PREF]) jar.set(MODE_COOKIE, parseMode(prefs[MODE_PREF]), year);
}

// ---- signing in --------------------------------------------------------------------------------------------

export async function loginStart() {
  try {
    return { ok: true as const, options: await loginOptions() };
  } catch (e) {
    return fail(e);
  }
}

export async function loginFinish(response: AuthenticationResponseJSON): Promise<Result> {
  try {
    await remember(await checkLogin(response));
    revalidatePath("/", "layout");
    return { ok: true };
  } catch (e) {
    return fail(e);
  }
}

export async function signOut() {
  await endSession();
  await logout();
  (await cookies()).delete(BOOK_COOKIE);
  redirect("/");
}

/** Add a passkey on this device: for someone logged in, or the manager (by password) making their owner login. */
export async function passkeyStart(name?: string) {
  try {
    let user = await currentUser();
    if (!user) {
      if (!(await isAdmin())) throw new Error("Log in first");
      const rows = await home()`SELECT id, name FROM public.users WHERE role = 'owner' ORDER BY id LIMIT 1`;
      const owner = rows[0] ?? (await home()`INSERT INTO public.users (name, role) VALUES (${(name || "Manager").slice(0, 40)}, 'owner')
        RETURNING id, name`)[0];
      user = { id: Number(owner.id), name: owner.name, role: "owner", office: null, prefs: {}, share_overview: false };
    }
    await setSigned(JOIN, JSON.stringify({ u: user.id }), 600);
    return { ok: true as const, options: await registrationOptions(user) };
  } catch (e) {
    return fail(e);
  }
}

export async function passkeyFinish(response: RegistrationResponseJSON): Promise<Result> {
  try {
    const want = await takeSigned(JOIN);
    if (!want) throw new Error("That took too long: please try again.");
    const { u } = JSON.parse(want);
    await saveRegistration(u, response, device(await agent()));
    if (!(await currentUser())) await remember(u);
    revalidatePath("/", "layout");
    return { ok: true };
  } catch (e) {
    return fail(e);
  }
}

// ---- joining (an invite link from the owner: /join/<token>) ------------------------------------------------

export type Invite = { name: string; userId: number | null; hasKey: boolean; expired: boolean; used: boolean };

export async function readInvite(token: string): Promise<Invite | null> {
  const rows = await home()`
    SELECT i.name, i.user_id, i.expires_at, i.used_at, o.key_box IS NOT NULL AS has_key
    FROM public.invites i LEFT JOIN public.users u ON u.id = i.user_id LEFT JOIN public.offices o ON o.slug = u.office
    WHERE i.token_hash = ${inviteHash(token)}`.catch(() => []);
  if (!rows.length) return null;
  const r = rows[0];
  return { name: r.name, userId: r.user_id ? Number(r.user_id) : null, hasKey: !!r.has_key,
           expired: new Date(r.expires_at).getTime() < Date.now(), used: !!r.used_at };
}

/** An office name from a person's name: lowercase letters and digits ("Sam O'Neil" -> "samoneil"), never taken. */
async function freeSlug(name: string): Promise<string> {
  let base = name.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]/g, "").replace(/^[0-9]+/, "").slice(0, 20);
  if (base.length < 2) base = "friend";
  const taken = new Set((await home()`SELECT office FROM public.users WHERE office LIKE ${base + "%"}`).map((r) => r.office));
  for (let i = 1; ; i++) {
    const slug = i === 1 ? base : `${base}${i}`;
    if (!taken.has(slug)) return slug;
  }
}

export async function joinStart(token: string, agreed: boolean): Promise<Result<{ options: unknown }>> {
  try {
    const inv = await readInvite(token);
    if (!inv || inv.expired) throw new Error("This invite link has expired. Ask for a new one.");
    if (inv.used) throw new Error("This invite link has been used already. Ask for a new one.");
    if (!agreed) throw new Error("Tick the box to say you've read what this is.");
    let userId = inv.userId;
    if (!userId) {
      const slug = await freeSlug(inv.name);
      userId = Number((await home()`INSERT INTO public.users (name, role, office, share_overview)
        VALUES (${inv.name}, 'friend', ${slug}, true) RETURNING id`)[0].id);
      await home()`INSERT INTO public.offices (slug, user_id, name) VALUES (${slug}, ${userId}, ${inv.name})
        ON CONFLICT (slug) DO NOTHING`;
      await home()`UPDATE public.invites SET user_id = ${userId} WHERE token_hash = ${inviteHash(token)}`;
    }
    await setSigned(JOIN, JSON.stringify({ u: userId, t: inviteHash(token) }), 600);
    return { ok: true, options: await registrationOptions({ id: userId, name: inv.name }) };
  } catch (e) {
    return fail(e);
  }
}

export async function joinPasskey(response: RegistrationResponseJSON): Promise<Result> {
  try {
    const want = await takeSigned(JOIN);
    if (!want) throw new Error("That took too long: please start again.");
    const { u, t } = JSON.parse(want);
    await saveRegistration(u, response, device(await agent()));
    await remember(u);
    await home()`UPDATE public.invites SET used_at = now() WHERE token_hash = ${t}`;
    return { ok: true };
  } catch (e) {
    return fail(e);
  }
}

/** The friend's Kalshi API key: checked with Kalshi, then locked so only the server can use it. */
export async function connectKalshi(keyId: string, pemText: string): Promise<Result<{ balance: number }>> {
  try {
    const user = await currentUser();
    if (!user?.office) throw new Error("Log in first");
    const id = keyId.trim();
    if (!/^[0-9a-f-]{20,64}$/i.test(id)) throw new Error("The Key ID looks like a long code of letters, numbers and dashes.");
    const pem = tidyPem(pemText);
    const balance = await kalshiBalance(id, pem);
    await home()`UPDATE public.offices SET key_id = ${id}, key_box = ${lockKey(pem)}, note = NULL, updated_at = now(),
      status = CASE WHEN status = 'setup' THEN 'ready' ELSE status END WHERE slug = ${user.office}`;
    return { ok: true, balance };
  } catch (e) {
    return fail(e);
  }
}

// ---- preferences, offices ----------------------------------------------------------------------------------

/** Remember someone's choices (the look, for now) with their login, so every device of theirs gets them. */
export async function savePrefs(prefs: Record<string, string>) {
  const user = await currentUser();
  if (!user) return;
  await home()`UPDATE public.users SET prefs = prefs || ${JSON.stringify(prefs)}::jsonb WHERE id = ${user.id}`;
}

export async function createInvite(name: string, forUser?: number): Promise<Result<{ link: string }>> {
  try {
    if (!(await isAdmin())) throw new Error("Manager login required");
    const who = name.trim().slice(0, 40);
    if (!who) throw new Error("Whose invite is it? Type their first name.");
    const token = randomBytes(18).toString("base64url");
    await home()`INSERT INTO public.invites (token_hash, name, user_id, expires_at)
      VALUES (${inviteHash(token)}, ${who}, ${forUser ?? null}, now() + interval '7 days')`;
    const h = await headers();
    const host = h.get("x-forwarded-host") ?? h.get("host");
    return { ok: true, link: `https://${host}/join/${token}` };
  } catch (e) {
    return fail(e);
  }
}

/** The owner opens a friend's office (read-only for the owner; only offices whose friend agreed). */
export async function viewOffice(book: Book | null) {
  if (!(await isAdmin())) return;
  const jar = await cookies();
  if (book && isOffice(book) && (await getOffice(book))) {
    // An hour: the app opens on the owner's own office (11-16)
    jar.set(BOOK_COOKIE, book, { path: "/", maxAge: 3600, sameSite: "lax", httpOnly: true, secure: true });
  } else {
    jar.delete(BOOK_COOKIE);
  }
  revalidatePath("/", "layout");
  redirect("/");
}

/** A friend's own pause button (the owner can press it too, from their office page). */
export async function setOfficePaused(paused: boolean): Promise<Result> {
  try {
    const user = await currentUser();
    const book = await viewedBook();
    const mine = officeOf(user) === book;
    if (!isOffice(book) || !(mine || (await isAdmin()))) throw new Error("Not your office");
    const by = mine ? user!.name : "the owner";
    const at = new Date().toISOString();
    const data = paused ? { halted: true, reason: `paused by ${by}`, by, at, long: true } : { halted: false, resumed_by: by, at };
    await db(book)`INSERT INTO settings (key, updated_at, data) VALUES ('trading', ${at}, ${JSON.stringify(data)})
      ON CONFLICT (key) DO UPDATE SET updated_at = excluded.updated_at, data = excluded.data`;
    if (!paused) await db(book)`UPDATE status SET data = '{}', updated_at = ${at} WHERE key = '_live_books'`;
    await db(book)`INSERT INTO events (ts, strategy, kind, detail)
      VALUES (${at}, ${null}, 'trading', ${JSON.stringify({ action: paused ? "halted" : "resumed", reason: paused ? `paused by ${by}` : null, by })})`;
    revalidateTag(bookTag(book));
    revalidatePath("/");
    return { ok: true };
  } catch (e) {
    return fail(e);
  }
}
