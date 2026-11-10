"use client";

import { useId, useMemo, useState } from "react";
import type { MoneyMove, Point, Series } from "@/lib/types";
import MoneyMarks from "./MoneyMarks";
import { axisMoney, dollars, pct, shortName } from "@/lib/format";
import Avatar from "./Avatar";
import { niceTicks, useWidth } from "./useWidth";
import { lerpAt } from "@/lib/interp";

// Read each line exactly as drawn: straight between points, so the dot sits on the line
const valueAt = (pts: Point[], t: number) => lerpAt(pts, t, (p) => p.t, (p) => p.v);

const median = (vs: number[]) => {
  const s = [...vs].sort((a, b) => a - b);
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
};

/**
 * One employee's profit over time (blue) against the typical teammate (gray
 * dashed: the median of the office pool, so one wild employee can't drag it),
 * plus one teammate picked from the menu (orange) to compare with.
 */
export default function CompareChart({ series, focus, given, members, height = 240, marks }: {
  /** money put in or taken out of the pool mid-season, marked where it happened */
  marks?: MoneyMove[];
  series: Series[];
  focus: string;
  /** money each employee was given, for "% of their money" */
  given: Record<string, number>;
  /** who counts toward the typical teammate (the office pool, not the yardsticks) */
  members: string[];
  height?: number;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(360);
  const [hover, setHover] = useState<number | null>(null);
  const [other, setOther] = useState<string>("");
  const clip = useId().replace(/:/g, "");
  const me = series.find((s) => s.key === focus);
  const them = series.find((s) => s.key === other) ?? null;

  const pad = { l: 8, r: 52, t: 8, b: 24 };
  const w = width - pad.l - pad.r;
  const h = height - pad.t - pad.b;

  // The typical teammate, sampled evenly across the range
  const typical = useMemo<Point[]>(() => {
    const pool = series.filter((s) => members.includes(s.key) && s.points.length);
    const all = pool.flatMap((s) => s.points.map((p) => p.t));
    if (pool.length < 2 || !all.length) return [];
    const x0 = Math.min(...all), x1 = Math.max(...all);
    const out: Point[] = [];
    for (let i = 0; i <= 120; i++) {
      const t = x0 + ((x1 - x0) * i) / 120;
      const vs = pool.map((s) => valueAt(s.points, t)).filter((v): v is number => v != null);
      if (vs.length) out.push({ t, v: median(vs) });
    }
    return out;
  }, [series, members]);

  const shown = useMemo(() => [me, them].filter((s): s is Series => !!s).map((s) => s.points).concat([typical]), [me, them, typical]);

  const geo = useMemo(() => {
    if (!me || me.points.length < 2) return null;
    const pts = shown.flat();
    const x0 = Math.min(...pts.map((p) => p.t)), x1 = Math.max(...pts.map((p) => p.t));
    const lo = Math.min(0, ...pts.map((p) => p.v)), hi = Math.max(0, ...pts.map((p) => p.v));
    const ticks = niceTicks(lo, hi, 4);
    // The axis always covers every line, so nothing can run off the chart
    const step = ticks[1] - ticks[0] || 1;
    while (ticks[ticks.length - 1] < hi) ticks.push(ticks[ticks.length - 1] + step);
    while (ticks[0] > lo) ticks.unshift(ticks[0] - step);
    const y0 = ticks[0], y1 = ticks[ticks.length - 1];
    return {
      x0, x1, ticks,
      x: (t: number) => pad.l + (x1 === x0 ? w / 2 : ((t - x0) / (x1 - x0)) * w),
      y: (v: number) => pad.t + h - ((v - y0) / (y1 - y0 || 1)) * h,
    };
  }, [shown, me, w, h, pad.l, pad.t]);

  if (!geo || !me) return <div className="empty">Not enough history yet for this range.</div>;
  const { x0, x1, ticks, x, y } = geo;
  const spanDays = (x1 - x0) / 86_400_000;
  const when = (t: number) =>
    new Date(t).toLocaleString("en-US", spanDays > 2 ? { month: "short", day: "numeric", hour: "numeric" } : { weekday: "short", hour: "numeric", minute: "2-digit" });
  const path = (pts: Point[]) => pts.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join("");

  const t = hover ?? x1;
  const at = (pts: Point[]) => valueAt(pts, Math.min(t, pts[pts.length - 1]?.t ?? t));
  const mine = at(me.points);
  const mid = typical.length ? at(typical) : null;
  const theirs = them ? at(them.points) : null;

  const pick = (clientX: number, box: DOMRect) => {
    const frac = Math.max(0, Math.min(1, (clientX - box.left - pad.l) / w));
    setHover(x0 + frac * (x1 - x0));
  };

  const Info = ({ s, v, color }: { s: Series; v: number; color: string }) => (
    <div className="info-row">
      <span className="swatch" style={{ background: color }} />
      <Avatar k={s.key} emoji={s.emoji} size={20} /><span className="info-name">{s.label}</span>
      <strong className={v >= 0 ? "up" : "down"}>{dollars(v, true)}</strong>
      <span className="muted">{pct(v / (given[s.key] || 1000), true)}</span>
    </div>
  );
  const dot = (pts: Point[], v: number | null, color: string) =>
    v != null && pts.length ? <circle cx={x(Math.min(t, pts[pts.length - 1].t))} cy={y(v)} r={4} fill={color} stroke="var(--surface-1)" strokeWidth={2} /> : null;

  return (
    <div className="chart" ref={ref}>
      <div className="compare-pick">
        <label className="muted small" htmlFor={`${clip}-pick`}>Compare with</label>
        <select id={`${clip}-pick`} value={other} onChange={(e) => setOther(e.target.value)}>
          <option value="">Nobody</option>
          {series.filter((s) => s.key !== focus).map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
      </div>
      <div className="info" aria-live="polite">
        <div className="muted small">{hover == null ? "Now" : when(t)}</div>
        {mine != null && <Info s={me} v={mine} color="var(--series-1)" />}
        {mid != null && (
          <div className="info-row">
            <span className="swatch dashed" />
            <span className="info-name">Typical teammate</span>
            <strong className={mid >= 0 ? "up" : "down"}>{dollars(mid, true)}</strong>
            {mine != null && <span className="muted">{shortName(me.label)} is {mine >= mid ? "ahead" : "behind"} by {dollars(Math.abs(mine - mid))}</span>}
          </div>
        )}
        {them && theirs != null && <Info s={them} v={theirs} color="var(--series-2)" />}
      </div>
      <svg
        height={height}
        role="img"
        aria-label={`${me.label}'s profit over time compared with the typical teammate`}
        style={{ touchAction: "pan-y" }}
        onPointerMove={(e) => pick(e.clientX, e.currentTarget.getBoundingClientRect())}
        onPointerDown={(e) => pick(e.clientX, e.currentTarget.getBoundingClientRect())}
        // On a phone the reading stays after lifting the finger; with a mouse it clears on leaving
        onPointerLeave={(e) => { if (e.pointerType === "mouse") setHover(null); }}
      >
        <defs>
          <clipPath id={clip}><rect x={pad.l} y={pad.t - 4} width={w} height={h + 8} /></clipPath>
        </defs>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={pad.l + w} y1={y(v)} y2={y(v)} stroke={v === 0 ? "var(--axis)" : "var(--grid)"} strokeWidth={1} />
            <text x={pad.l + w + 6} y={y(v)} dy="0.32em" fontSize={11} fill="var(--text-muted)" style={{ fontVariantNumeric: "tabular-nums" }}>
              {axisMoney(v, ticks[1] - ticks[0])}
            </text>
          </g>
        ))}
        {[x0, x1].map((tt, k) => (
          <text key={k} x={x(tt)} y={height - 6} textAnchor={k ? "end" : "start"} fontSize={11} fill="var(--text-muted)">
            {k ? "now" : when(tt)}
          </text>
        ))}
        <g clipPath={`url(#${clip})`}>
          {typical.length > 0 && <path d={path(typical)} fill="none" stroke="var(--text-muted)" strokeWidth={1.5} strokeDasharray="5 4" strokeLinejoin="round" />}
          {them && <path d={path(them.points)} fill="none" stroke="var(--series-2)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />}
          <path d={path(me.points)} fill="none" stroke="var(--series-1)" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
        </g>
        <MoneyMarks marks={marks} x={x} x0={x0} x1={x1} top={pad.t} bottom={pad.t + h} />
        {hover != null && <line x1={x(t)} x2={x(t)} y1={pad.t} y2={pad.t + h} stroke="var(--axis)" strokeWidth={1} />}
        {dot(typical, mid, "var(--text-muted)")}
        {them && dot(them.points, theirs, "var(--series-2)")}
        {dot(me.points, mine, "var(--series-1)")}
      </svg>
      <div className="legend">
        <span><span className="key" style={{ background: "var(--series-1)" }} />{me.label}</span>
        {typical.length > 0 && <span><span className="key dashed" />Typical teammate (median)</span>}
        {them && <span><span className="key" style={{ background: "var(--series-2)" }} />{them.label}</span>}
      </div>
    </div>
  );
}
