"use client";

import { useId, useState } from "react";
import { pct } from "@/lib/format";
import { fmtWhen, updatedAgo } from "./PortfolioChart";
import { niceTicks, smoothPath, useWidth } from "./useWidth";

/** One office for the chart: its colour, money put in, start, and running profit after each finished bet. */
export type ReturnLine = { key: string; label: string; color: string; putIn: number; since: number; pnl: [t: number, sum: number][] };

/** Profit so far at time t (the last finished bet at or before it). */
const sumAt = (l: ReturnLine, t: number) => {
  let v = 0;
  for (const [ts, s] of l.pnl) { if (ts > t) break; v = s; }
  return v;
};

/** End-of-line tags pushed apart so they never overprint, even when two lines end at the same place. */
function spread(ys: { key: string; y: number }[], gap: number, top: number, bottom: number) {
  const s = [...ys].sort((a, b) => a.y - b.y);
  for (let i = 1; i < s.length; i++) if (s[i].y - s[i - 1].y < gap) s[i].y = s[i - 1].y + gap;
  const over = s.length ? s[s.length - 1].y - bottom : 0;
  if (over > 0) for (const x of s) x.y -= over;
  for (let i = 0; i < s.length; i++) s[i].y = Math.max(top + i * gap, s[i].y);
  return Object.fromEntries(s.map((x) => [x.key, x.y]));
}

const short = (name: string) => name.split(" ")[0];

/**
 * Each office's return in % over the range picked (11-16, the cockpit). Offices of different sizes and ages share one
 * scale the standard way (a stock site's "compare"): each line starts at 0% where the range starts (or where the office
 * started, if later) and measures profit since then over what the office was worth then.
 *
 * 11-22 restyle (owner's pick of the candidates): every line is sampled on one grid across the range and drawn as a
 * smooth curve through those samples, so the hover dot (snapped to a sample) sits exactly on its line; a glow under
 * each line, a soft fill down to 0%, and a tag at each line's end, spaced so tags never overlap.
 */
