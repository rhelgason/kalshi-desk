import "server-only";
import { createHash, createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import { cache } from "react";
import { home, type Book } from "./db";

/**
 * Logins (2026-11-09): one per person, remembered for as long as browsers allow (400 days, renewed on every
 * visit by middleware.ts), so nobody has to log in again unless they log out or clear the browser. People
 * sign in with a passkey (lib/passkeys.ts): Face ID or Touch ID, a fingerprint, Windows Hello, or their phone.
 *
 * The owner can also still use the manager password (lib/admin.ts). A friend sees only their own office.
 * Tables: deploy/friends.sql (public schema; RLS on with no policies, like the bot's).
 */
export const SESSION_COOKIE = "desk_session";
export const SESSION_DAYS = 400; // the most Chrome keeps a cookie; Safari keeps server-set ones as long

export type User = {
  id: number; name: string; role: "owner" | "friend"; office: string | null;
  prefs: Record<string, unknown>; share_overview: boolean;
};

const hash = (token: string) => createHash("sha256").update(token).digest("hex");

/** Whoever this browser is logged in as (null: nobody, or the manager by password only). */
export const currentUser = cache(async (): Promise<User | null> => {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token || token.length > 100) return null;
  try {
    const rows = await home()`
      SELECT u.id, u.name, u.role, u.office, u.prefs, u.share_overview, s.last_seen
      FROM public.sessions s JOIN public.users u ON u.id = s.user_id WHERE s.token_hash = ${hash(token)}`;
    if (!rows.length) return null;
    const r = rows[0];
    if (Date.now() - new Date(r.last_seen).getTime() > 86_400_000) {
      await home()`UPDATE public.sessions SET last_seen = now() WHERE token_hash = ${hash(token)}`;
    }
    return { id: Number(r.id), name: r.name, role: r.role, office: r.office, prefs: r.prefs ?? {},
             share_overview: !!r.share_overview };
  } catch {
    return null; // no tables yet, or the database is busy: show the page as for a visitor
  }
});

/** A friend's own book (their office's schema). */
export const officeOf = (u: User | null): Book | null => (u?.office ? (`office_${u.office}` as Book) : null);

export async function startSession(userId: number, agent: string | null): Promise<void> {
  const token = randomBytes(32).toString("base64url");
  await home()`INSERT INTO public.sessions (token_hash, user_id, agent) VALUES (${hash(token)}, ${userId}, ${agent?.slice(0, 200) ?? null})`;
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: SESSION_DAYS * 86_400,
  });
}

export async function endSession(): Promise<void> {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (token) await home()`DELETE FROM public.sessions WHERE token_hash = ${hash(token)}`.catch(() => null);
  jar.delete(SESSION_COOKIE);
}

// Short-lived signed values in cookies (a passkey challenge, a sign-up in progress): no table needed
function secret(): string {
  const s = process.env.SESSION_SECRET || process.env.ADMIN_PASSWORD;
  if (!s) throw new Error("SESSION_SECRET (or ADMIN_PASSWORD) must be set");
  return createHmac("sha256", s).update("kalshi-desk-signed-v1").digest("hex");
}

export async function setSigned(name: string, value: string, seconds: number): Promise<void> {
  const body = `${Date.now() + seconds * 1000}.${Buffer.from(value).toString("base64url")}`;
  const sig = createHmac("sha256", secret()).update(`${name}:${body}`).digest("base64url");
  (await cookies()).set(name, `${body}.${sig}`, { httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: seconds });
}

export async function takeSigned(name: string, keep = false): Promise<string | null> {
  const jar = await cookies();
  const raw = jar.get(name)?.value;
  if (!keep) jar.delete(name);
  if (!raw) return null;
  const [until, value, sig] = raw.split(".");
  if (!until || !value || !sig) return null;
  const want = createHmac("sha256", secret()).update(`${name}:${until}.${value}`).digest("base64url");
  if (want.length !== sig.length || !timingSafeEqual(Buffer.from(want), Buffer.from(sig))) return null;
  if (Date.now() > Number(until)) return null;
  return Buffer.from(value, "base64url").toString();
}

export const inviteHash = hash;
