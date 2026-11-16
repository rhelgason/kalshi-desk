"use client";

import { useMemo, useState } from "react";
import type { PortfolioPoint } from "@/lib/portfolio";
import type { MoneyMove } from "@/lib/types";
import { dollars, shortName } from "@/lib/format";
import Avatar from "./Avatar";
import PortfolioChart from "./PortfolioChart";

/** A pool member for the what-if: who, and what they made over the chart's range (shown on their chip). */
export type WhatIfMember = { key: string; name: string; emoji: string; inRange: number };
/** One finished bet, as the replay needs it: when, whose, and what it made. */
export type WhatIfBet = [t: number, strategy: string, pnl: number];

/** Typing into a number box: digits (and one dot), no leading zero, and empty means 0. */
const tidy = (v: string, decimals: boolean) => {
  let s = v.replace(decimals ? /[^\d.]/g : /\D/g, "");
  if (decimals) s = s.replace(/(\..*)\./g, "$1");
  s = s.replace(/^0+(?=\d)/, "");
  return s === "" || s === "." ? "0" : s;
};

/**
 * The office chart with a light "What if…" under it (11-16). Three switches that combine: a different amount put
 * in, a different bet size, and leaving employees out. Typing in a box turns its switch on.
 *
 * The what-if replays the season's finished bets in order. Bets are a share of the pool, so each bet scales with how
 * big the what-if pool is at that moment compared with the real one, times the bet-size change; leaving someone out
 * drops their bets, which also shrinks or grows everyone else's later bets. It assumes every bet would still fill at
 * its new size, which gets less true as bets grow (bigger bids wait longer, and the desk's caps on open bets bite).
 */
export default function HeroChart({ points, marks, checked, members, bets, putIn, betPct, period }: {
  points: PortfolioPoint[]; marks?: MoneyMove[]; checked?: string | null;
  members: WhatIfMember[]; bets: WhatIfBet[]; putIn: number; betPct: number; period: string;
}) {
  const [open, setOpen] = useState(false);
  const [moneyOn, setMoneyOn] = useState(false);
  const [money, setMoney] = useState(String(Math.round(putIn)));
  const [betOn, setBetOn] = useState(false);
  const [bet, setBet] = useState(String(+(betPct * 100).toFixed(2)));
  const [out, setOut] = useState<string[]>([]);
  const m = Number(money), b = Number(bet);
  const k = moneyOn && m > 0 && putIn > 0 ? m / putIn : 1;
  const ratio = betOn && b > 0 && betPct > 0 ? b / 100 / betPct : 1;
  const on = (moneyOn && m > 0) || (betOn && b > 0) || out.length > 0;

  // Replay the season: the real pool and the what-if pool side by side, deposits scaled like the money put in
  const alt = useMemo(() => {
    if (!on) return null;
    const moved = (marks ?? []).reduce((s, x) => s + x.amount, 0);
    let real = putIn - moved, what = real * k;
    const events: [number, number, string | null, number][] = [
      ...(marks ?? []).map((x) => [x.t, 0, null, x.amount] as [number, number, string | null, number]),
      ...bets.map(([t, s, p]) => [t, 1, s, p] as [number, number, string | null, number]),
    ].sort((a, c) => a[0] - c[0] || a[1] - c[1]);
    const timeline: [number, number][] = [];
    for (const [t, kind, who, v] of events) {
      if (kind === 0) { real += v; what += v * k; }
      else {
        if (!out.includes(who!) && real > 0) what += v * (what / real) * ratio;
        real += v;
      }
      timeline.push([t, Math.max(0, what)]);
    }
    let i = 0, last = (putIn - moved) * k;
    return points.map((p) => {
      while (i < timeline.length && timeline[i][0] <= p.t) last = timeline[i++][1];
      return last;
    });
  }, [on, marks, bets, points, putIn, k, ratio, out]);

  const reset = () => { setMoneyOn(false); setBetOn(false); setOut([]); setOpen(false); };
  const toggleOut = (key: string) => setOut((o) => (o.includes(key) ? o.filter((x) => x !== key) : [...o, key]));
  const end = alt?.[alt.length - 1];
  const endPut = (points[points.length - 1]?.putIn ?? putIn) * k;
  const nudge = (v: string, by: number, min: number) => String(Math.max(min, Math.round((Number(v) + by) * 100) / 100));

  return (
    <>
      <PortfolioChart points={points} marks={marks} checked={checked} alt={alt} altScale={k} />
      <div className="whatif-bar">
        {!open ? (
          <button type="button" className="btn small whatif-open" onClick={() => setOpen(true)}>🔮 What if…</button>
        ) : (
          <div className="whatif-panel">
            <div className="whatif-row">
              <button type="button" className="chip" aria-pressed={moneyOn} onClick={() => setMoneyOn(!moneyOn)}>With</button>
              <label className="whatif-input">$
                <input type="text" inputMode="numeric" value={money} onFocus={(e) => e.target.select()}
                       onChange={(e) => { setMoney(tidy(e.target.value, false)); setMoneyOn(true); }}
                       onKeyDown={(e) => {
                         if (e.key === "ArrowUp" || e.key === "ArrowDown") {
                           e.preventDefault(); setMoney(nudge(money, e.key === "ArrowUp" ? 10 : -10, 0)); setMoneyOn(true);
                         }
                       }} />
              </label>
              <span className="muted">put in</span>
            </div>
            <div className="whatif-row">
              <button type="button" className="chip" aria-pressed={betOn} onClick={() => setBetOn(!betOn)}>Every bet</button>
              <label className="whatif-input">
                <input type="text" inputMode="decimal" value={bet} onFocus={(e) => e.target.select()}
                       onChange={(e) => { setBet(tidy(e.target.value, true)); setBetOn(true); }}
                       onKeyDown={(e) => {
                         if (e.key === "ArrowUp" || e.key === "ArrowDown") {
                           e.preventDefault(); setBet(nudge(bet, e.key === "ArrowUp" ? 0.5 : -0.5, 0)); setBetOn(true);
                         }
                       }} />%
              </label>
              <span className="muted">of the pool (now {+(betPct * 100).toFixed(2)}%)</span>
            </div>
            <div className="whatif-row whatif-people">
              <span className="muted">Without</span>
              {members.map((p) => (
                <button key={p.key} type="button" className="chip person-chip" aria-pressed={out.includes(p.key)} onClick={() => toggleOut(p.key)}
                        title={`${p.name}: ${dollars(p.inRange, true)} ${period.toLowerCase()}`}>
                  <Avatar k={p.key} emoji={p.emoji} size={18} /> {shortName(p.name)}
                  <span className={p.inRange >= 0 ? "up" : "down"}>{dollars(p.inRange, true)}</span>
                </button>
              ))}
            </div>
            <div className="whatif-foot">
              {end != null
                ? <span>That would be <strong>{dollars(end)}</strong>, <span className={end - endPut >= 0 ? "up" : "down"}>{dollars(end - endPut, true)}</span> on {dollars(endPut)} put in</span>
                : <span className="muted">Pick one or more.</span>}
              <button type="button" className="link-btn" onClick={reset}>Close</button>
            </div>
            {betOn && ratio > 1.5 && (
              <p className="muted small whatif-warn">
                A best case: bigger bets wait longer to fill and run into the desk&apos;s limit on money out at once, so
                fewer of them would happen.
              </p>
            )}
          </div>
        )}
      </div>
    </>
  );
}
