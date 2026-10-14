"use client";

import { useState, useTransition } from "react";
import { fireEmployee, rehireEmployee, reinstateEmployee, setLevel, suspendEmployee } from "@/app/actions";
import { LEVELS, poolShare } from "@/lib/hr";
import type { Employee } from "@/lib/types";

/** The everyday manager controls in one slim row: bet size, bench, fire. Everything else lives further down. */
export default function ManagerBar({ e }: { e: Employee }) {
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);
  const status = e.status ?? "active";
  const run = (fn: () => Promise<unknown>, ok: string) =>
    start(async () => {
      try {
        const r = (await fn()) as { error?: string } | undefined;
        setMsg(r?.error ? `⚠ ${r.error}` : `✓ ${ok}`);
      } catch (err) {
        setMsg(`⚠ ${String(err)}`);
      }
    });

  return (
    <section className="card manager-bar">
      <span className="label">👔 Manager</span>
      {status !== "fired" && (
        <select aria-label="Bet size" value={e.level ?? 1} disabled={pending}
          onChange={(ev) => { const l = Number(ev.target.value); run(() => setLevel(e.key, l), `Bets now ${poolShare(LEVELS[l].multiplier)} of the pool (${LEVELS[l].title})`); }}>
          {LEVELS.map((l, i) => <option key={l.title} value={i}>{l.title} · {poolShare(l.multiplier)} of the pool per bet</option>)}
        </select>
      )}
      {status === "fired" ? (
        <button className="btn small" disabled={pending} onClick={() => run(() => rehireEmployee(e.key), "Rehired as an Intern")}>🔄 Rehire</button>
      ) : status === "suspended" ? (
        <button className="btn small" disabled={pending} onClick={() => run(() => reinstateEmployee(e.key), "Back at work")}>▶️ Bring back</button>
      ) : (
        <select aria-label="Bench" value="" disabled={pending}
          onChange={(ev) => {
            const d = ev.target.value;
            if (!d) return;
            const days = d === "forever" ? null : Number(d);
            run(() => suspendEmployee(e.key, days, ""), days ? `Benched for ${days} day${days > 1 ? "s" : ""}` : "Benched until you bring them back");
          }}>
          <option value="">⏸️ Bench…</option>
          <option value="1">for 1 day</option>
          <option value="3">for 3 days</option>
          <option value="7">for 7 days</option>
          <option value="forever">until I say so</option>
        </select>
      )}
      {status !== "fired" && (
        <button className="btn small danger" disabled={pending}
          onClick={() => {
            const why = prompt(`Fire ${e.name}? They stop trading for good (you can rehire later). Reason:`);
            if (why !== null) run(() => fireEmployee(e.key, why), "Fired");
          }}>Fire</button>
      )}
      <a href="#manager" className="small muted">More controls ↓</a>
      {msg && <span className="small muted manager-msg">{msg}. Takes effect within ~2 min.</span>}
    </section>
  );
}
