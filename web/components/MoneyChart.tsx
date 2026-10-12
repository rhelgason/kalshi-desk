"use client";

import { useMemo, useState } from "react";
import type { PortfolioPoint } from "@/lib/portfolio";
import type { Point } from "@/lib/types";
import { dollars } from "@/lib/format";
import PortfolioChart from "./PortfolioChart";

type Member = { key: string; name: string; emoji: string; profit: Point[] };

const valueAt = (pts: Point[], t: number) => {
  let v = 0;
  for (const p of pts) {
    if (p.t > t) break;
    v = p.v;
  }
  return v;
};

const names = (ms: Member[]) =>
  ms.length <= 2 ? ms.map((m) => m.name).join(" and ") : `${ms.length} employees`;

/**
 * The portfolio chart plus "What if?": tap employees to bench them and see how
 * the same period would have gone without their wins and losses.
 */
export default function MoneyChart({ points, team, period }: { points: PortfolioPoint[]; team: Member[]; period: string }) {
  const [benched, setBenched] = useState<string[]>([]);

  // Each employee's profit or loss over the period shown
  const change = useMemo(() => {
    const t0 = points[0]?.t ?? 0, t1 = points[points.length - 1]?.t ?? 0;
    return Object.fromEntries(team.map((m) => [m.key, valueAt(m.profit, t1) - valueAt(m.profit, t0)]));
  }, [points, team]);
  const ordered = [...team].filter((m) => Math.abs(change[m.key]) >= 0.01).sort((a, b) => change[a.key] - change[b.key]);
  const actual = points.length ? points[points.length - 1].worth - points[points.length - 1].putIn - (points[0].worth - points[0].putIn) : 0;

  const alt = useMemo(() => {
    if (!benched.length || !points.length) return null;
    const t0 = points[0].t;
    const out = team.filter((m) => benched.includes(m.key));
    return points.map((p) => p.worth - out.reduce((s, m) => s + valueAt(m.profit, p.t) - valueAt(m.profit, t0), 0));
  }, [benched, points, team]);
  const altResult = actual - benched.reduce((s, k) => s + (change[k] ?? 0), 0);

  const losers = ordered.filter((m) => change[m.key] < 0).map((m) => m.key);
  const best = ordered.filter((m) => change[m.key] > 0).reduce((s, m) => s + change[m.key], 0);
  const toggle = (k: string) => setBenched((b) => (b.includes(k) ? b.filter((x) => x !== k) : [...b, k]));
  const word = (v: number) => <strong className={v >= 0 ? "up" : "down"}>{v >= 0 ? "▲ up" : "▼ down"} {dollars(Math.abs(v))}</strong>;

  return (
    <>
      <PortfolioChart points={points} alt={alt} />
      <div className="whatif">
        <div className="whatif-head">
          <strong>🔮 What if?</strong>
          <span className="muted small">Tap employees to bench them for {period.toLowerCase()}.</span>
        </div>
        {benched.length ? (
          <p className="whatif-result">
            Without {names(team.filter((m) => benched.includes(m.key)))}, {period.toLowerCase()} would be {word(altResult)} instead of {word(actual)}.
          </p>
        ) : (
          <p className="whatif-result muted">
            {losers.length > 0 && best > 0
              ? <>Best lineup in hindsight (only the {ordered.length - losers.length} who made money): {word(best)}.</>
              : <>Pick someone to see the difference.</>}
          </p>
        )}
        <div className="chips">
          {ordered.map((m) => (
            <button key={m.key} className={`chip ${benched.includes(m.key) ? "on" : ""}`} onClick={() => toggle(m.key)} aria-pressed={benched.includes(m.key)}>
              {m.emoji} {m.name.split(" ").slice(-1)[0]} <span className={change[m.key] >= 0 ? "up" : "down"}>{dollars(change[m.key], true)}</span>
            </button>
          ))}
        </div>
        <div className="row-btns" style={{ marginTop: 8 }}>
          {losers.length > 0 && <button className="btn small" onClick={() => setBenched(losers)}>Bench everyone who lost money</button>}
          {benched.length > 0 && <button className="btn small" onClick={() => setBenched([])}>Reset</button>}
        </div>
        <p className="muted small" style={{ margin: "8px 0 0" }}>
          Hindsight is easy: this shows who hurt or helped, not who will win next. Employees bet with separate money, so benching one doesn&apos;t change the others&apos; bets.
        </p>
      </div>
    </>
  );
}
