"use client";

import { useState } from "react";
import { axisMoney, dollars } from "@/lib/format";
import { fmtWhen, updatedAgo } from "./PortfolioChart";
import { niceTicks, smoothPath, useWidth } from "./useWidth";

/** One office for the chart: its colour, when it started, and its value after each deposit and finished bet. */
export type OfficeLine = { key: string; label: string; color: string; since: number; worth: [t: number, v: number][] };

/** The office's value at time t (the last change at or before it). */
const worthAt = (pts: [number, number][], t: number) => {
  let v = pts[0][1];
  for (const [ts, w] of pts) { if (ts > t) break; v = w; }
  return v;
};

/**
 * Every office's value over the range picked (11-16, the cockpit), drawn like the office chart: smoothed lines, the
 * scale on the right, the readout above, drag to read any moment. Values move only when a bet is decided (or money
 * goes in or out), like the office headline. The table under it is the legend, so the readout shows all offices
 * together until you drag, then each office at that moment.
 */
export default function OfficesChart({ lines, from, now, checked, height = 240 }: {
  lines: OfficeLine[]; from: number; now: number; checked?: string | null; height?: number;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(360);
  const [hover, setHover] = useState<number | null>(null);
  const pad = { l: 8, r: 52, t: 8, b: 24 };
  const w = width - pad.l - pad.r, h = height - pad.t - pad.b;
  if (!lines.length) return <div className="empty">No offices trading yet.</div>;

  const series = lines.map((l) => {
    const start = Math.max(from, l.since);
    const pts: [number, number][] = [[start, worthAt(l.worth, start)], ...l.worth.filter(([t]) => t > start)];
    pts.push([now, pts[pts.length - 1][1]]);
    return { l, pts };
  });
  const vs = series.flatMap((s) => s.pts.map((p) => p[1]));
  const x0 = Math.min(...series.map((s) => s.pts[0][0])), x1 = now;
  let lo = Math.min(...vs), hi = Math.max(...vs);
  const padY = Math.max((hi - lo) * 0.1, 1);
  lo = Math.max(0, lo - padY);
  hi += padY;
  const ticks = niceTicks(lo, hi, 4).filter((v) => v >= lo && v <= hi);
  const X = (t: number) => pad.l + ((t - x0) / (x1 - x0 || 1)) * w;
  const Y = (v: number) => pad.t + h - ((v - lo) / (hi - lo || 1)) * h;
  const spanDays = (x1 - x0) / 86_400_000;
  const step = ticks.length > 1 ? ticks[1] - ticks[0] : undefined;
  const ht = hover ?? x1;
  // Each office at the moment read (none for an office that hadn't started yet)
  const at = series.map(({ l, pts }) => ({ l, v: ht < pts[0][0] ? null : worthAt(pts, ht) }));
  const total = at.reduce((s, a) => s + (a.v ?? 0), 0);
  const pick = (clientX: number, box: DOMRect) => {
    const frac = Math.max(0, Math.min(1, (clientX - box.left - pad.l) / w));
    setHover(x0 + frac * (x1 - x0));
  };

  return (
    <div className="chart offices-chart" ref={ref}>
      <div className="readout" aria-live="polite">
        <span className="muted">{hover == null ? "Now" : fmtWhen(ht, spanDays)}</span>
        {hover == null
          ? <span><strong>{dollars(total)}</strong> <span className="muted">all offices together</span></span>
          : at.map(({ l, v }) => v == null ? null : (
            <span key={l.key} className="readout-item"><span className="swatch" style={{ background: l.color }} /> <strong>{dollars(v)}</strong></span>
          ))}
        {checked && <span className="readout-checked" suppressHydrationWarning>Updated {updatedAgo(checked)}</span>}
      </div>
      <svg height={height} role="img" aria-label={`Each office's value; ${dollars(total)} together now`} style={{ touchAction: "pan-y" }}
           onPointerMove={(e) => { if (e.pointerType === "mouse" || e.buttons) pick(e.clientX, e.currentTarget.getBoundingClientRect()); }}
           onPointerDown={(e) => { e.currentTarget.setPointerCapture?.(e.pointerId); pick(e.clientX, e.currentTarget.getBoundingClientRect()); }}
           onPointerUp={(e) => { if (e.pointerType !== "mouse") setHover(null); }}
           onPointerCancel={() => setHover(null)}
           onPointerLeave={(e) => { if (e.pointerType === "mouse") setHover(null); }}>
        <defs>
          <clipPath id="oc-plot"><rect x={pad.l} y={pad.t - 4} width={w} height={h + 8} /></clipPath>
        </defs>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={pad.l + w} y1={Y(v)} y2={Y(v)} stroke="var(--grid)" />
            <text x={pad.l + w + 6} y={Y(v)} dy="0.32em" fontSize={11} fill="var(--text-muted)" style={{ fontVariantNumeric: "tabular-nums" }}>
              {axisMoney(v, step)}
            </text>
          </g>
        ))}
        {[x0, x1].map((t, k) => (
          <text key={k} x={X(t)} y={height - 6} textAnchor={k ? "end" : "start"} fontSize={11} fill="var(--text-muted)">
            {k && hover == null ? "now" : fmtWhen(t, spanDays)}
          </text>
        ))}
        <g clipPath="url(#oc-plot)">
          {series.map(({ l, pts }) => (
            <path key={l.key} d={smoothPath(pts.map(([t, v]) => [X(t), Y(v)]))} fill="none" stroke={l.color} strokeWidth={2.25}
                  strokeLinejoin="round" strokeLinecap="round" />
          ))}
        </g>
        {hover != null && <line x1={X(ht)} x2={X(ht)} y1={pad.t} y2={pad.t + h} stroke="var(--axis)" strokeDasharray="3 3" />}
        {at.map(({ l, v }) => v == null ? null : (
          <circle key={l.key} cx={X(ht)} cy={Y(v)} r={4} fill={l.color} stroke="var(--surface-1)" strokeWidth={2} />
        ))}
      </svg>
    </div>
  );
}
