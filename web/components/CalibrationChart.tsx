"use client";

import { useState } from "react";
import type { CalibrationBin } from "@/lib/types";
import { useWidth } from "./useWidth";

/**
 * Forecast vs. reality. Each dot is a group of bets: x = the average forecast,
 * y = how often those bets actually won. Dots on the diagonal = well calibrated;
 * below it = overconfident.
 */
export default function CalibrationChart({
  model,
  market,
  modelLabel = "Employee's odds",
}: {
  model: CalibrationBin[];
  market: CalibrationBin[];
  modelLabel?: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(420);
  const [tip, setTip] = useState<{ x: number; y: number; label: string; b: CalibrationBin } | null>(null);
  const size = Math.min(width, 420);
  const pad = { l: 44, r: 12, t: 10, b: 36 };
  const w = size - pad.l - pad.r;
  const h = size * 0.8 - pad.t - pad.b;
  const x = (p: number) => pad.l + p * w;
  const y = (p: number) => pad.t + (1 - p) * h;
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const groups = [
    ...(model.length ? [{ label: modelLabel, bins: model, color: "var(--series-1)" }] : []),
    { label: "Market price", bins: market, color: "var(--series-2)" },
  ].filter((g) => g.bins.length);

  if (!groups.length) return <div className="empty">No settled bets yet.</div>;

  return (
    <div className="chart" ref={ref}>
      <svg height={size * 0.8} viewBox={`0 0 ${size} ${size * 0.8}`} style={{ maxWidth: size }} role="img" aria-label="Calibration: forecast probability vs actual win rate">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(0)} x2={x(1)} y1={y(t)} y2={y(t)} stroke="var(--grid)" />
            <line x1={x(t)} x2={x(t)} y1={y(0)} y2={y(1)} stroke="var(--grid)" />
            <text x={pad.l - 6} y={y(t)} dy="0.32em" textAnchor="end" fontSize={11} fill="var(--text-muted)">{t * 100}%</text>
            <text x={x(t)} y={y(0) + 16} textAnchor="middle" fontSize={11} fill="var(--text-muted)">{t * 100}%</text>
          </g>
        ))}
        <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="var(--axis)" strokeWidth={1} />
        <text x={x(0.5)} y={y(0) + 32} textAnchor="middle" fontSize={11} fill="var(--text-secondary)">forecast</text>
        <text transform={`translate(12 ${y(0.5)}) rotate(-90)`} textAnchor="middle" fontSize={11} fill="var(--text-secondary)">actually won</text>
        {groups.map((g) =>
          g.bins.map((b) => (
            <circle
              key={`${g.label}-${b.lo}`}
              cx={x(b.avg_forecast)}
              cy={y(b.hit_rate)}
              r={5}
              fill={g.color}
              stroke="var(--surface-1)"
              strokeWidth={2}
              onMouseEnter={() => setTip({ x: x(b.avg_forecast), y: y(b.hit_rate), label: g.label, b })}
              onMouseLeave={() => setTip(null)}
              style={{ cursor: "default" }}
            />
          )),
        )}
      </svg>
      {tip && (
        <div className="tooltip" style={{ left: Math.min(tip.x + 10, size - 170), top: Math.max(0, tip.y - 70) }}>
          <div className="t">{tip.label}</div>
          <div className="row"><span>forecast</span><span className="num">{(tip.b.avg_forecast * 100).toFixed(1)}%</span></div>
          <div className="row"><span>actually won</span><span className="num">{(tip.b.hit_rate * 100).toFixed(1)}%</span></div>
          <div className="row"><span>bets</span><span className="num">{tip.b.n}</span></div>
        </div>
      )}
      <div className="legend">
        {groups.map((g) => (
          <span key={g.label}><span className="key" style={{ background: g.color, height: 8, width: 8, borderRadius: 4 }} />{g.label}</span>
        ))}
        <span><span className="key" style={{ background: "var(--axis)" }} />diagonal = perfectly calibrated</span>
      </div>
    </div>
  );
}
