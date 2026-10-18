"use client";

import { useMemo, useState } from "react";
import type { PortfolioPoint } from "@/lib/portfolio";
import type { Point } from "@/lib/types";
import { dollars, shortName } from "@/lib/format";
import Avatar from "./Avatar";
import PortfolioChart from "./PortfolioChart";

/** light: the long-run verdict (every bet since the fresh start); bets: how many have finished */
type Member = { key: string; name: string; emoji: string; profit: Point[]; light: string; bets: number };

/** Would benching them for real be smart? Judged on the long run, never on one stretch. */
function verdict(m: Member, change: number): string {
  const he = shortName(m.name);
  if (m.light === "yardstick") return `But ${he} is the yardstick, so he stays.`;
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
 * The portfolio chart plus "What if?": tap employees to see how the same period
 * would have gone without their wins and losses, and whether that would really
 * be a reason to bench them (judged on the long run, not this stretch).
 */
export default function MoneyChart({ points, team, period, profitOnly }: {
  points: PortfolioPoint[]; team: Member[]; period: string; profitOnly?: string;
}) {
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

  const toggle = (k: string) => setBenched((b) => (b.includes(k) ? b.filter((x) => x !== k) : [...b, k]));
  const word = (v: number) => <strong className={v >= 0 ? "up" : "down"}>{v >= 0 ? "up" : "down"} {dollars(Math.abs(v))}</strong>;

  return (
    <>
      <PortfolioChart points={points} alt={alt} profitOnly={profitOnly} />
      <div className="whatif">
        <div className="whatif-head"><strong>🔮 What if…</strong></div>
        {benched.length ? (
          <p className="whatif-result">
            Without {names(team.filter((m) => benched.includes(m.key)))}, you&apos;d be {word(altResult)}, not {word(actual)}.{" "}
            {benched.length === 1 && <span className="muted">{verdict(team.find((m) => m.key === benched[0])!, change[benched[0]] ?? 0)}</span>}
          </p>
        ) : (
          <p className="whatif-result muted">…someone had stayed home? Tap a name.</p>
        )}
        <div className="chips">
          {ordered.map((m) => (
            <button key={m.key} className={`chip ${benched.includes(m.key) ? "on" : ""}`} onClick={() => toggle(m.key)} aria-pressed={benched.includes(m.key)}>
              <Avatar k={m.key} emoji={m.emoji} size={18} /> {m.name.split(" ").slice(-1)[0]} <span className={change[m.key] >= 0 ? "up" : "down"}>{dollars(change[m.key], true)}</span>
            </button>
          ))}
        </div>
        <div className="row-btns" style={{ marginTop: 8 }}>
          {benched.length > 0 && <button className="btn small" onClick={() => setBenched([])}>Reset</button>}
        </div>
      </div>
    </>
  );
}
