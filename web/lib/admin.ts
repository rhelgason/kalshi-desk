import "server-only";
import { createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import { currentUser } from "./session";

// The dashboard is public; changing anything requires the manager: the admin password (ADMIN_PASSWORD in
// Vercel, a signed cookie remembers it for 30 days) or the owner's passkey login (lib/session.ts, 400 days).
const COOKIE = "desk_admin";

function token(): string | null {
  const pw = process.env.ADMIN_PASSWORD;
  if (!pw) return null;
  return createHmac("sha256", pw).update("kalshi-desk-admin-v1").digest("hex");
}

async function passwordCookie(): Promise<boolean> {
  const expected = token();
  if (!expected) return false;
  const got = (await cookies()).get(COOKIE)?.value ?? "";
  if (got.length !== expected.length) return false;
  return timingSafeEqual(Buffer.from(got), Buffer.from(expected));
}

export async function isAdmin(): Promise<boolean> {
  return (await passwordCookie()) || (await currentUser())?.role === "owner";
}

export async function requireAdmin(): Promise<void> {
  if (!(await isAdmin())) throw new Error("Admin login required");
}

export async function login(password: string): Promise<boolean> {
  const pw = process.env.ADMIN_PASSWORD;
  if (!pw || password.length !== pw.length || !timingSafeEqual(Buffer.from(password), Buffer.from(pw))) return false;
  (await cookies()).set(COOKIE, token()!, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  return true;
}

export async function logout(): Promise<void> {
  (await cookies()).delete(COOKIE);
}
