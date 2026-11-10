"use client";

import { useMemo, useState, type ReactNode } from "react";
import { betCount, winCount, type PortfolioPoint, type Settlement } from "@/lib/portfolio";
import type { MoneyMove, Point, PoolSummary, Position } from "@/lib/types";
import { dollars, pct, shortName } from "@/lib/format";
import Avatar from "./Avatar";
import PoolGauges, { type PoolRecord } from "./PoolGauges";
import PortfolioChart from "./PortfolioChart";

/**
 * One pool member. profit: their running profit over the range shown; season: their
 * profit since the start; light: the long-run verdict; bets: how many have finished.
 */
export type Member = {
  key: string; name: string; emoji: string; light: string; bets: number;
  profit: Point[]; season: number;
};
type Settled = Settlement;

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
  /** deposits and withdrawals this season, marked on the chart */
  marks?: MoneyMove[];
  /** the chart's range in a few words for the cards ("today", "this week", "lifetime") */
  scope: string;
  team: Member[]; outside: string[];
  /** the pool's finished bets and open bets, for the cards */
  settled: Settled[]; positions: Position[]; tz: string;
  /** the real-money kill switch, when it's on: why */
  halted?: string | null;
  view: { pool: PoolSummary | null; worth: number; putIn: number; profit: number; since: string };
}) {
  const { points, team, view, settled, positions } = props;
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
  const cents = (v: number) => Math.round(v * 100) / 100 || 0; // no "−$0.00" from float dust
  const actual = cents(last && first ? last.worth - last.putIn - (first.worth - first.putIn) : 0);
  const altResult = cents(actual - benched.reduce((s, k) => s + (change[k] ?? 0), 0));

  const alt = useMemo(() => {
    if (!benched.length || !points.length) return null;
    const t0 = points[0].t;
    const gone = team.filter((m) => benched.includes(m.key));
    return points.map((p) => p.worth - gone.reduce((s, m) => s + valueAt(m.profit, p.t) - valueAt(m.profit, t0), 0));
  }, [benched, points, team]);

  // The cards follow the chart: bets that finished in its range, plus the lifetime count;
  // the what-if versions leave the benched employees' bets out
  const t0 = first?.t ?? 0;
  const record = (keep: (k: string) => boolean): PoolRecord => {
    const rows = settled.filter((s) => keep(s.strategy));
    const inRange = rows.filter((s) => s.t >= t0);
    return { range: { n: betCount(inRange), won: winCount(inRange) },
      lifetime: { n: betCount(rows), won: winCount(rows) } };
  };
  const startWorth = first ? first.worth : 0;
  const whatIf = view.pool && benched.length ? {
    inPlay: positions.filter((p) => !benched.includes(p.strategy)).reduce((s, p) => s + p.cost, 0),
    change: altResult,
    record: record((k) => !benched.includes(k)),
  } : null;

  const toggle = (k: string) => setBenched((b) => (b.includes(k) ? b.filter((x) => x !== k) : [...b, k]));
  const word = (v: number) => <strong className={v >= 0 ? "up" : "down"}>{v >= 0 ? "up" : "down"} {dollars(Math.abs(v))}</strong>;
  const altSeason = view.profit - minus((m) => m.season);

  return (
    <section className="card money-hero">
      {props.top}
      <div className="big-number">{dollars(view.worth)}</div>
      <div className={`change ${view.profit >= 0 ? "up" : "down"}`}>
        {view.profit >= 0 ? "▲" : "▼"} {dollars(Math.abs(view.profit))} ({pct(Math.abs(view.profit / (view.putIn || 1)), false, 1)}) {view.profit >= 0 ? "profit" : "loss"} since {view.since}
      </div>
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
              <Avatar k={m.key} emoji={m.emoji} size={18} /> {shortName(m.name)} <span className={change[m.key] >= 0 ? "up" : "down"}>{dollars(change[m.key], true)}</span>
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

      {view.pool && <PoolGauges pool={view.pool} record={record(() => true)} whatIf={whatIf} halted={props.halted}
        change={actual} start={startWorth} scope={props.scope} />}
      {benched.length > 0 && (
        <p className="muted small" style={{ margin: "4px 0 0" }}>Orange-edged cards are the what-if; the rest show what really happened.</p>
      )}

      {props.tabs}
      <PortfolioChart points={points} alt={alt} marks={props.marks} />
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
