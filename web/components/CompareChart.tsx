"use client";

import { useMemo, useState } from "react";
import type { Point, Series } from "@/lib/types";
import { axisMoney, dollars, pct } from "@/lib/format";
import Avatar from "./Avatar";
import { niceTicks, useWidth } from "./useWidth";

const valueAt = (pts: Point[], t: number) => {
  let v: number | null = null;
  for (const p of pts) {
    if (p.t > t) break;
    v = p.v;
  }
  return v;
};

type Row = { s: Series; v: number; rank: number; change: number };

/**
 * One employee's profit over time (blue) against the whole team (gray).
 * Point at (or tap) any line to light it up in orange and see how that
 * teammate was doing at that moment.
 */
export default function CompareChart({ series, focus, given, height = 240 }: {
  series: Series[];
  focus: string;
  /** money each employee was given, for "% of their money" */
  given: Record<string, number>;
  height?: number;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(360);
  const [hover, setHover] = useState<{ t: number; key: string | null } | null>(null);
  const me = series.find((s) => s.key === focus);

  const pad = { l: 8, r: 52, t: 8, b: 24 };
  const w = width - pad.l - pad.r;
  const h = height - pad.t - pad.b;

  const geo = useMemo(() => {
    const pts = series.flatMap((s) => s.points);
    if (!me || me.points.length < 2) return null;
    const x0 = Math.min(...pts.map((p) => p.t)), x1 = Math.max(...pts.map((p) => p.t));
    const lo = Math.min(0, ...pts.map((p) => p.v)), hi = Math.max(0, ...pts.map((p) => p.v));
    const ticks = niceTicks(lo, hi, 4);
    const y0 = ticks[0], y1 = ticks[ticks.length - 1];
    return {
      x0, x1, ticks,
      x: (t: number) => pad.l + (x1 === x0 ? w / 2 : ((t - x0) / (x1 - x0)) * w),
      y: (v: number) => pad.t + h - ((v - y0) / (y1 - y0 || 1)) * h,
    };
  }, [series, me, w, h, pad.l, pad.t]);

  if (!geo || !me) return <div className="empty">Not enough history yet for this range.</div>;
  const { x0, x1, ticks, x, y } = geo;
  const spanDays = (x1 - x0) / 86_400_000;
  const when = (t: number) =>
    new Date(t).toLocaleString("en-US", spanDays > 2 ? { month: "short", day: "numeric", hour: "numeric" } : { weekday: "short", hour: "numeric", minute: "2-digit" });
  const path = (s: Series) => s.points.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join("");

  // Everyone's standing at the chosen moment
  const t = hover?.t ?? x1;
  const rows: Row[] = series
    .map((s) => ({ s, v: valueAt(s.points, t), start: s.points[0]?.v ?? 0 }))
    .filter((r): r is { s: Series; v: number; start: number } => r.v != null)
    .sort((a, b) => b.v - a.v)
    .map((r, i) => ({ s: r.s, v: r.v, rank: i + 1, change: r.v - r.start }));
  const row = (k: string | null) => (k ? rows.find((r) => r.s.key === k) ?? null : null);
  const hotKey = hover?.key !== focus ? hover?.key ?? null : null;
  const mine = row(focus);
  const hot = row(hotKey);

  /** The time under the pointer, and the line closest to it (within ~24px). */
  const pick = (clientX: number, clientY: number, box: DOMRect) => {
    const px = clientX - box.left, py = clientY - box.top;
    const tt = x0 + Math.max(0, Math.min(1, (px - pad.l) / w)) * (x1 - x0);
    let best: string | null = null, dist = 24;
    for (const s of series) {
      const v = valueAt(s.points, tt);
      if (v == null) continue;
      const d = Math.abs(y(v) - py);
      if (d < dist) { dist = d; best = s.key; }
    }
    setHover({ t: tt, key: best });
  };

  const Info = ({ r, color }: { r: Row; color: string }) => (
    <div className="info-row">
      <span className="swatch" style={{ background: color }} />
      <Avatar k={r.s.key} emoji={r.s.emoji} size={20} /><span className="info-name">{r.s.label}</span>
      <strong className={r.v >= 0 ? "up" : "down"}>{dollars(r.v, true)}</strong>
      <span className="muted">{pct(r.v / (given[r.s.key] || 1000), true)} · #{r.rank} of {rows.length}</span>
    </div>
  );

  return (
    <div className="chart" ref={ref}>
      <div className="info" aria-live="polite">
        <div className="muted small">{hover == null ? "Now" : when(t)}</div>
        {mine && <Info r={mine} color="var(--series-1)" />}
        {hot ? (
          <>
            <Info r={hot} color="var(--series-2)" />
            {mine && (
              <div className="muted small">
                {me.label} is {mine.v >= hot.v ? "ahead of" : "behind"} {hot.s.label} by {dollars(Math.abs(mine.v - hot.v))}
              </div>
            )}
          </>
        ) : (
          <div className="muted small">Point at or tap a gray line to see who it is.</div>
        )}
      </div>
      <svg
        height={height}
        role="img"
        aria-label={`${me.label}'s profit over time compared with the team`}
        style={{ touchAction: "pan-y" }}
        onPointerMove={(e) => pick(e.clientX, e.clientY, e.currentTarget.getBoundingClientRect())}
        onPointerDown={(e) => pick(e.clientX, e.clientY, e.currentTarget.getBoundingClientRect())}
        // On a phone the pick stays after lifting the finger; with a mouse it clears on leaving
        onPointerLeave={(e) => { if (e.pointerType === "mouse") setHover(null); }}
      >
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={pad.l + w} y1={y(v)} y2={y(v)} stroke={v === 0 ? "var(--axis)" : "var(--grid)"} strokeWidth={1} />
            <text x={pad.l + w + 6} y={y(v)} dy="0.32em" fontSize={11} fill="var(--text-muted)" style={{ fontVariantNumeric: "tabular-nums" }}>
              {axisMoney(v)}
            </text>
          </g>
        ))}
        {[x0, x1].map((tt, k) => (
          <text key={k} x={x(tt)} y={height - 6} textAnchor={k ? "end" : "start"} fontSize={11} fill="var(--text-muted)">
            {k ? "now" : when(tt)}
          </text>
        ))}
        {series.filter((s) => s.key !== focus && s.key !== hotKey).map((s) => (
          <path key={s.key} d={path(s)} fill="none" stroke="var(--deemph)" strokeWidth={1.5} strokeLinejoin="round" />
        ))}
        {hot && <path d={path(hot.s)} fill="none" stroke="var(--series-2)" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />}
        <path d={path(me)} fill="none" stroke="var(--series-1)" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
        {hover != null && <line x1={x(t)} x2={x(t)} y1={pad.t} y2={pad.t + h} stroke="var(--axis)" strokeWidth={1} />}
        {mine && <circle cx={x(Math.min(t, me.points[me.points.length - 1].t))} cy={y(mine.v)} r={4} fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth={2} />}
        {hot && <circle cx={x(Math.min(t, hot.s.points[hot.s.points.length - 1].t))} cy={y(hot.v)} r={4} fill="var(--series-2)" stroke="var(--surface-1)" strokeWidth={2} />}
      </svg>
      <div className="legend">
        <span><span className="key" style={{ background: "var(--series-1)" }} />{me.label}</span>
        <span><span className="key" style={{ background: "var(--series-2)" }} />{hot ? hot.s.label : "highlighted teammate"}</span>
        <span><span className="key" style={{ background: "var(--deemph)" }} />everyone else</span>
      </div>
    </div>
  );
}
