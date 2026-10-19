"use client";

import { useMemo, useState, type ReactNode } from "react";
import type { Coin } from "@/lib/coin";
import type { PortfolioPoint } from "@/lib/portfolio";
import type { Point, PoolSummary, Position } from "@/lib/types";
import { dollars, pct, shortName } from "@/lib/format";
import Avatar from "./Avatar";
import CoinGauges from "./CoinGauges";
import PoolGauges, { type PoolRecord } from "./PoolGauges";
import PortfolioChart from "./PortfolioChart";

/**
 * One pool member. profit: their running profit over the range shown; season: their
 * profit since the start; today: their change since midnight; light: the long-run
 * verdict; bets: how many have finished.
 */
export type Member = {
  key: string; name: string; emoji: string; light: string; bets: number;
  profit: Point[]; season: number; today: number;
};
type Settled = { t: number; strategy: string; coin: string; pnl: number };

/** Would benching them for real be smart? Judged on the long run, never on one stretch. */
function verdict(m: Member, change: number): string {
  const he = shortName(m.name);
  if (m.light === "bad") return `Honestly? ${he} has earned the bench.`;
  if (m.light === "good") return change < 0 ? `Just a dip, though. ${he} is fine.` : `${he} is pulling their weight.`;
  if (m.bets < 30) return `Too early to blame ${he}, though.`;
  return `Could still be luck either way.`;
}

const valueAt = (pts: Point[], t: number) => {
  let v = 0;
  for (const p of pts) {
    if (p.t > t) break;
    v = p.v;
  }
  return v;
};

const names = (ms: Member[]) =>
  ms.length <= 2 ? ms.map((m) => shortName(m.name)).join(" and ") : `those ${ms.length}`;

/**
 * The money card, top to bottom: the headline, "What if…" (tap employees to send
 * them home), the stat cards, and the chart. Everything under the chips follows
 * the pick, so a real day without someone can be read at a glance.
 * Only the office pool is here: the yardsticks bet their own play money.
 */
