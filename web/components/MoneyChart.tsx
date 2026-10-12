"use client";

import { useMemo, useState } from "react";
import type { PortfolioPoint } from "@/lib/portfolio";
import type { Point } from "@/lib/types";
import { dollars } from "@/lib/format";
import Avatar from "./Avatar";
import PortfolioChart from "./PortfolioChart";

/** light: the long-run verdict (every bet since the fresh start); bets: how many have finished */
type Member = { key: string; name: string; emoji: string; profit: Point[]; light: string; bets: number };

/** Would benching them for real be smart? Judged on the long run, never on one stretch. */
function verdict(m: Member, change: number): string {
  const first = m.name.split(" ")[0] === "The" ? m.name : m.name.split(" ")[0];
  if (m.light === "yardstick") return `${first} is a yardstick: a simple rule kept around so you can see if the others beat it. Benching would hide that.`;
  if (m.light === "bad") return `${first} has lost over ${m.bets} finished bets, and the numbers say it's probably not bad luck. Benching is reasonable; the button is on their page.`;
  if (m.light === "good") return `${first} is ahead over the long run${change < 0 ? ", so this dip is likely noise" : ""}. Keep them working.`;
  if (m.bets < 30) return `${first} has only ${m.bets} finished bet${m.bets === 1 ? "" : "s"}, so this could easily be luck. Too early to bench.`;
  return `${first}'s results could still be luck either way. Not enough to act on.`;
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
  ms.length <= 2 ? ms.map((m) => m.name).join(" and ") : `${ms.length} employees`;

/**
 * The portfolio chart plus "What if?": tap employees to see how the same period
 * would have gone without their wins and losses, and whether that would really
 * be a reason to bench them (judged on the long run, not this stretch).
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

  const toggle = (k: string) => setBenched((b) => (b.includes(k) ? b.filter((x) => x !== k) : [...b, k]));
  const word = (v: number) => <strong className={v >= 0 ? "up" : "down"}>{v >= 0 ? "▲ up" : "▼ down"} {dollars(Math.abs(v))}</strong>;

  return (
    <>
      <PortfolioChart points={points} alt={alt} />
      <div className="whatif">
        <div className="whatif-head">
          <strong>🔮 What if?</strong>
          <span className="muted small">Tap someone to see {period.toLowerCase()} without them. Just pretend: nobody actually gets benched.</span>
        </div>
        {benched.length ? (
          <>
            <p className="whatif-result">
              Without {names(team.filter((m) => benched.includes(m.key)))}, {period.toLowerCase()} would be {word(altResult)} instead of {word(actual)}.
            </p>
            <ul className="whatif-verdicts">
              {team.filter((m) => benched.includes(m.key)).map((m) => (
                <li key={m.key}><Avatar k={m.key} emoji={m.emoji} size={18} /> <span>{verdict(m, change[m.key] ?? 0)}</span></li>
              ))}
            </ul>
          </>
        ) : (
          <p className="whatif-result muted">Pick someone to see how much they helped or hurt.</p>
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
        <p className="muted small" style={{ margin: "8px 0 0" }}>
          Hindsight is easy: a bad week can be plain bad luck. This shows who helped or hurt, not who will win next. Real benching decisions look at every bet since the start (that&apos;s what the 🟢🟡🔴 lights do), and only once there are enough bets to tell skill from luck.
        </p>
      </div>
    </>
  );
}
