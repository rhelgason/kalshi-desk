"use client";

import { useMemo, useState } from "react";
import type { PortfolioPoint } from "@/lib/portfolio";
import type { MoneyMove } from "@/lib/types";
import MoneyMarks from "./MoneyMarks";
import { ago, axisMoney, dollars } from "@/lib/format";
import { niceTicks, useWidth } from "./useWidth";
import { lerpAt } from "@/lib/interp";

const fmtWhen = (t: number, spanDays: number) =>
  new Date(t).toLocaleString("en-US", spanDays > 2
    ? { month: "short", day: "numeric", hour: "numeric" }
    : { weekday: "short", hour: "numeric", minute: "2-digit" });

/**
 * The whole desk's value over time (solid line) against the money put in
 * (dashed). The gap between them is the profit: shaded green above, red below.
 * With a what-if line, that shading steps aside for one light band between the
 * real line and the what-if (one color, so lines that cross don't turn to confetti).
 * Drag a finger (or mouse) across to read any moment; the readout sits above
 * the chart so a finger never covers it, and says how much has changed since
 * that moment (the line after it fades back). Letting go (or the mouse leaving) goes back to now (11-16).
 */
export default function PortfolioChart({ points, alt, height = 220, profitOnly, marks, checked }: {
  /** when the bot last looked at Kalshi, shown under the chart */
  checked?: string | null;
  points: PortfolioPoint[];
  /** money put in or taken out mid-season, marked where it happened */
  marks?: MoneyMove[];
  /** a running profit line (one coin's settled bets) instead of the pool's value: what to call it */
  profitOnly?: string;
  /** an alternative "what it would be worth" line (the what-if), same times as points */
  alt?: number[] | null;
  height?: number;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(360);
  const [hover, setHover] = useState<number | null>(null);
  const pad = { l: 8, r: 52, t: 8, b: 24 };
  const w = width - pad.l - pad.r;
  const h = height - pad.t - pad.b;

  const geo = useMemo(() => {
    if (points.length < 2) return null;
    const x0 = points[0].t, x1 = points[points.length - 1].t;
    const vals = [...points.flatMap((p) => [p.worth, p.putIn]), ...(alt ?? [])];
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const padY = Math.max((hi - lo) * 0.15, hi * 0.002, 1);
    lo -= padY;
    hi += padY;
    const ticks = niceTicks(lo, hi, 4).filter((v) => v >= lo && v <= hi);
    const x = (t: number) => pad.l + (x1 === x0 ? w / 2 : ((t - x0) / (x1 - x0)) * w);
    const y = (v: number) => pad.t + h - ((v - lo) / (hi - lo || 1)) * h;
    return { x0, x1, ticks, x, y };
  }, [points, alt, w, h, pad.l, pad.t]);

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
  const altPath = alt ? alt.map((v, j) => `${j ? "L" : "M"}${x(points[j].t).toFixed(1)},${y(v).toFixed(1)}`).join("") : null;
  const band = alt ? `${worthPath}${[...alt].reverse().map((v, j) => `L${x(points[alt.length - 1 - j].t).toFixed(1)},${y(v).toFixed(1)}`).join("")}Z` : null;

  // The exact moment under the pointer, read off the lines as drawn (not snapped to a data point)
  const ht = hover ?? x1;
  const at = (f: (q: PortfolioPoint) => number, step = false) => lerpAt(points, ht, (q) => q.t, f, step) ?? f(points[0]);
  const p = { t: ht, worth: at((q) => q.worth), putIn: at((q) => q.putIn, true) };
  const altNow = alt ? lerpAt(points.map((q, j) => ({ t: q.t, v: alt[j] })), ht, (q) => q.t, (q) => q.v) : null;
  const profit = p.worth - p.putIn;
  const altProfit = altNow != null ? altNow - p.putIn : null;
  // While scrubbing: how much it's moved from that moment to now (the "what happened since" number)
  const last = points[points.length - 1];
  const sinceThen = hover != null ? (profitOnly ? (last.worth - last.putIn) - profit : last.worth - p.worth) : null;
  const cut = x(p.t);

  const pick = (clientX: number, box: DOMRect) => {
    const frac = Math.max(0, Math.min(1, (clientX - box.left - pad.l) / w));
    setHover(x0 + frac * (x1 - x0));
  };

  return (
    <div className="chart" ref={ref}>
      <div className="readout" aria-live="polite">
        <span className="muted">{hover == null ? "Now" : fmtWhen(p.t, spanDays)}</span>
        {profitOnly ? (
          <span><strong className={profit >= 0 ? "up" : "down"}>{dollars(profit, true)}</strong> <span className="muted">{profitOnly}</span></span>
        ) : (
          <>
            <span><strong>{dollars(p.worth)}</strong> <span className="muted">worth</span></span>
            <span className={profit >= 0 ? "up" : "down"}>{profit >= 0 ? "▲ Up" : "▼ Down"} {dollars(Math.abs(profit))}</span>
          </>
        )}
        {sinceThen != null && (
          <span className="since-then">since then <strong className={sinceThen >= 0 ? "up" : "down"}>{sinceThen >= 0 ? "▲" : "▼"} {dollars(Math.abs(sinceThen))}</strong></span>
        )}
        {altNow != null && altProfit != null && (
          <span><span className="swatch" style={{ background: "var(--series-2)" }} /> what if: <strong>{dollars(altNow)}</strong>{" "}
            <span className="muted">({altProfit >= 0 ? "up" : "down"} {dollars(Math.abs(altProfit))})</span></span>
        )}
      </div>
      <svg
        height={height}
        role="img"
        aria-label={`Desk value over time: now ${dollars(points[points.length - 1].worth)}, with ${dollars(points[points.length - 1].putIn)} put in`}
        style={{ touchAction: "pan-y" }}
        onPointerMove={(e) => { if (e.pointerType === "mouse" || e.buttons) pick(e.clientX, e.currentTarget.getBoundingClientRect()); }}
        // Keep following the finger even when it drifts off the chart mid-drag
        onPointerDown={(e) => { e.currentTarget.setPointerCapture?.(e.pointerId); pick(e.clientX, e.currentTarget.getBoundingClientRect()); }}
        // Back to now when the finger lifts or the mouse leaves
        onPointerUp={(e) => { if (e.pointerType !== "mouse") setHover(null); }}
        onPointerCancel={() => setHover(null)}
        onPointerLeave={(e) => { if (e.pointerType === "mouse") setHover(null); }}
      >
        <defs>
          <clipPath id="pf-above"><path d={top} /></clipPath>
          <clipPath id="pf-below"><path d={bottom} /></clipPath>
          <clipPath id="pf-plot"><rect x={pad.l} y={pad.t - 4} width={w} height={h + 8} /></clipPath>
          {/* While scrubbing, the line after the finger fades back: what came since */}
          <clipPath id="pf-past"><rect x={pad.l - 4} y={pad.t - 4} width={Math.max(0, cut - pad.l + 4)} height={h + 8} /></clipPath>
          <clipPath id="pf-future"><rect x={cut} y={pad.t - 4} width={Math.max(0, pad.l + w - cut + 4)} height={h + 8} /></clipPath>
        </defs>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={pad.l + w} y1={y(v)} y2={y(v)} stroke="var(--grid)" strokeWidth={1} />
            <text x={pad.l + w + 6} y={y(v)} dy="0.32em" fontSize={11} fill="var(--text-muted)" style={{ fontVariantNumeric: "tabular-nums" }}>
              {axisMoney(v, ticks[1] - ticks[0])}
            </text>
          </g>
        ))}
        {[x0, x1].map((t, k) => (
          <text key={k} x={x(t)} y={height - 6} textAnchor={k ? "end" : "start"} fontSize={11} fill="var(--text-muted)">
            {k && hover == null ? "now" : fmtWhen(t, spanDays)}
          </text>
        ))}
        <g clipPath="url(#pf-plot)">
          {band ? <path d={band} fill="var(--series-2)" opacity={0.18} /> : (
            <>
              <path d={gap} fill="var(--up)" opacity={0.14} clipPath="url(#pf-above)" />
              <path d={gap} fill="var(--down)" opacity={0.14} clipPath="url(#pf-below)" />
            </>
          )}
          <path d={putInPath} fill="none" stroke="var(--text-muted)" strokeWidth={1.5} strokeDasharray="4 4" />
          {altPath && <path d={altPath} fill="none" stroke="var(--series-2)" strokeWidth={2} strokeDasharray="6 3" strokeLinejoin="round" />}
          {hover == null ? (
            <path d={worthPath} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          ) : (
            <>
              <path d={worthPath} fill="none" stroke="var(--series-1)" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" clipPath="url(#pf-past)" />
              <path d={worthPath} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" opacity={0.3} clipPath="url(#pf-future)" />
            </>
          )}
        </g>
        <MoneyMarks marks={marks} x={x} x0={x0} x1={x1} top={pad.t} bottom={pad.t + h} />
        {hover != null && <line x1={x(p.t)} x2={x(p.t)} y1={pad.t} y2={pad.t + h} stroke="var(--axis)" strokeWidth={1} />}
        {hover != null && <circle cx={x(p.t)} cy={y(p.putIn)} r={3} fill="var(--surface-1)" stroke="var(--text-muted)" strokeWidth={1.5} />}
        {altNow != null && <circle cx={x(p.t)} cy={y(altNow)} r={4} fill="var(--series-2)" stroke="var(--surface-1)" strokeWidth={2} />}
        <circle cx={x(p.t)} cy={y(p.worth)} r={4} fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth={2} />
      </svg>
      <div className="legend">
        <span><span className="key" style={{ background: "var(--series-1)" }} />{profitOnly ?? "Account value"}</span>
        {alt && <span><span className="key" style={{ background: "var(--series-2)" }} />What if</span>}
        {alt && <span><span className="key band" />The difference they made</span>}
        <span><span className="key dashed" />{profitOnly ? "Break-even" : "Money put in"}</span>
        {checked && <span className="legend-checked" suppressHydrationWarning>Checked {ago(checked)}</span>}
      </div>
    </div>
  );
}
