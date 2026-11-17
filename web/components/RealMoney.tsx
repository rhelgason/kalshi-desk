"use client";

import { useState, useTransition } from "react";
import { haltTrading, resumeTrading } from "@/app/actions";
import { ago, dollars } from "@/lib/format";
import type { TradingStatus } from "@/lib/types";

/** Real money at a glance, and the kill switch (desk/live). */
export default function RealMoney({ trading, killSwitch, admin }: {
  trading: TradingStatus;
  killSwitch: { halted: boolean; reason?: string; by?: string; at?: string };
  admin: boolean;
}) {
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);
  const live = trading.mode === "live";
  const halted = killSwitch.halted;
  const books = trading.books;

  const run = (fn: () => Promise<unknown>, ok: string) =>
    start(async () => {
      try {
        await fn();
        setMsg(`✓ ${ok}`);
      } catch (err) {
        setMsg(`⚠ ${String(err)}`);
      }
    });

  return (
    <section className="card">
      <h2>Real Money</h2>
      <p className="sub">
        {live
          ? `Real orders go to Kalshi${trading.env === "demo" ? "'s demo exchange (practice money)" : ""}. `
          : "The desk is on paper money: nothing is sent to Kalshi. "}
        The stop button works either way: no new real orders, and any waiting on Kalshi are cancelled within about
        2 minutes. Only you can turn trading back on.
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
      {admin && (
        <div className="row-btns">
          {halted ? (
            <button className="btn primary" disabled={pending}
              onClick={() => confirm("Allow real trading again?") && run(resumeTrading, "Trading allowed again from the next run")}>
              ▶️ Resume real trading
            </button>
          ) : (
            <button className="btn danger" disabled={pending}
              onClick={() => {
                const why = prompt("Stop all real trading? Waiting orders on Kalshi will be cancelled. Reason (optional):");
                if (why === null) return;
                const long = confirm("Is this a long pause? OK shows Training on your phone and the dashboard until you resume; Cancel for a short stop.");
                run(() => haltTrading(why, long), "Stopped. The bot cancels waiting orders on its next run");
              }}>
              🛑 Stop all real trading
            </button>
          )}
        </div>
      )}
      {msg && <p className="muted small">{msg}</p>}
    </section>
  );
}
