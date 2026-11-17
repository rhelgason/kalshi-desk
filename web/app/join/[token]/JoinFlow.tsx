"use client";

import { browserSupportsWebAuthn, startRegistration } from "@simplewebauthn/browser";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { connectKalshi, joinPasskey, joinStart } from "@/app/account";
import { checkKeyId, checkPem, type Check } from "@/lib/keycheck";

const cancelled = (e: unknown) => e instanceof Error && (e.name === "NotAllowedError" || e.name === "AbortError");

/** Where someone is in the setup, kept on this device so leaving and coming back lands on the same screen. */
const SPOT = "nux-setup";
const remember = (step: number) => { try { localStorage.setItem(SPOT, String(step)); } catch {} };
const recall = (): number | null => { try { const v = Number(localStorage.getItem(SPOT)); return v >= 1 && v <= 3 ? v : null; } catch { return null; } };

const TITLES = ["Welcome", "Your Kalshi account", "Make an API key", "Paste your key", "Done"];

function Hint({ c }: { c: Check | null }) {
  if (!c) return null;
  return <span className={`key-hint ${c.ok ? "up" : "down"}`}>{c.ok ? "✓ " : "⚠ "}{c.text}</span>;
}

/**
 * The new-user experience, part one (11-17): joining and setting up Kalshi, one phone-sized screen at a time.
 * Welcome and a passkey; a Kalshi account with money in it; an API key made click by click; pasting it (with live
 * checks, since both early friends were stuck on what to paste); and the balance Kalshi reports, proof it all works.
 * Then the guided tour of the app itself (components/Tour.tsx). `preview`: the manager walks through it with nothing
 * checked or saved.
 */
