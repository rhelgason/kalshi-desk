"use client";

import { browserSupportsWebAuthn, startRegistration } from "@simplewebauthn/browser";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { connectKalshi, joinPasskey, joinStart, savePrefs } from "@/app/account";
import { checkKeyId, checkPem, type Check } from "@/lib/keycheck";

const cancelled = (e: unknown) => e instanceof Error && (e.name === "NotAllowedError" || e.name === "AbortError");

/** Where someone is between the Kalshi screens, kept on this device so leaving and coming back lands on the same one. */
const SPOT = "nux-setup";
const remember = (step: number) => { try { localStorage.setItem(SPOT, String(step)); } catch {} };
const recall = (): number | null => { try { const v = Number(localStorage.getItem(SPOT)); return v >= 1 && v <= 3 ? v : null; } catch { return null; } };

const TITLES = ["Welcome", "Your Kalshi account", "Make an API key", "Paste your key", "Put money in", "Done"];
const SIGN_UP = "https://kalshi.com/sign-up";

/** A made-up key for the manager's preview: the right shape, so the paste checks can be tried. */
const PRETEND_ID = "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d";
function pretendKey(): string {
  const abc = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  let body = "MIIEowIBAAKCAQEA";
  while (body.length < 1588) body += abc[Math.floor(Math.random() * abc.length)];
  return ["-----BEGIN RSA PRIVATE KEY-----", ...(body.match(/.{1,64}/g) ?? []), "-----END RSA PRIVATE KEY-----"].join("\n");
}

function Hint({ c }: { c: Check | null }) {
  if (!c) return null;
  return <span className={`key-hint ${c.ok ? "up" : "down"}`}>{c.ok ? "✓ " : "⚠ "}{c.text}</span>;
}

/**
 * The new-user experience, part one (11-17): joining and setting up Kalshi, one phone-sized screen at a time.
 * Welcome and a passkey; a Kalshi account (have one, or make one); an API key made click by click; pasting it (with
 * live checks, since both early friends were stuck on what to paste); then money in, optional, with the balance
 * Kalshi reported when the key was checked. Then the guided tour of the app (components/Tour.tsx).
 *
 * `preview`: the manager walks through it as a friend would, on pretend data: no passkey, a made-up key on request,
 * a pretend balance they pick, and nothing checked or saved.
 */
