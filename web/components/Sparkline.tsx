import type { Point } from "@/lib/types";

/** Tiny single-series P&L trend for a leaderboard row. */
export default function Sparkline({ points, width = 96, height = 28 }: { points: Point[]; width?: number; height?: number }) {
  if (points.length < 2) return <span className="muted" style={{ fontSize: 12 }}>–</span>;
  const xs = points.map((p) => p.t);
  const vs = points.map((p) => p.v);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const lo = Math.min(0, ...vs), hi = Math.max(0, ...vs);
  const x = (t: number) => 2 + ((t - x0) / (x1 - x0 || 1)) * (width - 8);
  const y = (v: number) => 3 + (1 - (v - lo) / (hi - lo || 1)) * (height - 6);
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
  const last = points[points.length - 1];
  return (
    <svg width={width} height={height} aria-hidden="true" style={{ overflow: "visible", display: "block" }}>
      <line x1={0} x2={width - 4} y1={y(0)} y2={y(0)} stroke="var(--grid)" strokeWidth={1} />
      <path d={d} fill="none" stroke="var(--series-1)" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(last.t)} cy={y(last.v)} r={3} fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth={1.5} />
    </svg>
  );
}
