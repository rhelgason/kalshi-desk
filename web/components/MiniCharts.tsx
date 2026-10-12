"use client";

import { useState } from "react";
import { dollars } from "@/lib/format";
import { useWidth } from "./useWidth";

/** Bets won vs. lost as a donut, with the win rate in the middle. */
export function WinDonut({ wins, losses, open }: { wins: number; losses: number; open: number }) {
  const total = wins + losses;
  if (!total) return <div className="empty">No finished bets yet.</div>;
  const r = 52, c = 2 * Math.PI * r;
  const gap = total > 1 && wins && losses ? 3 : 0; // a small surface gap between the two slices
  const winLen = (wins / total) * c;
  return (
    <div className="donut-wrap">
      <svg width={140} height={140} viewBox="0 0 140 140" role="img" aria-label={`${wins} won, ${losses} lost`}>
        <g transform="rotate(-90 70 70)" fill="none" strokeWidth={18}>
          <circle cx={70} cy={70} r={r} stroke="var(--down)" strokeDasharray={`${Math.max(0, c - winLen - gap)} ${c}`} strokeDashoffset={-(winLen + gap / 2)} />
          {wins > 0 && <circle cx={70} cy={70} r={r} stroke="var(--up)" strokeDasharray={`${Math.max(0, winLen - gap)} ${c}`} strokeDashoffset={-gap / 2} />}
        </g>
        <text x={70} y={68} textAnchor="middle" fontSize={24} fontWeight={650} fill="var(--text-primary)">{Math.round((wins / total) * 100)}%</text>
        <text x={70} y={88} textAnchor="middle" fontSize={12} fill="var(--text-muted)">won</text>
      </svg>
      <ul className="donut-legend">
        <li><span className="swatch" style={{ background: "var(--up)" }} /> Won <strong>{wins.toLocaleString()}</strong></li>
        <li><span className="swatch" style={{ background: "var(--down)" }} /> Lost <strong>{losses.toLocaleString()}</strong></li>
        <li className="muted">Still open: {open}</li>
      </ul>
    </div>
  );
}

/** Money made on winning bets vs. lost on losing ones. */
export function MoneySplit({ won, lost, fees }: { won: number; lost: number; fees: number }) {
  const max = Math.max(won, -lost, 0.01);
  const bar = (v: number, color: string) => (
    <div className="split-track"><div className="split-bar" style={{ width: `${(Math.abs(v) / max) * 100}%`, background: color }} /></div>
  );
  return (
    <div className="split">
      <div className="split-row"><span>Made on winning bets</span><strong className="up">{dollars(won, true)}</strong></div>
      {bar(won, "var(--up)")}
      <div className="split-row"><span>Lost on losing bets</span><strong className="down">{dollars(lost, true)}</strong></div>
      {bar(lost, "var(--down)")}
      <div className="split-row" style={{ marginTop: 6 }}><span>Overall</span><strong className={won + lost >= 0 ? "up" : "down"}>{dollars(won + lost, true)}</strong></div>
      <p className="muted small" style={{ margin: "6px 0 0" }}>Kalshi took {dollars(fees)} of that in fees.</p>
    </div>
  );
}

/** Profit or loss for each day, as bars above or below $0. Tap or hover a bar for details. */
export function DailyBars({ days }: { days: { day: string; pnl: number; bets: number }[] }) {
  const [ref, width] = useWidth<HTMLDivElement>(320);
  const [hot, setHot] = useState<number | null>(null);
  if (!days.length) return <div className="empty">No finished bets yet.</div>;
  const shown = days.slice(-30);
  const height = 140, pad = { t: 8, b: 20 };
  const max = Math.max(...shown.map((d) => Math.abs(d.pnl)), 0.01);
  const anyNeg = shown.some((d) => d.pnl < 0), anyPos = shown.some((d) => d.pnl > 0);
  const h = height - pad.t - pad.b;
  // Baseline in the middle only when there are both good and bad days
  const zero = pad.t + (anyNeg && anyPos ? h / 2 : anyNeg ? 0 : h);
  const scale = (anyNeg && anyPos ? h / 2 : h) / max;
  const slot = width / shown.length;
  const bw = Math.max(4, Math.min(40, slot - 4));
  const label = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const cur = shown[hot ?? shown.length - 1];
  return (
    <div className="chart" ref={ref}>
      <div className="readout">
        <span className="muted">{hot == null ? "Latest day" : label(cur.day)}</span>
        <strong className={cur.pnl >= 0 ? "up" : "down"}>{dollars(cur.pnl, true)}</strong>
        <span className="muted">{cur.bets} bets finished</span>
      </div>
      <svg height={height} role="img" aria-label="Profit or loss per day" onPointerLeave={(e) => { if (e.pointerType === "mouse") setHot(null); }}>
        <line x1={0} x2={width} y1={zero} y2={zero} stroke="var(--axis)" />
        {shown.map((d, i) => {
          const len = Math.max(1, Math.abs(d.pnl) * scale);
          const x = i * slot + (slot - bw) / 2;
          return (
            <g key={d.day} onPointerEnter={() => setHot(i)} onPointerDown={() => setHot(i)}>
              <rect x={i * slot} y={pad.t} width={slot} height={h} fill="transparent" />
              <rect x={x} y={d.pnl >= 0 ? zero - len : zero} width={bw} height={len} rx={Math.min(4, bw / 2)}
                fill={d.pnl >= 0 ? "var(--up)" : "var(--down)"} opacity={hot == null || hot === i ? 1 : 0.45} />
            </g>
          );
        })}
        <text x={0} y={height - 4} fontSize={11} fill="var(--text-muted)">{label(shown[0].day)}</text>
        {shown.length > 1 && <text x={width} y={height - 4} fontSize={11} textAnchor="end" fill="var(--text-muted)">{label(shown[shown.length - 1].day)}</text>}
      </svg>
    </div>
  );
}
