"use client";

import { useEffect, useRef, useState } from "react";
import Card from "@/components/ui/Card";
import StatRow from "@/components/ui/StatRow";

/** The parts of the prediction model's status row `_forecast` (desk/forecast.py) this card draws. */
export type Forecast = {
  at: string;
  start: number;
  fan: { day: number; p10: number; p25: number; p50: number; p75: number; p90: number }[];
  tested_pool: number;
  check: { actual_line: [string, number][]; percentile: number; p10: number; p90: number; actual: number } | null;
};

const HORIZONS = [{ d: 30, label: "1 mo" }, { d: 90, label: "3 mo" }, { d: 180, label: "6 mo" }];

const money = (v: number) => v >= 10_000 ? `$${Math.round(v / 1000)}k` : v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${Math.round(v)}`;

function ticks(max: number, n = 4): number[] {
  const raw = max / n, p = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = 0; v <= max + 1e-9; v += step) out.push(v);
  return out;
}

/**
 * Where the office is heading (11-17, manager only for now): the season so far, then the prediction model's fan of
 * futures: the middle guess, the likely half and the 8-in-10 range. The dashed orange line is the pool size where
 * bids pass anything real fills have vouched for; above it the model is guessing about bigger bets.
 */
export default function ForecastCard({ f }: { f: Forecast }) {
  const [h, setH] = useState(90);
  // Drawn at the card's real width, so the labels stay 11px on a phone and on a laptop
  const box = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(680);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const past = (f.check?.actual_line ?? []).map(([, v], i, all) => [i - (all.length - 1), v] as const);
  const fan = f.fan.filter((p) => p.day <= h);
  const H = W < 500 ? 220 : 280, L = 46, R = 6, T = 12, B = 24;
  const xmin = past.length ? past[0][0] : 0;
  const yt = ticks(Math.max(...fan.map((p) => p.p90), ...past.map((p) => p[1])) * 1.05);
  const ytop = yt[yt.length - 1];
  const x = (d: number) => L + ((d - xmin) / (h - xmin)) * (W - L - R);
  const y = (v: number) => T + (1 - v / ytop) * (H - T - B);
  const band = (a: "p10" | "p25", b: "p90" | "p75") =>
    [...fan.map((p) => `${x(p.day)},${y(p[b])}`), ...fan.slice().reverse().map((p) => `${x(p.day)},${y(p[a])}`)].join(" ");
  const marks = h <= 30 ? [7, 14, 21, 30] : h <= 90 ? [30, 60, 90] : [60, 120, 180];
  const at = (d: number) => f.fan.reduce((a, p) => (Math.abs(p.day - d) < Math.abs(a.day - d) ? p : a));
  const last = fan[fan.length - 1];
  const from = f.check?.actual_line[0]?.[0];

  return (
    <Card title="Where It's Heading" className="forecast" aside={
      <div className="segmented" role="radiogroup" aria-label="How far ahead">
        {HORIZONS.map((o) => (
          <button key={o.d} type="button" role="radio" aria-checked={h === o.d} onClick={() => setH(o.d)}>{o.label}</button>
        ))}
      </div>
    }>
      <div ref={box} className="forecast-box">
      <svg viewBox={`0 0 ${W} ${H}`} className="forecast-chart" width={W} height={H} role="img"
        aria-label={`Middle guess ${money(last.p50)} in ${last.day} days, likely between ${money(last.p25)} and ${money(last.p75)}`}>
        {yt.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="fc-grid" />
            <text x={L - 6} y={y(v) + 4} textAnchor="end">{money(v)}</text>
          </g>
        ))}
        {from && x(0) - x(xmin) > 70 && <text x={x(xmin)} y={H - 6}>{new Date(from + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })}</text>}
        <text x={x(0)} y={H - 6} textAnchor="middle">today</text>
        {marks.map((d, i) => <text key={d} x={x(d)} y={H - 6} textAnchor={i === marks.length - 1 ? "end" : "middle"}>{d >= 30 ? `${Math.round(d / 30)} mo` : `${d} d`}</text>)}
        <polygon points={band("p10", "p90")} className="fc-wide" />
        <polygon points={band("p25", "p75")} className="fc-likely" />
        {f.tested_pool < ytop && (
          <g className="fc-tested">
            <line x1={L} x2={W - R} y1={y(f.tested_pool)} y2={y(f.tested_pool)} />
            <text x={W - R} y={y(f.tested_pool) - 5} textAnchor="end">tested so far</text>
          </g>
        )}
        <polyline points={fan.map((p) => `${x(p.day)},${y(p.p50)}`).join(" ")} className="fc-mid" />
        {past.length > 1 && <polyline points={past.map(([d, v]) => `${x(d)},${y(v)}`).join(" ")} className="fc-past" />}
        <circle cx={x(0)} cy={y(f.start)} r={4.5} className="fc-dot-now" />
        <circle cx={x(last.day)} cy={y(last.p50)} r={4.5} className="fc-dot-mid" />
      </svg>
      </div>
      <div className="fc-legend">
        <span><i className="fc-k-past" />So far</span>
        <span><i className="fc-k-mid" />Middle guess</span>
        <span><i className="fc-k-likely" />Likely</span>
        <span><i className="fc-k-wide" />8 in 10</span>
        <span><i className="fc-k-tested" />Bigger bets than we&apos;ve tested</span>
      </div>
      <StatRow flat stats={HORIZONS.map((o) => {
        const p = at(o.d);
        return { label: `In ${o.label.replace("mo", o.d === 30 ? "month" : "months")}`, value: money(p.p50), note: `${money(p.p10)} – ${money(p.p90)}` };
      })} />
      <p className="muted small fc-foot">
        A guess from Kalshi&apos;s trade history and every real bet so far, <strong>not a promise</strong>.
        {f.check && <> Started on day one with today&apos;s rules, it would have put today at {money(f.check.p10)}–{money(f.check.p90)}; the real {money(f.check.actual)} beat {Math.round(f.check.percentile * 100)}% of its futures.</>}
      </p>
    </Card>
  );
}
