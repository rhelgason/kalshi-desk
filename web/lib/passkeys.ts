import "server-only";
import {
  generateAuthenticationOptions, generateRegistrationOptions, verifyAuthenticationResponse, verifyRegistrationResponse,
  type AuthenticationResponseJSON, type RegistrationResponseJSON,
} from "@simplewebauthn/server";
import { headers } from "next/headers";
import { home } from "./db";
import { setSigned, takeSigned } from "./session";

/**
 * Passkeys: the phone's or laptop's own lock (Face ID, Touch ID, a fingerprint, Windows Hello, a PIN) instead
 * of a password. They sync through iCloud Keychain, Google Password Manager or 1Password, and a computer without
 * one can sign in with a nearby phone (the browser shows a QR code). Nothing secret is stored here: only each
 * passkey's public half.
 */
const CHALLENGE = "desk_challenge";
const RP_NAME = "Kalshi Desk";

/** This site's name for passkeys (its domain) and origin, from the request. */
async function site(): Promise<{ rpID: string; origin: string }> {
  const h = await headers();
  const host = (h.get("x-forwarded-host") ?? h.get("host") ?? "localhost").split(",")[0].trim();
  const rpID = host.replace(/:\d+$/, "");
  const proto = h.get("x-forwarded-proto") ?? (rpID === "localhost" ? "http" : "https");
  return { rpID, origin: `${proto}://${host}` };
}

export async function registrationOptions(user: { id: number; name: string }) {
  const { rpID } = await site();
  const existing = await home()`SELECT id, transports FROM public.passkeys WHERE user_id = ${user.id}`;
  const options = await generateRegistrationOptions({
    rpName: RP_NAME, rpID, userName: user.name, userDisplayName: user.name,
    userID: new TextEncoder().encode(`desk-user-${user.id}`),
    attestationType: "none",
    // A passkey the browser keeps (so signing in needs no username), checked with the device's own lock
    authenticatorSelection: { residentKey: "required", userVerification: "preferred" },
    excludeCredentials: existing.map((p) => ({ id: p.id, transports: p.transports ? JSON.parse(p.transports) : undefined })),
  });
  await setSigned(CHALLENGE, JSON.stringify({ c: options.challenge, u: user.id }), 300);
  return options;
}

export async function saveRegistration(userId: number, response: RegistrationResponseJSON, device: string | null) {
  const saved = await takeSigned(CHALLENGE);
  const want = saved ? JSON.parse(saved) : null;
  if (!want || want.u !== userId) throw new Error("That took too long: please try again.");
  const { rpID, origin } = await site();
  const v = await verifyRegistrationResponse({ response, expectedChallenge: want.c, expectedOrigin: origin, expectedRPID: rpID,
                                               requireUserVerification: false });
  if (!v.verified) throw new Error("The passkey couldn't be checked: please try again.");
  const c = v.registrationInfo.credential;
  await home()`INSERT INTO public.passkeys (id, user_id, public_key, counter, transports, device)
    VALUES (${c.id}, ${userId}, ${Buffer.from(c.publicKey).toString("base64url")}, ${c.counter},
            ${c.transports ? JSON.stringify(c.transports) : null}, ${device?.slice(0, 200) ?? null})
    ON CONFLICT (id) DO NOTHING`;
}

export async function loginOptions() {
  const { rpID } = await site();
  const options = await generateAuthenticationOptions({ rpID, userVerification: "preferred" });
  await setSigned(CHALLENGE, JSON.stringify({ c: options.challenge }), 300);
  return options;
}

/** The user a passkey sign-in belongs to, or an error to show. */
export async function checkLogin(response: AuthenticationResponseJSON): Promise<number> {
  const saved = await takeSigned(CHALLENGE);
  if (!saved) throw new Error("That took too long: please try again.");
  const rows = await home()`SELECT id, user_id, public_key, counter, transports FROM public.passkeys WHERE id = ${response.id}`;
  if (!rows.length) throw new Error("This site doesn't know that passkey. Ask for a new invite link.");
  const p = rows[0];
  const { rpID, origin } = await site();
  const v = await verifyAuthenticationResponse({
    response, expectedChallenge: JSON.parse(saved).c, expectedOrigin: origin, expectedRPID: rpID,
    credential: { id: p.id, publicKey: new Uint8Array(Buffer.from(p.public_key, "base64url")), counter: Number(p.counter),
                  transports: p.transports ? JSON.parse(p.transports) : undefined },
    requireUserVerification: false,
  });
  if (!v.verified) throw new Error("The passkey couldn't be checked: please try again.");
  await home()`UPDATE public.passkeys SET counter = ${v.authenticationInfo.newCounter}, last_used = now() WHERE id = ${p.id}`;
  return Number(p.user_id);
}