export default function JoinFlow({ token, name, owner, hasKey, signedIn, preview = false }:
  { token: string; name: string; owner: string; hasKey: boolean; signedIn: boolean; preview?: boolean }) {
  const router = useRouter();
  const [step, setStep] = useState(preview ? 0 : signedIn ? (hasKey ? 4 : 1) : 0);
  const [creating, setCreating] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const [keyId, setKeyId] = useState("");
  const [pem, setPem] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [balance, setBalance] = useState<number | null>(null);
  const [pretendBalance, setPretendBalance] = useState(0);
  const [deposited, setDeposited] = useState(false);
  const [sheet, setSheet] = useState(false);
  const [testing, setTesting] = useState(false);

  // Back where they left off (only between the Kalshi screens; the key itself is never kept)
  useEffect(() => {
    if (!preview && signedIn && !hasKey) { const s = recall(); if (s) setStep(s); }
  }, [preview, signedIn, hasKey]);
  const go = (s: number) => {
    setMsg(null); setCreating(false); setStep(s);
    if (!preview && s >= 1 && s <= 3) remember(s);
    window.scrollTo(0, 0);
  };

  const passkey = () => start(async () => {
    setMsg(null);
    if (preview) return setSheet(true);
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

  // Tested live with Kalshi on the next screen, with a clear "testing" state; a failure goes back to the paste screen
  const connect = () => {
    setTesting(true);
    go(4);
    start(async () => {
      if (preview) {
        await new Promise((r) => setTimeout(r, 1800));
        setBalance(pretendBalance); setPem(""); setTesting(false);
        return;
      }
      const done = await connectKalshi(keyId, pem);
      setTesting(false);
      if (!done.ok) { go(3); setMsg(done.error); return; }
      setBalance(done.balance);
      setPem("");
      try { localStorage.removeItem(SPOT); } catch {}
    });
  };

  const tour = () => start(async () => {
    if (preview) {
      try { localStorage.setItem("nux-preview", "0"); } catch {}
      // the app shows a new friend's day one, with this pretend balance (lib/fresh.ts)
      document.cookie = `nux_fresh=${balance ?? pretendBalance}; path=/; max-age=7200; samesite=lax`;
    }
    else await savePrefs({ nux: "0" });
    router.push("/");
    router.refresh();
  });

  const funded = balance != null && balance > 0;

  return (
    <div className="card narrow stack auth nux">
      {preview && (
        <div className="nux-preview-bar">
          👀 Preview with pretend data: nothing is checked or saved.
          {step <= 3 && (
            <span className="nux-preview-pick">
              Pretend Kalshi balance:
              {[0, 50].map((b) => (
                <button key={b} type="button" className="chip" aria-pressed={pretendBalance === b} onClick={() => setPretendBalance(b)}>${b}</button>
              ))}
            </span>
          )}
        </div>
      )}
      <div className="steps" aria-hidden>{TITLES.map((t, s) => <span key={t} data-on={step >= s ? "" : undefined} />)}</div>
      <p className="nux-count muted small">Step {step + 1} of {TITLES.length} · {TITLES[step]}</p>

      {step === 0 && (
        <>
          <h2>Welcome {name}! 👋</h2>
          <p>
            {owner} invited you to <strong>Kalshi Desk</strong>, an office full of your own trading bots that bet on
            Kalshi markets.
          </p>
          <ul className="howto">
            <li>💵 Real money that stays in your own Kalshi account. Your bots can only trade on it, not withdraw it.</li>
            <li>📉 It can lose. Although results have made money so far, that&apos;s no promise. Only put in money that you are fine with fully losing.</li>
            <li>👀 {owner} sees every office&apos;s numbers (balance, bets, staff) to keep them all running well. That&apos;s part of joining.</li>
            <li>⏸ You can pause your office on the site whenever you like, for as long as you like, and resume when you&apos;re ready.</li>
          </ul>
          <label className="check nux-agree">
            <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
            <span>I&apos;ve read this, and I&apos;m in.</span>
          </label>
          <p className="sub">Next, create a passkey: your face, fingerprint or device PIN signs you in from now on. No password.</p>
          <button className="btn primary big" disabled={!agreed || pending} onClick={passkey}>
            {pending ? "Waiting for your device…" : "Create my passkey"}
          </button>
        </>
      )}

      {step === 1 && !creating && (
        <>
          <h2>Your Kalshi Account</h2>
          <p className="sub">Kalshi is where your money and the bets live. The office only places bets there for you.</p>
          <ol className="howto">
            <li>
              <strong>No account yet?</strong> <a href={SIGN_UP} target="_blank" rel="noreferrer">Sign up on Kalshi</a>.
              Kalshi asks for ID to confirm it&apos;s you; that usually takes a few minutes.
            </li>
            <li>
              <strong>Already have one?</strong> That works. Two things: close any bets you have open first (the office
              won&apos;t start on an account that already has open bets), and don&apos;t bet on it yourself while the office
              runs, since it checks every bet against Kalshi and yours would confuse it.
            </li>
          </ol>
          <div className="nux-choice">
            <button className="btn primary big" onClick={() => go(2)}>I have a Kalshi account →</button>
            <a className="btn big" href={SIGN_UP} target="_blank" rel="noreferrer" onClick={() => setCreating(true)}>Create a Kalshi account</a>
          </div>
          {preview && <button className="link-btn" onClick={() => go(0)}>← Back</button>}
        </>
      )}

      {step === 1 && creating && (
        <>
          <h2>Create Your Kalshi Account</h2>
          <p className="sub">Kalshi&apos;s sign-up opened in a new tab. Keep this tab open: you&apos;ll come back here next.</p>
          <ol className="howto">
            <li>Sign up with your email and confirm it.</li>
            <li>Kalshi asks for your details and a photo ID to confirm it&apos;s you. That usually takes a few minutes, sometimes longer.</li>
            <li>Once you can sign in to Kalshi, come back to this tab.</li>
          </ol>
          <p className="muted small">
            No new tab? <a href={SIGN_UP} target="_blank" rel="noreferrer">Open Kalshi&apos;s sign-up</a>. Waiting on the ID check?
            You can close this and come back later: you&apos;ll land right here.
          </p>
          <button className="btn primary big" onClick={() => go(2)}>My Kalshi account is ready →</button>
          <button className="link-btn" onClick={() => setCreating(false)}>← Back</button>
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
            <li>Kalshi shows you <strong>two things, only once</strong>. Keep this page open next to it.</li>
          </ol>
          <div className="key-sample">
            <div className="key-sample-label"><strong>The Key ID</strong>: the key&apos;s name tag. One short line of numbers, letters and dashes. Copy it. Ex:</div>
            <code>1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d</code>
          </div>
          <div className="key-sample">
            <div className="key-sample-label"><strong>The private key</strong>: the secret part. A long block of about 25 lines; Kalshi offers it as a file. Download it. Ex:</div>
            <pre>{"-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAu3x9Lk2vQ8b…\nq7Hc0Zt1mPa4W9sdf0Kx2Ln5Rr…\n…about 25 lines like these…\n-----END RSA PRIVATE KEY-----"}</pre>
          </div>
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
          {preview && (
            <button type="button" className="btn small" onClick={() => { setKeyId(PRETEND_ID); setPem(pretendKey()); setFileName(null); }}>
              Fill in a pretend key
            </button>
          )}
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
          <p className="nux-rules"><strong>Paste all of it, including the BEGIN and END comments.</strong></p>
          <p className="muted small">
            It&apos;s checked with Kalshi, then locked so that only the desk&apos;s server can use it. Nobody can read it
            back, including this website.
          </p>
          <button className="btn primary big" disabled={pending || !ready} onClick={connect}>Connect</button>
          <button className="link-btn" onClick={() => go(2)}>← How do I make a key?</button>
        </>
      )}

      {step === 4 && (
        <>
          <h2>Put Money In <span className="muted">(optional)</span></h2>
          {testing ? (
            <div className="nux-testing" role="status">
              <span className="nux-spinner" aria-hidden />
              <div>
                <strong>Testing your key with Kalshi…</strong>
                <div className="muted small">Asking Kalshi live for your balance. This takes a few seconds.</div>
              </div>
            </div>
          ) : (<>
          <p className="nux-balance up">✓ Kalshi accepted your key.</p>
          {balance != null && (
            <p className="nux-balance">Kalshi says your account has <strong>${balance.toFixed(2)}</strong>{funded ? " ✓" : " so far."}</p>
          )}
          {funded ? (
            <p>That&apos;s enough to start: the staff begin betting with it within about 10 minutes. Add more on Kalshi any time.</p>
          ) : (
            <>
              <p>The staff bet with whatever is in your Kalshi account. You can put money in now or any time later.</p>
              <ol className="howto">
                <li>On <a href="https://kalshi.com" target="_blank" rel="noreferrer">kalshi.com</a>, tap <strong>Deposit</strong>.</li>
                <li>Start small, like $50. Card deposits usually show up within minutes; bank transfers can take a few days.</li>
                <li>The office automatically notices the money about 10 minutes after it lands and starts betting.</li>
              </ol>
            </>
          )}
          {funded ? (
            <button className="btn primary big" onClick={() => go(5)}>Next →</button>
          ) : (
            <div className="nux-choice">
              <button className="btn primary big" onClick={() => { setDeposited(true); go(5); }}>I&apos;ve put money in →</button>
              <button className="btn big" onClick={() => { setDeposited(false); go(5); }}>Skip for now</button>
            </div>
          )}
          </>)}
        </>
      )}

      {step === 5 && (
        <>
          <h2>You&apos;re All Set Up! 🎉</h2>
          <p>
            {funded ? "Your office opens within a couple of minutes and starts betting with your money."
              : deposited ? "Your office opens within a couple of minutes. Once your deposit lands on Kalshi, the staff start betting with it within about 10 minutes."
              : "Your office opens within a couple of minutes. Put money in on Kalshi whenever you like: the staff start betting about 10 minutes after it lands."}
          </p>
          <p>Next, a tour of the app.</p>
          <button className="btn primary big" disabled={pending} onClick={tour}>Start the tour →</button>
          <button className="link-btn" onClick={() => go(4)}>← Back</button>
        </>
      )}

      {msg && <div className="down">{msg}</div>}

      {/* The preview's stand-in for the device's own passkey prompt (a real one would save a passkey for nothing) */}
      {sheet && (
        <div className="nux-sheet-wrap" role="dialog" aria-modal="true" aria-label="Create a passkey">
          <div className="nux-sheet">
            <div className="nux-sheet-icon" aria-hidden>🔑</div>
            <h3>Create a passkey?</h3>
            <p>Save a passkey for <strong>{name}</strong> on <strong>kalshi-desk-nu.vercel.app</strong>. You&apos;ll sign in with Face ID, Touch ID or your device PIN.</p>
            <div className="nux-sheet-btns">
              <button type="button" className="btn" onClick={() => setSheet(false)}>Cancel</button>
              <button type="button" className="btn primary" onClick={() => { setSheet(false); go(1); }}>Continue</button>
            </div>
            <p className="muted small">Preview: roughly what your friend&apos;s phone or computer shows here. It looks a little different on each device, and nothing is saved.</p>
          </div>
        </div>
      )}
    </div>
  );
}