export default function ReturnsChart({ lines, from, now, checked, height = 260 }: {
  lines: ReturnLine[]; from: number; now: number; checked?: string | null; height?: number;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(600);
  const [hover, setHover] = useState<number | null>(null);
  const clip = useId().replace(/:/g, "");
  if (!lines.length) return <div className="empty">No offices trading yet.</div>;

  const narrow = width < 520;
  const pad = { l: 8, r: narrow ? 110 : 120, t: 12, b: 24 };
  const w = Math.max(100, width - pad.l - pad.r), h = height - pad.t - pad.b;

  // Each office: when its line starts, and its return at any moment (profit since the start over its worth then)
  let made = 0, worth = 0;
  const offices = lines.map((l) => {
    const start = Math.max(from, l.since), s0 = sumAt(l, start), base = (l.putIn + s0) || 1;
    made += (l.pnl[l.pnl.length - 1]?.[1] ?? 0) - s0;
    worth += base;
    return { l, start, ret: (t: number) => (t < start ? null : (sumAt(l, t) - s0) / base) };
  });
  const together = worth ? made / worth : 0;
  const x0 = Math.min(...offices.map((o) => o.start)), x1 = now;
  // One shared grid, ~5 px apart: lines are drawn through these samples and the hover snaps to them
  const n = Math.max(40, Math.min(220, Math.round(w / 5)));
  const times = [...Array(n + 1)].map((_, i) => x0 + ((x1 - x0) * i) / n);
  const grid = offices.map((o) => ({ ...o, ys: times.map((t) => o.ret(t)) }));

  const vs = grid.flatMap((g) => g.ys.filter((y): y is number => y != null));
  let lo = Math.min(0, ...vs), hi = Math.max(0, ...vs);
  const room = Math.max((hi - lo) * 0.12, 0.002);
  lo -= room; hi += room;
  const ticks = niceTicks(lo, hi, 4).filter((v) => v >= lo && v <= hi);
  const step = ticks.length > 1 ? ticks[1] - ticks[0] : 0.01;
  const X = (t: number) => pad.l + ((t - x0) / (x1 - x0 || 1)) * w;
  const Y = (v: number) => pad.t + h - ((v - lo) / (hi - lo || 1)) * h;
  const spanDays = (x1 - x0) / 86_400_000;

  const xy = (ys: (number | null)[]) =>
    ys.map((y, i) => (y == null ? null : [X(times[i]), Y(y)] as [number, number])).filter((p): p is [number, number] => p != null);
  const idx = hover == null ? n : Math.max(0, Math.min(n, Math.round(((hover - x0) / (x1 - x0 || 1)) * n)));
  const pick = (clientX: number, box: DOMRect) => {
    const f = Math.max(0, Math.min(1, (clientX - box.left - pad.l) / w));
    setHover(x0 + f * (x1 - x0));
  };

  const ends = grid.filter((g) => g.ys[n] != null).map((g) => ({ key: g.l.key, y: Y(g.ys[n] as number) }));
  const tagY = spread(ends, 21, pad.t + 9, pad.t + h - 9);
  const reading = grid.map((g) => ({ l: g.l, v: g.ys[idx] })).filter((r) => r.v != null)
    .sort((a, b) => (b.v as number) - (a.v as number));

  return (
    <div className="chart returns-chart" ref={ref}>
      <div className="readout" aria-live="polite">
        <span className="muted">{hover == null ? "Now" : fmtWhen(times[idx], spanDays)}</span>
        {hover == null
          ? <span><strong className={together >= 0 ? "up" : "down"}>{pct(together, true, 1)}</strong> <span className="muted">all offices together</span></span>
          : reading.map(({ l, v }) => (
            <span key={l.key} className="readout-item">
              <span className="swatch" style={{ background: l.color }} /> {short(l.label)}{" "}
              <strong className={(v as number) >= 0 ? "up" : "down"}>{pct(v as number, true, 1)}</strong>
            </span>
          ))}
        {checked && <span className="readout-checked" suppressHydrationWarning>Updated {updatedAgo(checked)}</span>}
      </div>
      <svg width="100%" height={height} role="img" aria-label="Each office's return over the range"
           style={{ touchAction: "pan-y", display: "block", overflow: "visible" }}
           onPointerMove={(e) => { if (e.pointerType === "mouse" || e.buttons) pick(e.clientX, e.currentTarget.getBoundingClientRect()); }}
           onPointerDown={(e) => { e.currentTarget.setPointerCapture?.(e.pointerId); pick(e.clientX, e.currentTarget.getBoundingClientRect()); }}
           onPointerUp={(e) => { if (e.pointerType !== "mouse") setHover(null); }}
           onPointerCancel={() => setHover(null)}
           onPointerLeave={(e) => { if (e.pointerType === "mouse") setHover(null); }}>
        <defs>
          <clipPath id={`${clip}-plot`}><rect x={pad.l} y={pad.t - 6} width={w} height={h + 12} /></clipPath>
          {grid.map(({ l }) => (
            <linearGradient key={l.key} id={`${clip}-${l.key}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={l.color} stopOpacity={0.16} />
              <stop offset="100%" stopColor={l.color} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={pad.l + w} y1={Y(v)} y2={Y(v)} stroke="var(--grid)" />
            <text x={pad.l + 4} y={Y(v) - 4} fontSize={10.5} fill="var(--text-muted)" style={{ fontVariantNumeric: "tabular-nums" }}>
              {pct(v, v !== 0, step < 0.01 ? 1 : 0)}
            </text>
          </g>
        ))}
        <line x1={pad.l} x2={pad.l + w} y1={Y(0)} y2={Y(0)} stroke="var(--axis)" strokeDasharray="4 4" />
        {[x0, x1].map((t, k) => (
          <text key={k} x={X(t)} y={height - 6} textAnchor={k ? "end" : "start"} fontSize={11} fill="var(--text-muted)">
            {k ? "now" : fmtWhen(t, spanDays)}
          </text>
        ))}
        <g clipPath={`url(#${clip}-plot)`}>
          {grid.map(({ l, ys }) => {
            const pts = xy(ys);
            if (pts.length < 2) return null;
            const curve = smoothPath(pts);
            const last = pts[pts.length - 1], first = pts[0];
            return (
              <g key={l.key}>
                <path d={`${curve}L${last[0].toFixed(1)},${Y(0).toFixed(1)}L${first[0].toFixed(1)},${Y(0).toFixed(1)}Z`} fill={`url(#${clip}-${l.key})`} />
                <path d={curve} fill="none" stroke={l.color} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round"
                      className="glow-line" style={{ "--glow": l.color } as React.CSSProperties} />
              </g>
            );
          })}
        </g>
        {hover != null && <line x1={X(times[idx])} x2={X(times[idx])} y1={pad.t} y2={pad.t + h} stroke="var(--axis)" strokeDasharray="3 3" />}
        {grid.map(({ l, ys }) => ys[idx] == null ? null : (
          <circle key={l.key} cx={X(times[idx])} cy={Y(ys[idx] as number)} r={4.5} fill={l.color} stroke="var(--surface-1)" strokeWidth={2} />
        ))}
        {grid.map(({ l, ys }) => ys[n] == null || tagY[l.key] == null ? null : (
          <g key={l.key} className="end-tag">
            <path d={`M${pad.l + w + 2},${Y(ys[n] as number)} C${pad.l + w + 6},${Y(ys[n] as number)} ${pad.l + w + 4},${tagY[l.key]} ${pad.l + w + 9},${tagY[l.key]}`}
                  fill="none" stroke={l.color} strokeWidth={1.25} />
            <rect x={pad.l + w + 9} y={tagY[l.key] - 9} rx={9} width={pad.r - 12} height={18}
                  fill={`color-mix(in srgb, ${l.color} 22%, var(--surface-1))`} stroke={l.color} strokeWidth={1}
                  style={{ filter: "drop-shadow(0 2px 6px rgba(0,0,0,0.35))" }} />
            <text x={pad.l + w + 17} y={tagY[l.key]} dy="0.33em" fontSize={11} fontWeight={650} fill="var(--text-primary)">
              {short(l.label)}{" "}
              <tspan fill={(ys[n] as number) >= 0 ? "var(--up)" : "var(--down)"}>{pct(ys[n] as number, true, Math.abs(ys[n] as number) < 0.1 ? 1 : 0)}</tspan>
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
