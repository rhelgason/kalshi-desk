"use client";

import { useId, useState } from "react";
import { dollars, pct } from "@/lib/format";
import { fmtWhen } from "./PortfolioChart";
import { useWidth } from "./useWidth";
import SubmitButton from "./SubmitButton";

/** One moment of an office: what it was worth (v) and what had been put in by then (p). */
export type OfficePoint = { t: number; v: number; p: number };

export type OfficeCard = {
  key: string; name: string; color: string; paused: boolean; since: number;
  worth: number; putIn: number;
  /** profit over the range picked above */
  period: number;
  points: OfficePoint[];
  /** deposits and withdrawals in the range, marked on the put-in line */
  moves: { t: number; amount: number }[];
  visit?: () => Promise<void>;
};

const H = 96;

/** Read the line exactly as drawn (straight between points), so the dot always sits on it. */
function at(pts: OfficePoint[], t: number): OfficePoint {
  if (t <= pts[0].t) return pts[0];
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i];
    if (t <= b.t) {
      const f = b.t === a.t ? 1 : (t - a.t) / (b.t - a.t);
      return { t, v: a.v + (b.v - a.v) * f, p: t < b.t ? a.p : b.p };
    }
  }
  return pts[pts.length - 1];
}

/**
 * One office as a player card (11-22, replacing the shared % chart): money now, money put in, how much each $1 has
 * grown, and its own little chart (worth as a glowing line over a dashed "put in" step, each on its own scale so a
 * $100 office reads as clearly as a $1,000 one). Drag a chart to read any moment. A friend sees % only, no dollars.
 */
