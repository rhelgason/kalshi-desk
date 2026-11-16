"use client";

import { browserSupportsWebAuthn, startRegistration } from "@simplewebauthn/browser";
import Link from "next/link";
import { useState, useTransition } from "react";
import { connectKalshi, joinPasskey, joinStart } from "@/app/account";

const cancelled = (e: unknown) => e instanceof Error && (e.name === "NotAllowedError" || e.name === "AbortError");

/**
 * Joining in three steps, each a screen that fits a phone: what this is (and a yes), a passkey so they never
 * type a password, then their Kalshi key. Done: the office opens on the server within a couple of minutes.
 */
export default function JoinFlow({ token, name, owner, hasKey, signedIn }:
  { token: string; name: string; owner: string; hasKey: boolean; signedIn: boolean }) {
  const [step, setStep] = useState(signedIn ? (hasKey ? 3 : 2) : 0);
  const [agreed, setAgreed] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const [keyId, setKeyId] = useState("");
  const [pem, setPem] = useState("");
  const [balance, setBalance] = useState<number | null>(null);

  const passkey = () => start(async () => {
    setMsg(null);
    if (!browserSupportsWebAuthn()) return setMsg("This browser can't make passkeys. Open the link in Safari, Chrome, Edge or Firefox.");
    const begun = await joinStart(token, agreed);
    if (!begun.ok) return setMsg(begun.error);
    try {
      const done = await joinPasskey(await startRegistration({ optionsJSON: begun.options as never }));
      if (!done.ok) return setMsg(done.error);
      setStep(hasKey ? 3 : 2);
    } catch (e) {
      if (!cancelled(e)) setMsg(e instanceof Error ? e.message : String(e));
    }
  });

  const readFile = async (f: File | undefined) => {
    if (!f) return;
    if (f.size > 20_000) return setMsg("That file is too big to be a Kalshi key.");
    setPem(await f.text());
    setMsg(null);
  };

  const connect = () => start(async () => {
    setMsg(null);
    const done = await connectKalshi(keyId, pem);
    if (!done.ok) return setMsg(done.error);
    setBalance(done.balance);
    setPem("");
    setStep(3);
  });

  return (
    <div className="card narrow stack auth">
      <div className="steps" aria-hidden>{[0, 2, 3].map((s) => <span key={s} data-on={step >= s ? "" : undefined} />)}</div>

      {step === 0 && (
        <>
          <h2>Hi {name}! 👋</h2>
          <p>
            {owner} invited you to <strong>Kalshi Desk</strong>: a little office of trading bots that bets on
            Kalshi&apos;s short markets (mostly &quot;will bitcoin be up in 15 minutes?&quot;) for you, in your own
            Kalshi account, on its own. It mostly buys strong favorites just under $1 and waits to be paid.
          </p>
          <ul className="howto">
            <li>💵 Real money, yours: it stays in your Kalshi account. The bots can&apos;t withdraw it (Kalshi keys can&apos;t).</li>
            <li>📉 It can lose. It has made money so far, but that&apos;s no promise. Only put in what you&apos;re fine losing.</li>
            <li>👀 {owner} sees every office&apos;s numbers (balance, bets, staff) to keep them all running well. That&apos;s part of joining.</li>
            <li>⏸ You can pause it any time on the site, or stop it for good by deleting the key on Kalshi.</li>
          </ul>
          <label className="check">
            <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
            <span>I&apos;ve read this, and I&apos;m in.</span>
          </label>
          <p className="sub">Next, save a passkey: your face, fingerprint or device PIN signs you in from now on. No password.</p>
          <button className="btn primary big" disabled={!agreed || pending} onClick={passkey}>
            {pending ? "Waiting for your device…" : "Save my passkey"}
          </button>
        </>
      )}

      {step === 2 && (
        <>
          <h2>Connect Your Kalshi Account</h2>
          <p className="sub">The office needs a Kalshi API key to bet for you. It takes a minute (easiest on a computer):</p>
          <ol className="howto">
            <li>No account yet? Sign up at <a href="https://kalshi.com" target="_blank" rel="noreferrer">kalshi.com</a> first. Use this account for the desk only: the office checks every bet against Kalshi, and your own bets would confuse it.</li>
            <li>On kalshi.com open <strong>Account &amp; security</strong> (from your profile), find <strong>API keys</strong>, and choose <strong>Create key</strong>.</li>
            <li>Kalshi shows a <strong>Key ID</strong> and gives you a <strong>private key</strong> file. It&apos;s shown only once, so keep it.</li>
          </ol>
          <div className="form">
            <label>Key ID <input value={keyId} onChange={(e) => setKeyId(e.target.value)} placeholder="a1b2c3d4-…" autoComplete="off" spellCheck={false} /></label>
            <label>Private key file <input type="file" accept=".pem,.key,.txt,text/plain" onChange={(e) => readFile(e.target.files?.[0])} /></label>
            <label>…or paste it <textarea className="pem" value={pem} onChange={(e) => setPem(e.target.value)} placeholder="-----BEGIN RSA PRIVATE KEY-----" spellCheck={false} /></label>
          </div>
          <p className="muted small">It&apos;s checked with Kalshi, then locked so that only the desk&apos;s server can use it. Nobody can read it back, including this website.</p>
          <button className="btn primary big" disabled={pending || !keyId || !pem} onClick={connect}>
            {pending ? "Checking with Kalshi…" : "Connect"}
          </button>
        </>
      )}

      {step === 3 && (
        <>
          <h2>You&apos;re In!</h2>
          {balance != null && <p>Kalshi says your account has <strong>${balance.toFixed(2)}</strong>.</p>}
          <p>
            Your office opens within a couple of minutes. Whenever you like, put money in on Kalshi (say $50): the
            office notices within about 10 minutes and the staff start betting with it. Small bets, many times a day.
          </p>
          <p className="sub">This site remembers you. Add it to your home screen to check in with a tap.</p>
          <Link className="btn primary big" href="/">Go to my office →</Link>
        </>
      )}

      {msg && <div className="down">{msg}</div>}
    </div>
  );
}
