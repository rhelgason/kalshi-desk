"use client";

import { useMemo, useState } from "react";
import type { PortfolioPoint } from "@/lib/portfolio";
import type { MoneyMove } from "@/lib/types";
import { dollars, shortName } from "@/lib/format";
import Avatar from "./Avatar";
import PortfolioChart from "./PortfolioChart";

/** One pool member for the what-if: their running profit from finished bets, as [time, total] steps. */
export type WhatIfMember = { key: string; name: string; emoji: string; steps: [number, number][] };

const totalAt = (steps: [number, number][], t: number) => {
  let v = 0;
  for (const [s, x] of steps) { if (s > t) break; v = x; }
  return v;
};

/**
 * The office chart with a light "What if…" under it (11-16): closed, it's one small link. Open, three switches that
 * combine: a different amount put in, a different bet size, and leaving employees out. The chart draws the result
 * as a second line. Rough on purpose: profit scales with the money and the bet size, ignoring compounding and caps.
 */
export default function HeroChart({ points, marks, checked, members, putIn, betPct }: {
  points: PortfolioPoint[]; marks?: MoneyMove[]; checked?: string | null;
  members: WhatIfMember[]; putIn: number; betPct: number;
}) {
  const [open, setOpen] = useState(false);
  const [money, setMoney] = useState<number | null>(null);
  const [bet, setBet] = useState<number | null>(null);
  const [out, setOut] = useState<string[]>([]);
  const k = money != null && putIn > 0 ? money / putIn : 1;
  const b = bet != null && betPct > 0 ? bet / 100 / betPct : 1;
  const on = money != null || bet != null || out.length > 0;

  const alt = useMemo(() => {
    if (!on) return null;
    const gone = members.filter((m) => out.includes(m.key));
    return points.map((p) => {
      const removed = gone.reduce((s, m) => s + totalAt(m.steps, p.t), 0);
      return k * (p.putIn + (p.worth - p.putIn - removed) * b);
    });
  }, [on, members, out, points, k, b]);

  const reset = () => { setMoney(null); setBet(null); setOut([]); setOpen(false); };
  const toggleOut = (key: string) => setOut((o) => (o.includes(key) ? o.filter((x) => x !== key) : [...o, key]));
  const last = alt?.[alt.length - 1];
  const lastPut = (points[points.length - 1]?.putIn ?? putIn) * k;

  return (
    <>
      <PortfolioChart points={points} marks={marks} checked={checked} alt={alt} altScale={k} />
      <div className="whatif-bar">
        {!open ? (
          <button type="button" className="link-btn" onClick={() => setOpen(true)}>What if…</button>
        ) : (
          <div className="whatif-panel">
            <div className="whatif-row">
              <button type="button" className="chip" aria-pressed={money != null}
                      onClick={() => setMoney(money == null ? Math.max(100, Math.round(putIn * 2 / 100) * 100) : null)}>With</button>
              <label className="whatif-input">$<input type="number" inputMode="numeric" min={1} value={money ?? Math.round(putIn)}
                onChange={(e) => setMoney(Math.max(1, Number(e.target.value) || 0))} /></label>
              <span className="muted">put in</span>
            </div>
            <div className="whatif-row">
              <button type="button" className="chip" aria-pressed={bet != null}
                      onClick={() => setBet(bet == null ? Math.round(betPct * 200) : null)}>Every bet</button>
              <label className="whatif-input"><input type="number" inputMode="decimal" min={0.5} max={25} step={0.5}
                value={bet ?? +(betPct * 100).toFixed(1)} onChange={(e) => setBet(Math.max(0.5, Math.min(25, Number(e.target.value) || 0)))} />%</label>
              <span className="muted">of the pool</span>
            </div>
            <div className="whatif-row whatif-people">
              <span className="muted">Without</span>
              {members.map((m) => (
                <button key={m.key} type="button" className="chip person-chip" aria-pressed={out.includes(m.key)} onClick={() => toggleOut(m.key)}
                        title={m.name}>
                  <Avatar k={m.key} emoji={m.emoji} size={18} /> {shortName(m.name)}
                </button>
              ))}
            </div>
            <div className="whatif-foot">
              {last != null
                ? <span>That would be <strong>{dollars(last)}</strong>, <span className={last - lastPut >= 0 ? "up" : "down"}>{dollars(last - lastPut, true)}</span> on {dollars(lastPut)}</span>
                : <span className="muted">Pick one or more.</span>}
              <button type="button" className="link-btn" onClick={reset}>Close</button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