export default function MoneyHero(props: {
  top: ReactNode; under?: ReactNode; tabs: ReactNode; footer?: ReactNode;
  points: PortfolioPoint[]; period: string; showChange: boolean;
  team: Member[]; outside: string[];
  /** the pool's finished bets (one coin's, in a coin view) and open bets, for the cards */
  settled: Settled[]; positions: Position[]; tz: string;
  view: { kind: "pool"; pool: PoolSummary | null; worth: number; putIn: number; profit: number; since: string }
    | { kind: "coin"; coin: Coin; coinName: string; since: string; wholePool: number };
}) {
  const { points, team, view, settled, positions, tz } = props;
  const [benched, setBenched] = useState<string[]>([]);
  const out = team.filter((m) => benched.includes(m.key));
  const minus = (f: (m: Member) => number) => out.reduce((s, m) => s + f(m), 0);

  // Each employee's profit or loss over the period shown
  const change = useMemo(() => {
    const t0 = points[0]?.t ?? 0, t1 = points[points.length - 1]?.t ?? 0;
    return Object.fromEntries(team.map((m) => [m.key, valueAt(m.profit, t1) - valueAt(m.profit, t0)]));
  }, [points, team]);
  const ordered = [...team].filter((m) => Math.abs(change[m.key]) >= 0.01).sort((a, b) => change[a.key] - change[b.key]);
  const last = points[points.length - 1], first = points[0];
  const actual = last && first ? last.worth - last.putIn - (first.worth - first.putIn) : 0;
  const altResult = actual - benched.reduce((s, k) => s + (change[k] ?? 0), 0);

  const alt = useMemo(() => {
    if (!benched.length || !points.length) return null;
    const t0 = points[0].t;
    const gone = team.filter((m) => benched.includes(m.key));
    return points.map((p) => p.worth - gone.reduce((s, m) => s + valueAt(m.profit, p.t) - valueAt(m.profit, t0), 0));
  }, [benched, points, team]);

  // The cards' numbers without the benched employees' bets
  const day = (t: number) => new Date(t).toLocaleDateString("en-CA", { timeZone: tz });
  const record = (keep: (k: string) => boolean): PoolRecord => {
    const today = day(Date.now());
    const rows = settled.filter((s) => keep(s.strategy));
    const td = rows.filter((s) => day(s.t) === today);
    return { today: { n: td.length, won: td.filter((s) => s.pnl > 0).length }, season: { n: rows.length, won: rows.filter((s) => s.pnl > 0).length } };
  };
  const whatIf = view.kind === "pool" && view.pool && benched.length ? {
    inPlay: positions.filter((p) => !benched.includes(p.strategy)).reduce((s, p) => s + p.cost, 0),
    today: view.pool.equity - view.pool.day_open - minus((m) => m.today),
    record: record((k) => !benched.includes(k)),
  } : null;

  const toggle = (k: string) => setBenched((b) => (b.includes(k) ? b.filter((x) => x !== k) : [...b, k]));
  const word = (v: number) => <strong className={v >= 0 ? "up" : "down"}>{v >= 0 ? "up" : "down"} {dollars(Math.abs(v))}</strong>;
  const altSeason = (view.kind === "pool" ? view.profit : settled.reduce((s, r) => s + r.pnl, 0)) - minus((m) => m.season);

  return (
    <section className="card money-hero">
      {props.top}
      {view.kind === "coin" ? (
        <>
          <div className={`big-number ${settled.reduce((s, r) => s + r.pnl, 0) >= 0 ? "up" : "down"}`}>
            {dollars(settled.reduce((s, r) => s + r.pnl, 0), true)}
          </div>
          <div className="muted">
            Profit from {settled.length} finished {view.coinName} bet{settled.length === 1 ? "" : "s"} since {view.since}
            {settled.length ? <> ({pct(settled.filter((s) => s.pnl > 0).length / settled.length, false, 0)} won)</> : null}.
            {" "}The whole pool is {dollars(view.wholePool)} across all coins.
          </div>
        </>
      ) : (
        <>
          <div className="big-number">{dollars(view.worth)}</div>
          <div className={`change ${view.profit >= 0 ? "up" : "down"}`}>
            {view.profit >= 0 ? "▲" : "▼"} {dollars(Math.abs(view.profit))} ({pct(Math.abs(view.profit / (view.putIn || 1)), false, 1)}) {view.profit >= 0 ? "profit" : "loss"} since {view.since}
          </div>
        </>
      )}
      {benched.length > 0 && (
        <div className="whatif-line">
          🔮 Without {names(out)}: <strong className={altSeason >= 0 ? "up" : "down"}>{dollars(altSeason, true)}</strong> since {view.since}
        </div>
      )}
      {props.under}

      <div className="whatif">
        <div className="whatif-head">
          <strong>🔮 What if…</strong>
          {benched.length > 0 && <button className="btn small" onClick={() => setBenched([])}>Reset</button>}
        </div>
        {benched.length ? (
          <p className="whatif-result">
            {props.period}, without {names(out)}, you&apos;d be {word(altResult)}, not {word(actual)}.{" "}
            {benched.length === 1 && <span className="muted">{verdict(out[0], change[benched[0]] ?? 0)}</span>}
          </p>
        ) : (
          <p className="whatif-result muted">…someone had stayed home? Tap names: the cards and chart below follow.</p>
        )}
        <div className="chips">
          {ordered.map((m) => (
            <button key={m.key} className={`chip ${benched.includes(m.key) ? "on" : ""}`} onClick={() => toggle(m.key)} aria-pressed={benched.includes(m.key)}>
              <Avatar k={m.key} emoji={m.emoji} size={18} /> {m.name.split(" ").slice(-1)[0]} <span className={change[m.key] >= 0 ? "up" : "down"}>{dollars(change[m.key], true)}</span>
            </button>
          ))}
          {!ordered.length && <span className="muted small">Nobody has won or lost anything in this range yet.</span>}
        </div>
        {props.outside.length > 0 && (
          <p className="muted small" style={{ margin: "8px 0 0" }}>
            {props.outside.join(" and ")} (yardsticks) bet their own play money, so they&apos;re never in this pool.
          </p>
        )}
      </div>

      {view.kind === "coin"
        ? <CoinGauges coin={view.coin} settled={settled} positions={positions} tz={tz} benched={benched}
            names={Object.fromEntries(team.map((m) => [m.key, m.name]))} />
        : view.pool && <PoolGauges pool={view.pool} record={record(() => true)} whatIf={whatIf} />}
      {benched.length > 0 && view.kind === "pool" && (
        <p className="muted small" style={{ margin: "4px 0 0" }}>Orange-edged cards are the what-if; the rest show what really happened.</p>
      )}

      {props.tabs}
      <PortfolioChart points={points} alt={alt} profitOnly={view.kind === "coin" ? `${view.coinName} profit` : undefined} />
      {props.showChange && first && (
        <p className="range-change">
          {props.period}: <strong className={actual >= 0 ? "up" : "down"}>{actual >= 0 ? "▲ up" : "▼ down"} {dollars(Math.abs(actual))}</strong>
          {benched.length > 0 && <> · what if: <strong className={altResult >= 0 ? "up" : "down"}>{altResult >= 0 ? "▲ up" : "▼ down"} {dollars(Math.abs(altResult))}</strong></>}
        </p>
      )}
      {props.footer}
    </section>
  );
}
