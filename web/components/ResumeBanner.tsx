"use client";

import Link from "next/link";
import { useState, useTransition } from "react";
import { resumeTrading } from "@/app/actions";
import { ago } from "@/lib/format";
import type { KillSwitch } from "@/lib/db";

/**
 * Top of the home page while real trading is paused: why, and a one-tap Resume for the manager
 * (or a link to log in and come straight back), so a pause can be undone from a phone.
 */
export default function ResumeBanner({ kill, admin }: { kill: KillSwitch; admin: boolean }) {
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);
  const resume = () =>
    confirm("Turn real-money betting back on?") &&
    start(async () => {
      try {
        await resumeTrading();
        setMsg("✓ Back on: the bot bets again from its next run (within 2 minutes)");
      } catch (err) {
        setMsg(`⚠ ${String(err)}`);
      }
    });
  return (
    <div className="card resume-banner">
      <div>
        <strong>⏸ Real-money betting is paused</strong>
        <p className="sub">
          {kill.reason || "Stopped by the manager"}
          {kill.at ? ` · ${ago(kill.at)}` : ""}{kill.by === "bot" ? " · by the safety check" : ""}
        </p>
        {kill.reason?.startsWith("our books don't match Kalshi") && (
          <p className="sub">It turns itself back on as soon as the books agree again.</p>
        )}
        {msg && <p className="sub">{msg}</p>}
      </div>
      {msg?.startsWith("✓") ? null : admin ? (
        <button className="btn primary" disabled={pending} onClick={resume}>▶️ Resume</button>
      ) : (
        <Link className="btn primary" href="/admin?next=/">🔑 Log in to resume</Link>
      )}
    </div>
  );
}