function Card({ c, money, period }: { c: OfficeCard; money: boolean; period: string }) {
  const [ref, width] = useWidth<HTMLDivElement>(260);
  const [hover, setHover] = useState<number | null>(null);
  const id = useId().replace(/:/g, "");
  // Before the first money went in there's nothing to draw (a new office starts at its first deposit)
  const pts = c.points.filter((p) => p.p >= 1);
  const ret = c.putIn ? (c.worth - c.putIn) / c.putIn : 0;
  const up = c.worth >= c.putIn;

  const w = Math.max(80, width), pad = { t: 12, b: 6, l: 4, r: 14 };
  const x0 = pts[0]?.t ?? c.since, x1 = pts[pts.length - 1]?.t ?? Date.now();
  const vs = pts.flatMap((p) => [p.v, p.p]);
  let lo = Math.min(...vs), hi = Math.max(...vs);
  const room = Math.max((hi - lo) * 0.12, hi * 0.01, 1);
  lo -= room; hi += room;
  const X = (t: number) => pad.l + ((t - x0) / (x1 - x0 || 1)) * (w - pad.l - pad.r);
  const Y = (v: number) => pad.t + (1 - (v - lo) / (hi - lo || 1)) * (H - pad.t - pad.b);
  const line = pts.map((p, i) => `${i ? "L" : "M"}${X(p.t).toFixed(1)},${Y(p.v).toFixed(1)}`).join("");
  const area = pts.length ? `${line}L${X(x1).toFixed(1)},${H}L${X(x0).toFixed(1)},${H}Z` : "";
  // Put in: a step (it only changes when money is added or taken out)
  const step = pts.map((p, i) => (i ? `H${X(p.t).toFixed(1)}V${Y(p.p).toFixed(1)}` : `M${X(p.t).toFixed(1)},${Y(p.p).toFixed(1)}`)).join("");

  const read = hover != null && pts.length > 1 ? at(pts, hover) : null;
  const end = pts[pts.length - 1];
  const pick = (clientX: number, box: DOMRect) => {
    const f = Math.max(0, Math.min(1, (clientX - box.left - pad.l) / (w - pad.l - pad.r)));
    setHover(x0 + f * (x1 - x0));
  };
  const span = (x1 - x0) / 86_400_000;

  return (
    <div className={`office-card ${up ? "is-up" : "is-down"}`} style={{ "--office": c.color } as React.CSSProperties}>
      <div className="office-card-head">
        <span className="office-card-badge" aria-hidden>{c.name.slice(0, 1).toUpperCase()}</span>
        <strong className="office-card-name">{c.name}</strong>
        {c.paused && <span className="badge paused-badge">Paused</span>}
      </div>
      <div className="office-card-money">
        {read
          ? <>
              <span className="office-card-big">{money ? dollars(read.v) : pct(read.p ? (read.v - read.p) / read.p : 0, true, 1)}</span>
              <span className="muted small">{fmtWhen(read.t, span)}{money && <> · put in {dollars(read.p)}</>}</span>
            </>
          : <>
              <span className="office-card-bigrow">
                <span className="office-card-big">{money ? dollars(c.worth) : pct(ret, true, 1)}</span>
                {money && <span className={`office-card-growth ${up ? "up" : "down"}`}>{pct(ret, true, ret > -0.1 && ret < 0.1 ? 1 : 0)}</span>}
              </span>
              <span className="muted small office-card-sub">
                <span>{money ? <>put in {dollars(c.putIn)}</> : "since they joined"}</span>
                <span><span className={`nowrap ${c.period >= 0 ? "up" : "down"}`}>
                  {money ? dollars(c.period, true) : pct(c.putIn ? c.period / c.putIn : 0, true, 1)}
                </span> {period.toLowerCase()}</span>
              </span>
            </>}
      </div>
      <div className="office-card-chart" ref={ref}>
        {pts.length > 1 ? (
          <svg width={w} height={H} role="img" aria-label={`${c.name}: worth over time against money put in`} style={{ touchAction: "pan-y" }}
               onPointerMove={(e) => { if (e.pointerType === "mouse" || e.buttons) pick(e.clientX, e.currentTarget.getBoundingClientRect()); }}
               onPointerDown={(e) => { e.currentTarget.setPointerCapture?.(e.pointerId); pick(e.clientX, e.currentTarget.getBoundingClientRect()); }}
               onPointerUp={(e) => { if (e.pointerType !== "mouse") setHover(null); }}
               onPointerCancel={() => setHover(null)}
               onPointerLeave={(e) => { if (e.pointerType === "mouse") setHover(null); }}>
            <defs>
              <linearGradient id={`${id}-fill`} x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor={c.color} stopOpacity={0.35} />
                <stop offset="100%" stopColor={c.color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <path d={area} fill={`url(#${id}-fill)`} />
            <path d={step} fill="none" stroke="var(--text-muted)" strokeWidth={1.25} strokeDasharray="4 4" />
            {c.moves.filter((m) => m.t >= x0 && m.t <= x1).map((m) => (
              <g key={m.t} className="office-card-coin">
                <circle cx={X(m.t)} cy={Y(at(pts, m.t + 1).p)} r={5} />
                <title>{money ? `${dollars(m.amount, true)} ${m.amount >= 0 ? "added" : "taken out"}` : m.amount >= 0 ? "Money added" : "Money taken out"}</title>
              </g>
            ))}
            <path d={line} fill="none" stroke={c.color} strokeWidth={2.25} strokeLinejoin="round" strokeLinecap="round" className="office-card-line" />
            {read
              ? <>
                  <line x1={X(read.t)} x2={X(read.t)} y1={0} y2={H} stroke="var(--axis)" strokeDasharray="3 3" />
                  <circle cx={X(read.t)} cy={Y(read.v)} r={4} fill={c.color} stroke="var(--surface-1)" strokeWidth={2} />
                </>
              : <>
                  <circle cx={X(end.t)} cy={Y(end.v)} r={7} fill={c.color} className="office-card-pulse" />
                  <circle cx={X(end.t)} cy={Y(end.v)} r={3.5} fill={c.color} stroke="var(--surface-1)" strokeWidth={1.5} />
                </>}
          </svg>
        ) : <div className="empty small">Not enough history yet.</div>}
      </div>
      {c.visit && (
        <form action={c.visit} className="office-card-open"><SubmitButton className="link-btn small">Open office →</SubmitButton></form>
      )}
    </div>
  );
}

/** Every office as a card, biggest first for the manager (most grown first for a friend, who sees no dollars). */
export default function OfficeCards({ cards, money, period }: { cards: OfficeCard[]; money: boolean; period: string }) {
  const growth = (c: OfficeCard) => (c.putIn ? (c.worth - c.putIn) / c.putIn : 0);
  const sorted = [...cards].sort((a, b) => (money ? b.worth - a.worth : growth(b) - growth(a)));
  if (!sorted.length) return <div className="empty">No offices trading yet.</div>;
  return <div className="office-cards">{sorted.map((c) => <Card key={c.key} c={c} money={money} period={period} />)}</div>;
}