export default function JoinFlow({ token, name, owner, hasKey, signedIn, preview = false }:
  { token: string; name: string; owner: string; hasKey: boolean; signedIn: boolean; preview?: boolean }) {
  const router = useRouter();
  const [step, setStep] = useState(preview ? 0 : signedIn ? (hasKey ? 4 : 1) : 0);
  const [agreed, setAgreed] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const [keyId, setKeyId] = useState("");
  const [pem, setPem] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [balance, setBalance] = useState<number | null>(null);

  // Back where they left off (only between the Kalshi screens; the key itself is never kept)
  useEffect(() => {
    if (!preview && signedIn && !hasKey) { const s = recall(); if (s) setStep(s); }
  }, [preview, signedIn, hasKey]);
  const go = (s: number) => { setMsg(null); setStep(s); if (!preview && s >= 1 && s <= 3) remember(s); window.scrollTo(0, 0); };

  const passkey = () => start(async () => {
    setMsg(null);
    if (preview) return go(1);
    if (!browserSupportsWebAuthn()) return setMsg("This browser can't make passkeys. Open the link in Safari, Chrome, Edge or Firefox.");
    const begun = await joinStart(token, agreed);
    if (!begun.ok) return setMsg(begun.error);
    try {
      const done = await joinPasskey(await startRegistration({ optionsJSON: begun.options as never }));
      if (!done.ok) return setMsg(done.error);
      go(hasKey ? 4 : 1);
    } catch (e) {
      if (!cancelled(e)) setMsg(e instanceof Error ? e.message : String(e));
    }
  });

  const readFile = async (f: File | undefined) => {
    if (!f) return;
    if (f.size > 20_000) return setMsg("That file is too big to be a Kalshi key. It should be a small text file.");
    setPem(await f.text());
    setFileName(f.name);
    setMsg(null);
  };

  const idCheck = checkKeyId(keyId), pemCheck = checkPem(pem);
  const ready = !!idCheck?.ok && !!pemCheck?.ok;

  const connect = () => start(async () => {
    setMsg(null);
    if (preview) { setBalance(0); setPem(""); return go(4); }
    const done = await connectKalshi(keyId, pem);
    if (!done.ok) return setMsg(done.error);
    setBalance(done.balance);
    setPem("");
    try { localStorage.removeItem(SPOT); } catch {}
    go(4);
  });

  const tour = () => {
    if (preview) { try { localStorage.setItem("nux-preview", "0"); } catch {} }
    router.push("/");
    router.refresh();
  };

  return (
    <div className="card narrow stack auth nux">
      {preview && <div className="nux-preview-bar">👀 Preview: nothing here is checked or saved.</div>}
      <div className="steps" aria-hidden>{TITLES.map((t, s) => <span key={t} data-on={step >= s ? "" : undefined} />)}</div>
      <p className="nux-count muted small">Step {step + 1} of {TITLES.length} · {TITLES[step]}</p>

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

      {step === 1 && (
        <>
          <h2>Your Kalshi Account</h2>
          <p className="sub">Kalshi is where the money and the bets live. The office only places bets there for you.</p>
          <ol className="howto">
            <li>
              <strong>No account yet?</strong> Sign up at <a href="https://kalshi.com/sign-up" target="_blank" rel="noreferrer">kalshi.com</a>.
              Kalshi asks for ID to confirm it&apos;s you; that usually takes a few minutes.
            </li>
            <li>
              <strong>Already have one?</strong> That works. Two things: close any bets you have open first (the office
              won&apos;t start on an account that already has open bets), and don&apos;t bet on it yourself while the office
              runs, since it checks every bet against Kalshi and yours would confuse it.
            </li>
            <li>
              <strong>Put money in</strong> (optional now): on Kalshi, tap <strong>Deposit</strong>. Start small, like $50.
              Card deposits usually show up within minutes; bank transfers can take a few days. You can also do this later:
              the office starts betting about 10 minutes after the money lands.
            </li>
          </ol>
          <button className="btn primary big" onClick={() => go(2)}>I have a Kalshi account →</button>
          {preview && <button className="link-btn" onClick={() => go(0)}>← Back</button>}
        </>
      )}

      {step === 2 && (
        <>
          <h2>Make an API Key</h2>
          <p className="sub">
            An API key is a pass that lets the office place bets in your account. It can&apos;t move money out. This is
            easiest on a computer.
          </p>
          <ol className="howto">
            <li>Sign in at <a href="https://kalshi.com" target="_blank" rel="noreferrer">kalshi.com</a>.</li>
            <li>Click your <strong>profile</strong> (top right), then <strong>Account &amp; security</strong>.</li>
            <li>Find <strong>API keys</strong> and click <strong>Create new API key</strong>. Name it anything, like &quot;Kalshi Desk&quot;. If Kalshi asks what it may do, allow trading.</li>
            <li>
              Kalshi shows you <strong>two things, only once</strong>. Keep this page open next to it:
              <div className="key-sample">
                <div className="key-sample-label">1. The <strong>Key ID</strong>: one short line, like</div>
                <code>1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d</code>
                <div className="key-sample-label">2. The <strong>private key</strong>: a long block (Kalshi offers it as a file to download), like</div>
                <pre>{"-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAu3x9Lk2vQ8b…\nq7Hc0Zt1mPa4W9sdf0Kx2Ln5Rr…\n…about 25 lines like these…\n-----END RSA PRIVATE KEY-----"}</pre>
              </div>
            </li>
            <li><strong>Download the private key file</strong> and copy the Key ID. Then come back here.</li>
          </ol>
          <p className="muted small">
            Closed it before saving them? No harm done: delete that key on Kalshi and make a new one.
          </p>
          <button className="btn primary big" onClick={() => go(3)}>I have my Key ID and private key →</button>
          <button className="link-btn" onClick={() => go(1)}>← Back</button>
        </>
      )}

      {step === 3 && (
        <>
          <h2>Paste Your Key</h2>
          <div className="form nux-form">
            <label>
              <span className="nux-label">1. Key ID <span className="muted small">(the short line)</span></span>
              <input value={keyId} onChange={(e) => setKeyId(e.target.value)} placeholder="1a2b3c4d-5e6f-…" autoComplete="off"
                     autoCapitalize="off" spellCheck={false} />
              <Hint c={idCheck} />
            </label>
            <div className="nux-field">
              <span className="nux-label">2. Private key <span className="muted small">(the long block)</span></span>
              <label className="btn file-btn">
                📄 {fileName ? `Chosen: ${fileName}` : "Choose the downloaded file"}
                <input type="file" accept=".pem,.key,.txt,text/plain" onChange={(e) => readFile(e.target.files?.[0])} hidden />
              </label>
              <span className="muted small nux-or">or paste it</span>
              <textarea className="pem" value={pem} onChange={(e) => { setPem(e.target.value); setFileName(null); }}
                        placeholder={"-----BEGIN RSA PRIVATE KEY-----\n…\n-----END RSA PRIVATE KEY-----"} spellCheck={false} />
              <Hint c={pemCheck} />
            </div>
          </div>
          <ul className="howto small nux-rules">
            <li><strong>Paste all of it</strong>, from <code>-----BEGIN</code> to <code>-----END … KEY-----</code>, those two lines included.</li>
            <li>Copied it without the <code>-----</code> lines? That&apos;s fine too: we add them back.</li>
            <li>Spaces and line breaks don&apos;t matter.</li>
          </ul>
          <p className="muted small">
            It&apos;s checked with Kalshi, then locked so that only the desk&apos;s server can use it. Nobody can read it
            back, including this website.
          </p>
          <button className="btn primary big" disabled={pending || !ready} onClick={connect}>
            {pending ? "Checking with Kalshi…" : "Connect"}
          </button>
          <button className="link-btn" onClick={() => go(2)}>← How do I make a key?</button>
        </>
      )}

      {step === 4 && (
        <>
          <h2>You&apos;re Connected! 🎉</h2>
          {balance != null && balance > 0 && (
            <p className="nux-balance up">Kalshi says your account has <strong>${balance.toFixed(2)}</strong> ✓</p>
          )}
          {balance != null && balance <= 0 && (
            <p className="nux-balance">
              Kalshi says your account has <strong>$0</strong> so far. That&apos;s fine: once a deposit lands, the office
              notices within about 10 minutes and starts betting.
            </p>
          )}
          {balance == null && <p className="nux-balance up">Your Kalshi key is connected ✓</p>}
          <p>
            Your office opens within a couple of minutes. Meanwhile, here&apos;s a quick tour of the app: tap the
            highlighted thing at each step.
          </p>
          <button className="btn primary big" onClick={tour}>Start the tour →</button>
        </>
      )}

      {msg && <div className="down">{msg}</div>}
    </div>
  );
}
