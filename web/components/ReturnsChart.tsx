"use client";

import { pct } from "@/lib/format";
import type { Point } from "@/lib/types";
import { niceTicks, useWidth } from "./useWidth";

export type ReturnLine = { key: string; label: string; points: Point[]; mine?: boolean };

const COLORS = ["var(--series-1)", "var(--series-2)", "#8b5cf6", "#14b8a6", "#ec4899"];

/**
 * Each office's return since it started, in % (11-16, the cockpit): offices of different sizes on one scale.
 * Steps at each finished bet, like the office chart.
 */
export default function ReturnsChart({ lines, height = 220 }: { lines: ReturnLine[]; height?: number }) {
  const [ref, width] = useWidth<HTMLDivElement>(640);
  const all = lines.flatMap((l) => l.points);
  if (all.length < 2) return <div className="empty">Not enough finished bets to draw yet.</div>;
  const t0 = Math.min(...all.map((p) => p.t)), t1 = Math.max(Date.now(), ...all.map((p) => p.t));
  const ticks = niceTicks(Math.min(0, ...all.map((p) => p.v)), Math.max(0, ...all.map((p) => p.v)), 4);
  const lo = ticks[0], hi = ticks[ticks.length - 1];
  const pad = { l: 44, r: 8, t: 8, b: 20 };
  const x = (t: number) => pad.l + ((t - t0) / (t1 - t0 || 1)) * (width - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - (v - lo) / (hi - lo || 1)) * (height - pad.t - pad.b);
  const path = (pts: Point[]) => {
    if (!pts.length) return "";
    let d = `M${x(pts[0].t)},${y(pts[0].v)}`;
    for (let i = 1; i < pts.length; i++) d += `H${x(pts[i].t)}V${y(pts[i].v)}`;
    return d + `H${x(t1)}`;
  };
  const day = (t: number) => new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return (
    <div ref={ref} className="returns-chart">
      <svg width={width} height={height} role="img" aria-label="Return since each office started">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={width - pad.r} y1={y(v)} y2={y(v)} stroke={v === 0 ? "var(--axis)" : "var(--grid)"} />
            <text x={pad.l - 6} y={y(v) + 4} textAnchor="end" fontSize="11" fill="var(--text-muted)">{pct(v, v !== 0, 0)}</text>
          </g>
        ))}
        <text x={pad.l} y={height - 4} fontSize="11" fill="var(--text-muted)">{day(t0)}</text>
        <text x={width - pad.r} y={height - 4} fontSize="11" fill="var(--text-muted)" textAnchor="end">{day(t1)}</text>
        {lines.map((l, i) => (
          <path key={l.key} d={path(l.points)} fill="none" stroke={COLORS[i % COLORS.length]} strokeWidth={l.mine ? 2.5 : 1.75} />
        ))}
      </svg>
      <div className="legend">
        {lines.map((l, i) => (
          <span key={l.key} className="legend-item">
            <span className="legend-swatch" style={{ background: COLORS[i % COLORS.length] }} />
            {l.label} {l.points.length > 0 && <strong>{pct(l.points[l.points.length - 1].v, true, 1)}</strong>}
          </span>
        ))}
      </div>
    </div>
  );
}
