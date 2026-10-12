"use client";

import { useMemo, useState } from "react";
import type { Point, Series } from "@/lib/types";
import { axisMoney, dollars } from "@/lib/format";
import { niceTicks, useWidth } from "./useWidth";

const valueAt = (pts: Point[], t: number) => {
  let v: number | null = null;
  for (const p of pts) {
    if (p.t > t) break;
    v = p.v;
  }
  return v;
};

/**
 * One employee's profit over time (blue), compared with a teammate of your
 * choice (orange) or everyone else (gray). Drag across to read any moment;
 * the readout sits above the chart so a finger never covers it.
 */
export default function CompareChart({ series, focus, height = 220 }: { series: Series[]; focus: string; height?: number }) {
  const [ref, width] = useWidth<HTMLDivElement>(360);
  const [hover, setHover] = useState<number | null>(null);
  const [other, setOther] = useState<string>("everyone");
  const me = series.find((s) => s.key === focus);
  const rival = series.find((s) => s.key === other) ?? null;
  const shown = other === "everyone" ? series : series.filter((s) => s.key === focus || s.key === other);

  const pad = { l: 8, r: 52, t: 8, b: 24 };
  const w = width - pad.l - pad.r;
  const h = height - pad.t - pad.b;

  const geo = useMemo(() => {
    const pts = shown.flatMap((s) => s.points);
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
  }, [shown, me, w, h, pad.l, pad.t]);

  const picker = (
    <label className="picker">
      <span className="muted">Compare with</span>
      <select value={other} onChange={(e) => setOther(e.target.value)}>
        <option value="everyone">Everyone (gray lines)</option>
        <option value="nobody">Nobody</option>
        {series.filter((s) => s.key !== focus).map((s) => (
          <option key={s.key} value={s.key}>{s.emoji} {s.label}</option>
        ))}
      </select>
    </label>
  );

  if (!geo || !me) {
    return <>{picker}<div className="empty">Not enough history yet for this range.</div></>;
  }
  const { x0, x1, ticks, x, y } = geo;
  const spanDays = (x1 - x0) / 86_400_000;
  const when = (t: number) =>
    new Date(t).toLocaleString("en-US", spanDays > 2 ? { month: "short", day: "numeric", hour: "numeric" } : { weekday: "short", hour: "numeric", minute: "2-digit" });
  const path = (s: Series) => s.points.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join("");

  const t = hover ?? x1;
  const mine = valueAt(me.points, t);
  const theirs = rival ? valueAt(rival.points, t) : null;

  const pick = (clientX: number, box: DOMRect) => {
    const px = clientX - box.left;
    setHover(x0 + Math.max(0, Math.min(1, (px - pad.l) / w)) * (x1 - x0));
  };

  return (
    <div className="chart" ref={ref}>
      {picker}
      <div className="readout" aria-live="polite">
        <span className="muted">{hover == null ? "Now" : when(t)}</span>
        <span>
          <span className="swatch" style={{ background: "var(--series-1)" }} /> {me.label}{" "}
          <strong className={mine == null ? "" : mine >= 0 ? "up" : "down"}>{mine == null ? "–" : dollars(mine, true)}</strong>
        </span>
        {rival && (
          <span>
            <span className="swatch" style={{ background: "var(--series-2)" }} /> {rival.label}{" "}
            <strong className={theirs == null ? "" : theirs >= 0 ? "up" : "down"}>{theirs == null ? "–" : dollars(theirs, true)}</strong>
          </span>
        )}
      </div>
      <svg
        height={height}
        role="img"
        aria-label={`${me.label}'s profit over time`}
        style={{ touchAction: "pan-y" }}
        onPointerMove={(e) => pick(e.clientX, e.currentTarget.getBoundingClientRect())}
        onPointerDown={(e) => pick(e.clientX, e.currentTarget.getBoundingClientRect())}
        onPointerLeave={() => setHover(null)}
        onPointerCancel={() => setHover(null)}
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
        {other === "everyone" && series.filter((s) => s.key !== focus).map((s) => (
          <path key={s.key} d={path(s)} fill="none" stroke="var(--deemph)" strokeWidth={1.5} strokeLinejoin="round" />
        ))}
        {rival && <path d={path(rival)} fill="none" stroke="var(--series-2)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />}
        <path d={path(me)} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {hover != null && <line x1={x(t)} x2={x(t)} y1={pad.t} y2={pad.t + h} stroke="var(--axis)" strokeWidth={1} />}
        {mine != null && <circle cx={x(Math.min(t, me.points[me.points.length - 1].t))} cy={y(mine)} r={4} fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth={2} />}
        {rival && theirs != null && <circle cx={x(Math.min(t, rival.points[rival.points.length - 1].t))} cy={y(theirs)} r={4} fill="var(--series-2)" stroke="var(--surface-1)" strokeWidth={2} />}
      </svg>
      <div className="legend">
        <span><span className="key" style={{ background: "var(--series-1)" }} />{me.label}</span>
        {rival && <span><span className="key" style={{ background: "var(--series-2)" }} />{rival.label}</span>}
        {other === "everyone" && <span><span className="key" style={{ background: "var(--deemph)" }} />everyone else</span>}
        <span className="muted">$0 line = broke even</span>
      </div>
    </div>
  );
}
