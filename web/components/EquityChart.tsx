"use client";

import { useMemo, useState } from "react";
import type { Series } from "@/lib/types";
import { axisMoney, money } from "@/lib/format";
import { niceTicks, useWidth } from "./useWidth";

/**
 * P&L over time for every employee. With a dozen employees there are more
 * lines than distinguishable colors, so everyone draws in a quiet gray and one
 * employee at a time is highlighted in the accent color (hover a line, or a
 * row in the leaderboard via `highlight`).
 */
export default function EquityChart({
  series,
  highlight,
  onHighlight,
  height = 280,
}: {
  series: Series[];
  highlight?: string | null;
  onHighlight?: (key: string | null) => void;
  height?: number;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hoverX, setHoverX] = useState<number | null>(null);
  const [localHot, setLocalHot] = useState<string | null>(null);
  const hot = localHot ?? highlight ?? (series.length === 1 ? series[0].key : null);

  const pad = { l: 56, r: 16, t: 12, b: 28 };
  const w = width - pad.l - pad.r;
  const h = height - pad.t - pad.b;

  const { x0, x1, yTicks, x, y } = useMemo(() => {
    const pts = series.flatMap((s) => s.points);
    const x0 = Math.min(...pts.map((p) => p.t));
    const x1 = Math.max(...pts.map((p) => p.t));
    const lo = Math.min(0, ...pts.map((p) => p.v));
    const hi = Math.max(0, ...pts.map((p) => p.v));
    const yTicks = niceTicks(lo, hi, 5);
    const y0 = yTicks[0];
    const y1 = yTicks[yTicks.length - 1];
    return {
      x0,
      x1,
      yTicks,
      x: (t: number) => pad.l + (x1 === x0 ? w / 2 : ((t - x0) / (x1 - x0)) * w),
      y: (v: number) => pad.t + h - ((v - y0) / (y1 - y0 || 1)) * h,
    };
  }, [series, w, h, pad.l, pad.t]);

  if (!series.length || !series.some((s) => s.points.length)) {
    return <div className="empty">No equity history yet. It fills in every 5 minutes once the bot is running.</div>;
  }

  const path = (s: Series) =>
    s.points.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join("");

  const spanDays = (x1 - x0) / 86_400_000;
  const fmtTime = (t: number) => {
    const d = new Date(t);
    return spanDays > 2
      ? d.toLocaleDateString("en-US", { month: "short", day: "numeric" })
      : d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  };
  const nTicks = Math.min(6, Math.max(2, Math.floor(w / 110)));
  const xTicks = Array.from({ length: nTicks }, (_, i) => x0 + ((x1 - x0) * i) / (nTicks - 1));

  // Nearest timestamp to the cursor, and each series' value at that time
  let tip: { t: number; rows: { s: Series; v: number }[] } | null = null;
  if (hoverX != null) {
    const t = x0 + ((hoverX - pad.l) / w) * (x1 - x0);
    const rows = series
      .map((s) => {
        let best = s.points[0];
        for (const p of s.points) if (Math.abs(p.t - t) < Math.abs(best.t - t)) best = p;
        return { s, v: best.v, t: best.t };
      })
      .sort((a, b) => b.v - a.v);
    tip = { t: rows[0]?.t ?? t, rows };
  }

  const ordered = [...series].sort((a, b) => (a.key === hot ? 1 : b.key === hot ? -1 : 0));

  return (
    <div className="chart" ref={ref}>
      <svg
        height={height}
        role="img"
        aria-label="Profit and loss over time for each employee"
        onMouseMove={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          const px = e.clientX - box.left;
          setHoverX(px >= pad.l && px <= pad.l + w ? px : null);
        }}
        onMouseLeave={() => {
          setHoverX(null);
          setLocalHot(null);
          onHighlight?.(null);
        }}
      >
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={pad.l + w} y1={y(v)} y2={y(v)} stroke={v === 0 ? "var(--axis)" : "var(--grid)"} strokeWidth={1} />
            <text x={pad.l - 8} y={y(v)} dy="0.32em" textAnchor="end" fontSize={11} fill="var(--text-muted)" style={{ fontVariantNumeric: "tabular-nums" }}>
              {axisMoney(v)}
            </text>
          </g>
        ))}
        {xTicks.map((t, i) => (
          <text key={i} x={x(t)} y={height - 8} textAnchor={i === 0 ? "start" : i === xTicks.length - 1 ? "end" : "middle"} fontSize={11} fill="var(--text-muted)">
            {fmtTime(t)}
          </text>
        ))}

        {ordered.map((s) => {
          const isHot = s.key === hot;
          const last = s.points[s.points.length - 1];
          return (
            <g key={s.key}>
              <path d={path(s)} fill="none" stroke={isHot ? "var(--series-1)" : "var(--deemph)"} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {/* Wide invisible stroke: a hover target bigger than the 2px line */}
              <path
                d={path(s)}
                fill="none"
                stroke="transparent"
                strokeWidth={12}
                onMouseEnter={() => {
                  setLocalHot(s.key);
                  onHighlight?.(s.key);
                }}
              />
              {isHot && last && (
                <circle cx={x(last.t)} cy={y(last.v)} r={4} fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth={2} />
              )}
            </g>
          );
        })}

        {tip && hoverX != null && (
          <line x1={x(tip.t)} x2={x(tip.t)} y1={pad.t} y2={pad.t + h} stroke="var(--axis)" strokeWidth={1} />
        )}
      </svg>

      {tip && hoverX != null && (
        <div className="tooltip" style={{ left: Math.min(x(tip.t) + 12, width - 200), top: 8 }}>
          <div className="t">{new Date(tip.t).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</div>
          {tip.rows.slice(0, 12).map(({ s, v }) => (
            <div key={s.key} className={`row ${s.key === hot ? "hot" : ""}`}>
              <span>{s.emoji} {s.label}</span>
              <span className="num">{money(v)}</span>
            </div>
          ))}
        </div>
      )}

      {series.length > 1 && (
        <div className="legend">
          {hot ? (
            <>
              <span><span className="key" style={{ background: "var(--series-1)" }} />{series.find((s) => s.key === hot)?.label}</span>
              <span><span className="key" style={{ background: "var(--deemph)" }} />everyone else</span>
            </>
          ) : (
            <span><span className="key" style={{ background: "var(--deemph)" }} />one line per employee. Hover a line or a leaderboard row to highlight it</span>
          )}
        </div>
      )}
    </div>
  );
}
