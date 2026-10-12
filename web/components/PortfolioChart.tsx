"use client";

import { useMemo, useState } from "react";
import type { PortfolioPoint } from "@/lib/portfolio";
import { axisMoney, dollars } from "@/lib/format";
import { niceTicks, useWidth } from "./useWidth";

const fmtWhen = (t: number, spanDays: number) =>
  new Date(t).toLocaleString("en-US", spanDays > 2
    ? { month: "short", day: "numeric", hour: "numeric" }
    : { weekday: "short", hour: "numeric", minute: "2-digit" });

/**
 * The whole desk's value over time (solid line) against the money put in
 * (dashed). The gap between them is the profit: shaded green above, red below.
 * Drag a finger (or mouse) across to read any moment; the readout sits above
 * the chart so a finger never covers it.
 */
export default function PortfolioChart({ points, height = 220 }: { points: PortfolioPoint[]; height?: number }) {
  const [ref, width] = useWidth<HTMLDivElement>(360);
  const [hover, setHover] = useState<number | null>(null);
  const pad = { l: 8, r: 52, t: 8, b: 24 };
  const w = width - pad.l - pad.r;
  const h = height - pad.t - pad.b;

  const geo = useMemo(() => {
    if (points.length < 2) return null;
    const x0 = points[0].t, x1 = points[points.length - 1].t;
    const vals = points.flatMap((p) => [p.worth, p.putIn]);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const padY = Math.max((hi - lo) * 0.15, hi * 0.002, 1);
    lo -= padY;
    hi += padY;
    const ticks = niceTicks(lo, hi, 4).filter((v) => v >= lo && v <= hi);
    const x = (t: number) => pad.l + (x1 === x0 ? w / 2 : ((t - x0) / (x1 - x0)) * w);
    const y = (v: number) => pad.t + h - ((v - lo) / (hi - lo || 1)) * h;
    return { x0, x1, ticks, x, y };
  }, [points, w, h, pad.l, pad.t]);

  if (!geo) {
    return <div className="empty">Not enough history yet for this range. The line fills in every few minutes.</div>;
  }
  const { x0, x1, ticks, x, y } = geo;
  const spanDays = (x1 - x0) / 86_400_000;
  const line = (key: "worth" | "putIn", step = false) =>
    points.map((p, i) => {
      const px = x(p.t).toFixed(1), py = y(p[key]).toFixed(1);
      if (!i) return `M${px},${py}`;
      return step ? `H${px}V${py}` : `L${px},${py}`;
    }).join("");
  const worthPath = line("worth");
  const putInPath = line("putIn", true);
  // Area between the two lines, then clipped to above / below the put-in line
  const gap = `${worthPath}${[...points].reverse().map((p) => `L${x(p.t).toFixed(1)},${y(p.putIn).toFixed(1)}`).join("")}Z`;
  const top = `${putInPath}V${pad.t}H${pad.l}Z`;
  const bottom = `${putInPath}V${pad.t + h}H${pad.l}Z`;

  const i = hover ?? points.length - 1;
  const p = points[i];
  const profit = p.worth - p.putIn;

  const pick = (clientX: number, box: DOMRect) => {
    const t = x0 + ((clientX - box.left - pad.l) / w) * (x1 - x0);
    let best = 0;
    for (let j = 1; j < points.length; j++) if (Math.abs(points[j].t - t) < Math.abs(points[best].t - t)) best = j;
    setHover(best);
  };

  return (
    <div className="chart" ref={ref}>
      <div className="readout" aria-live="polite">
        <span className="muted">{hover == null ? "Now" : fmtWhen(p.t, spanDays)}</span>
        <span><strong>{dollars(p.worth)}</strong> <span className="muted">worth</span></span>
        <span className={profit >= 0 ? "up" : "down"}>{profit >= 0 ? "▲ Up" : "▼ Down"} {dollars(Math.abs(profit))}</span>
      </div>
      <svg
        height={height}
        role="img"
        aria-label={`Desk value over time: now ${dollars(points[points.length - 1].worth)}, with ${dollars(points[points.length - 1].putIn)} put in`}
        style={{ touchAction: "pan-y" }}
        onPointerMove={(e) => pick(e.clientX, e.currentTarget.getBoundingClientRect())}
        onPointerDown={(e) => pick(e.clientX, e.currentTarget.getBoundingClientRect())}
        onPointerLeave={() => setHover(null)}
        onPointerCancel={() => setHover(null)}
      >
        <defs>
          <clipPath id="pf-above"><path d={top} /></clipPath>
          <clipPath id="pf-below"><path d={bottom} /></clipPath>
        </defs>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={pad.l + w} y1={y(v)} y2={y(v)} stroke="var(--grid)" strokeWidth={1} />
            <text x={pad.l + w + 6} y={y(v)} dy="0.32em" fontSize={11} fill="var(--text-muted)" style={{ fontVariantNumeric: "tabular-nums" }}>
              {axisMoney(v)}
            </text>
          </g>
        ))}
        {[x0, x1].map((t, k) => (
          <text key={k} x={x(t)} y={height - 6} textAnchor={k ? "end" : "start"} fontSize={11} fill="var(--text-muted)">
            {k && hover == null ? "now" : fmtWhen(t, spanDays)}
          </text>
        ))}
        <path d={gap} fill="var(--up)" opacity={0.14} clipPath="url(#pf-above)" />
        <path d={gap} fill="var(--down)" opacity={0.14} clipPath="url(#pf-below)" />
        <path d={putInPath} fill="none" stroke="var(--text-muted)" strokeWidth={1.5} strokeDasharray="4 4" />
        <path d={worthPath} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {hover != null && <line x1={x(p.t)} x2={x(p.t)} y1={pad.t} y2={pad.t + h} stroke="var(--axis)" strokeWidth={1} />}
        <circle cx={x(p.t)} cy={y(p.worth)} r={4} fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth={2} />
      </svg>
      <div className="legend">
        <span><span className="key" style={{ background: "var(--series-1)" }} />What it&apos;s worth</span>
        <span><span className="key dashed" />Money put in: {dollars(p.putIn)}</span>
      </div>
    </div>
  );
}
