"use client";

import { browserSupportsWebAuthn, startAuthentication, startRegistration } from "@simplewebauthn/browser";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { loginFinish, loginStart, passkeyFinish, passkeyStart } from "@/app/account";

/** A browser's own words for "you cancelled" (the passkey sheet closed): not worth an error. */
const cancelled = (e: unknown) => e instanceof Error && (e.name === "NotAllowedError" || e.name === "AbortError");
const unsupported = "This browser can't use passkeys. Try Safari, Chrome, Edge or Firefox, up to date.";

/** Sign in with a passkey: no username, the device asks for its own lock (face, finger, PIN) and that's it. */
export function PasskeyLogin({ next = "/" }: { next?: string }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);
  const go = () => start(async () => {
    setMsg(null);
    if (!browserSupportsWebAuthn()) return setMsg(unsupported);
    const begun = await loginStart();
    if (!begun.ok) return setMsg(begun.error);
    try {
      const done = await loginFinish(await startAuthentication({ optionsJSON: begun.options }));
      if (!done.ok) return setMsg(done.error);
      router.push(next);
      router.refresh();
    } catch (e) {
      if (!cancelled(e)) setMsg(String(e instanceof Error ? e.message : e));
    }
  });
  return (
    <div className="stack-tight">
      <button className="btn primary big" disabled={pending} onClick={go}>{pending ? "Waiting for your device…" : "🔑 Sign in with a passkey"}</button>
      {msg && <div className="down">{msg}</div>}
    </div>
  );
}

/** Save a passkey on this device (for someone signed in, or the manager by password making their owner login). */
export function AddPasskey({ label = "📱 Remember this device with a passkey", askName = false }: { label?: string; askName?: boolean }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);
  const [name, setName] = useState("");
  const go = () => start(async () => {
    setMsg(null);
    if (!browserSupportsWebAuthn()) return setMsg(unsupported);
    const begun = await passkeyStart(name || undefined);
    if (!begun.ok) return setMsg(begun.error);
    try {
      const done = await passkeyFinish(await startRegistration({ optionsJSON: begun.options }));
      setMsg(done.ok ? "✓ Saved. This device (and any synced to it) signs in with a tap from now on." : done.error);
      router.refresh();
    } catch (e) {
      if (!cancelled(e)) setMsg(String(e instanceof Error ? e.message : e));
    }
  });
  return (
    <div className="stack-tight">
      {askName && (
        <label className="form">Your first name <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} /></label>
      )}
      <button className="btn" disabled={pending} onClick={go}>{pending ? "Waiting for your device…" : label}</button>
      {msg && <div className={msg.startsWith("✓") ? "up" : "down"}>{msg}</div>}
    </div>
  );
}
