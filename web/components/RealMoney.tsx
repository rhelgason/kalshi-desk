"use client";

import { useState, useTransition } from "react";
import { haltTrading, resumeAllTrading, resumeTrading, stopAllTrading } from "@/app/actions";
import { setOfficePaused } from "@/app/account";
import { ago, dollars } from "@/lib/format";
import type { TradingStatus } from "@/lib/types";

/**
 * Real money at a glance and the stop buttons (11-17). Everyone pauses their own office's betting (`mine`: the
 * manager on their real book, a friend on their own office); only the manager stops all trading, every office at
 * once, and only they lift it.
 */
export default function RealMoney({ trading, killSwitch, admin, mine, office }: {
  trading: TradingStatus;
  killSwitch: { halted: boolean; reason?: string; by?: string; at?: string; all?: boolean };
  admin: boolean;
  mine: boolean;
  office: boolean;
}) {
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);
  const live = trading.mode === "live";
  const halted = killSwitch.halted;
  const books = trading.books;

  const run = (fn: () => Promise<unknown>, ok: string) =>
    start(async () => {
      try {
        const r = (await fn()) as { ok?: boolean; error?: string } | undefined;
        setMsg(r && r.ok === false ? `⚠ ${r.error}` : `✓ ${ok}`);
      } catch (err) {
        setMsg(`⚠ ${String(err)}`);
      }
    });
  const everyone = !!killSwitch.all;
  const pause = () => {
    if (office) {
      if (confirm("Pause your office's betting? Nothing new gets bet until you resume; bets already on finish as usual."))
        run(() => setOfficePaused(true), "Paused from the next run (within 2 minutes)");
      return;
    }
    const why = prompt("Pause your betting? Waiting orders on Kalshi will be cancelled. Reason (optional):");
    if (why === null) return;
    const long = confirm("Is this a long pause? OK shows Training on your phone and the dashboard until you resume; Cancel for a short stop.");
    run(() => haltTrading(why, long), "Paused. The bot cancels waiting orders on its next run");
  };
  const resume = () => confirm("Start betting again?")
    && run(office ? () => setOfficePaused(false) : resumeTrading, "Betting again from the next run (within 2 minutes)");

  return (
    <section className="card">
      <h2>Real Money</h2>
      <p className="sub">
        {live
          ? `Real orders go to Kalshi${trading.env === "demo" ? "'s demo exchange (practice money)" : ""}. `
          : "The desk is on paper money: nothing is sent to Kalshi. "}
        Pausing stops new bets within about 2 minutes and cancels any waiting on Kalshi; bets already on finish as usual.
      </p>
      <dl className="kv">
        <dt>Mode</dt><dd>{live ? `LIVE (${trading.env})` : "Paper"}</dd>
        <dt>Trading</dt>
        <dd className={halted ? "down" : undefined}>
          {halted ? `🛑 Stopped${killSwitch.reason ? `: ${killSwitch.reason}` : ""}${killSwitch.at ? ` (${ago(killSwitch.at)}, by ${killSwitch.by ?? "?"})` : ""}`
            : "✅ Allowed"}
        </dd>
        {live && books && (
          <>
            <dt>Last check vs Kalshi</dt>
            <dd className={books.ok ? undefined : "down"}>
              {books.ok ? "✅ Books match" : `⚠ ${Object.keys(books.mismatches).length} market(s) differ`}
              {` · balance ${dollars(books.balance)}, drift ${dollars(books.drift, true)} · ${ago(books.at)}`}
            </dd>
          </>
        )}
        {live && trading.limits && (
          <>
            <dt>Hard limits</dt>
            <dd>
              {trading.limits.max_order_pct ? `${Math.round(trading.limits.max_order_pct * 100)}% of the pool` : dollars(trading.limits.max_order_dollars)} per order · {trading.limits.max_orders_per_day} orders a day ·
              stop after losing {trading.limits.max_daily_loss_pct ? `${Math.round(trading.limits.max_daily_loss_pct * 100)}% of the pool` : dollars(trading.limits.max_daily_loss)} in a day
            </dd>
          </>
        )}
      </dl>
      {(mine || admin) && (
        <div className="row-btns" data-tour="pause">
          {mine && (halted
            ? <button className="btn primary" disabled={pending || (everyone && !admin)} onClick={resume}>▶️ Resume my betting</button>
            : <button className="btn" disabled={pending} onClick={pause}>⏸ Pause my betting</button>)}
          {admin && (everyone
            ? <button className="btn primary" disabled={pending}
                onClick={() => confirm("Resume trading for everyone?") && run(resumeAllTrading, "Everyone bets again from the next run")}>
                ▶️ Resume everyone
              </button>
            : <button className="btn danger" disabled={pending}
                onClick={() => {
                  const why = prompt("Stop ALL trading, your office and every friend's? Waiting orders are cancelled and only you can turn it back on. Reason (optional):");
                  if (why !== null) run(() => stopAllTrading(why), "Everyone stopped. Waiting orders are cancelled on the next runs");
                }}>
                🛑 Stop all trading
              </button>)}
        </div>
      )}
      {everyone && !admin && <p className="muted small">The manager has stopped all trading; it comes back on when they resume it.</p>}
      {msg && <p className="muted small">{msg}</p>}
    </section>
  );
}
