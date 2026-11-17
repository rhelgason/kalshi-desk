"use client";

import { useState } from "react";
import { pct } from "@/lib/format";
import { fmtWhen, updatedAgo } from "./PortfolioChart";
import { niceTicks, smoothPath, useWidth } from "./useWidth";

/** One office for the chart: its colour, money put in, start, and running profit after each finished bet. */
export type ReturnLine = { key: string; label: string; color: string; putIn: number; since: number; pnl: [t: number, sum: number][] };

/** Profit so far at time t (the last finished bet at or before it). */
const sumAt = (l: ReturnLine, t: number) => {
  let v = 0;
  for (const [ts, s] of l.pnl) { if (ts > t) break; v = s; }
  return v;
};

/**
 * Each office's return in % over the range picked (11-16, the cockpit), drawn like the office chart: smoothed lines,
 * the scale on the right, the readout above, drag to read any moment. Offices of different sizes and ages share
 * one scale the standard way (a stock site's "compare"): each line starts at 0% where the range starts (or where
 * the office started, if later), and measures profit since then over what the office was worth then. The table under
 * it is the legend, so the readout shows all offices together until you drag, then each office at that moment.
 */
export default function ReturnsChart({ lines, from, now, checked, height = 240 }: {
  lines: ReturnLine[]; from: number; now: number; checked?: string | null; height?: number;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(360);
  const [hover, setHover] = useState<number | null>(null);
  const pad = { l: 8, r: 52, t: 8, b: 24 };
  const w = width - pad.l - pad.r, h = height - pad.t - pad.b;

  // All offices together over the range: every office's profit since its start over what they were all worth then
  let made = 0, worth = 0;
  const series = lines.map((l) => {
    const start = Math.max(from, l.since), s0 = sumAt(l, start), base = (l.putIn + s0) || 1;
    made += (l.pnl[l.pnl.length - 1]?.[1] ?? 0) - s0;
    worth += base;
    const pts: [number, number][] = [[start, 0], ...l.pnl.filter(([t]) => t > start).map(([t, s]) => [t, (s - s0) / base] as [number, number])];
    pts.push([now, pts[pts.length - 1][1]]);
    return { l, pts };
  });
  const together = worth ? made / worth : 0;
  const vs = series.flatMap((s) => s.pts.map((p) => p[1]));
  if (!lines.length) return <div className="empty">No offices trading yet.</div>;
  const x0 = Math.min(...series.map((s) => s.pts[0][0])), x1 = now;
  let lo = Math.min(0, ...vs), hi = Math.max(0, ...vs);
  const padY = Math.max((hi - lo) * 0.15, 0.002);
  lo -= padY;
  hi += padY;
  const ticks = niceTicks(lo, hi, 4).filter((v) => v >= lo && v <= hi);
  const X = (t: number) => pad.l + ((t - x0) / (x1 - x0 || 1)) * w;
  const Y = (v: number) => pad.t + h - ((v - lo) / (hi - lo || 1)) * h;
  const spanDays = (x1 - x0) / 86_400_000;
  const step = ticks.length > 1 ? ticks[1] - ticks[0] : 0.01;
  // Each line's value at the moment read (none for an office that hadn't started yet)
  const valueAt = (pts: [number, number][], t: number) => {
    if (t < pts[0][0]) return null;
    let v = pts[0][1];
    for (const p of pts) { if (p[0] > t) break; v = p[1]; }
    return v;
  };
  const ht = hover ?? x1;
  const pick = (clientX: number, box: DOMRect) => {
    const frac = Math.max(0, Math.min(1, (clientX - box.left - pad.l) / w));
    setHover(x0 + frac * (x1 - x0));
  };

  return (
    <div className="chart returns-chart" ref={ref}>
      <div className="readout" aria-live="polite">
        <span className="muted">{hover == null ? "Now" : fmtWhen(ht, spanDays)}</span>
        {hover == null
          ? <span><strong className={together >= 0 ? "up" : "down"}>{pct(together, true, 1)}</strong> <span className="muted">all offices together</span></span>
          : series.map(({ l, pts }) => {
            const v = valueAt(pts, ht);
            return v == null ? null : (
              <span key={l.key} className="readout-item">
                <span className="swatch" style={{ background: l.color }} /> <strong className={v >= 0 ? "up" : "down"}>{pct(v, true, 1)}</strong>
              </span>
            );
          })}
        {checked && <span className="readout-checked" suppressHydrationWarning>Updated {updatedAgo(checked)}</span>}
      </div>
      <svg height={height} role="img" aria-label="Each office's return over the range" style={{ touchAction: "pan-y" }}
           onPointerMove={(e) => { if (e.pointerType === "mouse" || e.buttons) pick(e.clientX, e.currentTarget.getBoundingClientRect()); }}
           onPointerDown={(e) => { e.currentTarget.setPointerCapture?.(e.pointerId); pick(e.clientX, e.currentTarget.getBoundingClientRect()); }}
           onPointerUp={(e) => { if (e.pointerType !== "mouse") setHover(null); }}
           onPointerCancel={() => setHover(null)}
           onPointerLeave={(e) => { if (e.pointerType === "mouse") setHover(null); }}>
        <defs>
          <clipPath id="rc-plot"><rect x={pad.l} y={pad.t - 4} width={w} height={h + 8} /></clipPath>
        </defs>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={pad.l + w} y1={Y(v)} y2={Y(v)} stroke="var(--grid)" />
            <text x={pad.l + w + 6} y={Y(v)} dy="0.32em" fontSize={11} fill="var(--text-muted)" style={{ fontVariantNumeric: "tabular-nums" }}>
              {pct(v, v !== 0, step < 0.01 ? 1 : 0)}
            </text>
          </g>
        ))}
        <line x1={pad.l} x2={pad.l + w} y1={Y(0)} y2={Y(0)} stroke="var(--axis)" strokeDasharray="4 4" />
        {[x0, x1].map((t, k) => (
          <text key={k} x={X(t)} y={height - 6} textAnchor={k ? "end" : "start"} fontSize={11} fill="var(--text-muted)">
            {k && hover == null ? "now" : fmtWhen(t, spanDays)}
          </text>
        ))}
        <g clipPath="url(#rc-plot)">
          {series.map(({ l, pts }) => (
            <path key={l.key} d={smoothPath(pts.map(([t, v]) => [X(t), Y(v)]))} fill="none" stroke={l.color} strokeWidth={2.25}
                  strokeLinejoin="round" strokeLinecap="round" />
          ))}
        </g>
        {hover != null && <line x1={X(ht)} x2={X(ht)} y1={pad.t} y2={pad.t + h} stroke="var(--axis)" strokeDasharray="3 3" />}
        {series.map(({ l, pts }) => {
          const v = valueAt(pts, ht);
          return v == null ? null : <circle key={l.key} cx={X(Math.min(ht, pts[pts.length - 1][0]))} cy={Y(v)} r={4} fill={l.color}
                                             stroke="var(--surface-1)" strokeWidth={2} />;
        })}
      </svg>
    </div>
  );
}
