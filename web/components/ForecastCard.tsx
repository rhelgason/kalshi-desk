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
  const out: number[] = [0];
  // up to the first tick at or above the top, so nothing is drawn above the chart
  while (out[out.length - 1] < max) out.push(out[out.length - 1] + step);
  return out;
}

type Fan = Forecast["fan"][number];
/** What's under the pointer: a day of the season so far, or a day of the forecast */
type Hover = { d: number; past?: number; fan?: Fan };

const dayWord = (d: number, today: Date) => {
  if (d === 0) return "Today";
  const t = new Date(today.getTime() + d * 86_400_000);
  return t.toLocaleDateString("en-US", { month: "short", day: "numeric" }) + (d > 0 ? ` · in ${d} days` : "");
};

/**
 * Where the office is heading (11-17, manager only for now): the season so far, then the prediction model's fan of
 * futures: the middle guess, the likely half and the 8-in-10 range, labelled at their right ends. Hover (or drag a
 * finger) for any day's numbers.
 */
export default function ForecastCard({ f }: { f: Forecast }) {
  const [h, setH] = useState(90);
  const [hover, setHover] = useState<Hover | null>(null);
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
  const today = new Date();
  const past = (f.check?.actual_line ?? []).map(([, v], i, all) => [i - (all.length - 1), v] as const);
  const fan = f.fan.filter((p) => p.day <= h);
  const last = fan[fan.length - 1];
  const narrow = W < 500;
  const H = narrow ? 230 : 290, L = 46, R = narrow ? 54 : 96, T = 14, B = 24;
  const xmin = past.length ? past[0][0] : 0;
  const yt = ticks(Math.max(...fan.map((p) => p.p90), ...past.map((p) => p[1])) * 1.04);
  const ytop = yt[yt.length - 1];
  const x = (d: number) => L + ((d - xmin) / (h - xmin)) * (W - L - R);
  const y = (v: number) => T + (1 - v / ytop) * (H - T - B);
  const band = (a: "p10" | "p25", b: "p90" | "p75") =>
    [...fan.map((p) => `${x(p.day)},${y(p[b])}`), ...fan.slice().reverse().map((p) => `${x(p.day)},${y(p[a])}`)].join(" ");
  const marks = h <= 30 ? [7, 14, 21, 30] : h <= 90 ? [30, 60, 90] : [60, 120, 180];
  const at = (d: number) => f.fan.reduce((a, p) => (Math.abs(p.day - d) < Math.abs(a.day - d) ? p : a));

  // Labels at the right end of each line and band, nudged apart so they never overlap
  const labels = [
    { text: "8 in 10", v: (last.p90 + last.p75) / 2, cls: "fc-l-wide" },
    { text: "likely", v: (last.p75 + last.p50) / 2, cls: "fc-l-likely" },
    { text: narrow ? "middle" : "middle guess", v: last.p50, cls: "fc-l-mid" },
  ].map((l) => ({ ...l, y: y(l.v) + 4 }));
  for (let i = 1; i < labels.length; i++) labels[i].y = Math.max(labels[i].y, labels[i - 1].y + 13);
  const over = labels[labels.length - 1].y - (H - B - 2);
  if (over > 0) labels.forEach((l) => (l.y -= over));

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const d = Math.round(xmin + ((e.clientX - r.left - L) / (W - L - R)) * (h - xmin));
    if (d < xmin || d > h) return setHover(null);
    if (d <= 0) {
      const p = past.find(([pd]) => pd === d) ?? past[past.length - 1];
      return setHover(p ? { d: p[0], past: p[1] } : null);
    }
    const p = at(d);
    setHover({ d: p.day, fan: p });
  };
  const hx = hover ? x(hover.d) : 0;

  return (
    <Card title="Where It's Heading" className="forecast" aside={
      <div className="segmented" role="radiogroup" aria-label="How far ahead">
        {HORIZONS.map((o) => (
          <button key={o.d} type="button" role="radio" aria-checked={h === o.d} onClick={() => { setH(o.d); setHover(null); }}>{o.label}</button>
        ))}
      </div>
    }>
      <div ref={box} className="forecast-box">
        <svg viewBox={`0 0 ${W} ${H}`} className="forecast-chart" width={W} height={H} role="img"
          aria-label={`Middle guess ${money(last.p50)} in ${last.day} days, likely between ${money(last.p25)} and ${money(last.p75)}`}
          onPointerMove={onMove} onPointerDown={onMove} onPointerLeave={() => setHover(null)}>
          {yt.map((v) => (
            <g key={v}>
              <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="fc-grid" />
              <text x={L - 6} y={y(v) + 4} textAnchor="end">{money(v)}</text>
            </g>
          ))}
          <text x={x(0)} y={H - 6} textAnchor="middle">today</text>
          {marks.map((d) => <text key={d} x={x(d)} y={H - 6} textAnchor="middle">{d >= 30 ? `${Math.round(d / 30)} mo` : `${d} d`}</text>)}
          <polygon points={band("p10", "p90")} className="fc-wide" />
          <polygon points={band("p25", "p75")} className="fc-likely" />
          <polyline points={fan.map((p) => `${x(p.day)},${y(p.p50)}`).join(" ")} className="fc-mid" />
          {past.length > 1 && <polyline points={past.map(([d, v]) => `${x(d)},${y(v)}`).join(" ")} className="fc-past" />}
          <circle cx={x(0)} cy={y(f.start)} r={4} className="fc-dot-now" />
          <circle cx={x(last.day)} cy={y(last.p50)} r={4} className="fc-dot-mid" />
          {past.length > 1 && x(0) - x(xmin) > 34 && (
            <text x={x(xmin)} y={y(past[0][1]) - 8} className="fc-l-past">so far</text>
          )}
          {labels.map((l) => <text key={l.text} x={W - R + 8} y={l.y} className={l.cls}>{l.text}</text>)}
          {hover && (
            <g className="fc-hover">
              <line x1={hx} x2={hx} y1={T} y2={H - B} />
              {hover.fan
                ? <><circle cx={hx} cy={y(hover.fan.p50)} r={4.5} className="fc-dot-mid" /></>
                : <circle cx={hx} cy={y(hover.past!)} r={4.5} className="fc-dot-now" />}
            </g>
          )}
        </svg>
        {hover && (
          <div className="fc-tip" style={{ left: Math.min(Math.max(hx, 90), W - 90) }}>
            <div className="fc-tip-day">{dayWord(hover.d, today)}</div>
            {hover.fan ? (
              <>
                <div className="fc-tip-main">{money(hover.fan.p50)}</div>
                <div>Likely {money(hover.fan.p25)} – {money(hover.fan.p75)}</div>
                <div className="muted">8 in 10: {money(hover.fan.p10)} – {money(hover.fan.p90)}</div>
              </>
            ) : <div className="fc-tip-main">{money(hover.past!)}</div>}
          </div>
        )}
      </div>
      <StatRow flat stats={HORIZONS.map((o) => {
        const p = at(o.d);
        return { label: `In ${o.label.replace("mo", o.d === 30 ? "month" : "months")}`, value: money(p.p50), note: `${money(p.p10)} – ${money(p.p90)}` };
      })} />
      <p className="muted small fc-foot">
        The middle guess is where half the simulated futures end up above and half below. A guess from Kalshi&apos;s trade
        history and every real bet so far, <strong>not a promise</strong>; the further out, the rougher it is, because
        bigger bets than we&apos;ve ever placed{f.tested_pool ? <> (past about {money(f.tested_pool)})</> : null} are still untested.
        {f.check && <> Started on day one with today&apos;s rules, it would have put today at {money(f.check.p10)}–{money(f.check.p90)}; the real {money(f.check.actual)} beat {Math.round(f.check.percentile * 100)}% of its futures.</>}
      </p>
    </Card>
  );
}
