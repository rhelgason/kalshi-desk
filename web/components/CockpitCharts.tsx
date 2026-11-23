"use client";

import { useId, useMemo, useState } from "react";
import { dollars, pct } from "@/lib/format";
import { fmtWhen } from "./PortfolioChart";
import { niceTicks, useWidth } from "./useWidth";
import ReturnsChart, { type ReturnLine } from "./ReturnsChart";

/** One office over the range: worth (v) and money put in so far (p) at each moment. */
export type OfficeSeries = {
  key: string; label: string; color: string; worth: number; putIn: number; since: number;
  pts: { t: number; v: number; p: number }[];
};

type Mode = "growth" | "stack" | "profit" | "bars" | "current";
const MODES: { key: Mode; label: string }[] = [
  { key: "growth", label: "A · $1 became" },
  { key: "stack", label: "B · Stacked" },
  { key: "profit", label: "C · $ profit" },
  { key: "bars", label: "D · Bars" },
  { key: "current", label: "Current %" },
];
const N = 160; // samples across the range: every line is drawn from these, so hover dots sit exactly on it
const H = 260;

/** An office at time t, straight between its points; null before it opened. */
function at(s: OfficeSeries, t: number) {
  const pts = s.pts;
  if (!pts.length || t < pts[0].t) return null;
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i];
    if (t <= b.t) {
      const f = b.t === a.t ? 1 : (t - a.t) / (b.t - a.t);
      return { v: a.v + (b.v - a.v) * f, p: t < b.t ? a.p : b.p };
    }
  }
  const z = pts[pts.length - 1];
  return { v: z.v, p: z.p };
}

/** End-of-line tags pushed apart so they never overprint (at least `gap` px between centres). */
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
 * TEMPORARY (11-22): the cockpit chart's candidates side by side behind a switcher, so the owner can pick one in
 * production. A "what each $1 became", B stacked money, C dollar profit, D money vs put in as bars, and the current %.
 */
export default function CockpitCharts({ series, lines, from, now, checked, money }: {
  series: OfficeSeries[]; lines: ReturnLine[]; from: number; now: number; checked?: string | null; money: boolean;
}) {
  const [mode, setMode] = useState<Mode>("growth");
  return (
    <div className="cockpit-charts">
      <div className="chart-switch" role="tablist" aria-label="Chart style (trying them out)">
        {MODES.filter((m) => money || m.key !== "stack").map((m) => (
          <button key={m.key} type="button" role="tab" aria-selected={mode === m.key} className={mode === m.key ? "on" : ""}
                  onClick={() => setMode(m.key)}>{m.label}</button>
        ))}
      </div>
      {mode === "current" ? <ReturnsChart lines={lines} from={from} now={now} checked={checked} />
        : mode === "bars" ? <Bars series={series} money={money} />
        : <Lines series={series} mode={mode} now={now} money={money} />}
    </div>
  );
}

function Lines({ series, mode, now, money }: { series: OfficeSeries[]; mode: "growth" | "stack" | "profit"; now: number; money: boolean }) {
  const [ref, width] = useWidth<HTMLDivElement>(600);
  const [hover, setHover] = useState<number | null>(null);
  const clip = useId().replace(/:/g, "");
  const live = series.filter((s) => s.pts.length > 1);
  const x0 = Math.min(...live.map((s) => s.pts[0].t), now), x1 = now;
  const times = useMemo(() => [...Array(N + 1)].map((_, i) => x0 + ((x1 - x0) * i) / N), [x0, x1]);

  // Each office's value on the shared grid, in this chart's unit
  const val = (s: OfficeSeries, t: number) => {
    const r = at(s, t);
    if (!r || r.p < 1) return null;
    return mode === "growth" ? r.v / r.p : mode === "profit" ? r.v - r.p : r.v;
  };
  const grid = live.map((s) => ({ s, ys: times.map((t) => val(s, t)) }));
  // Stacked: each band sits on the ones before it (biggest at the bottom)
  const order = [...grid].sort((a, b) => b.s.worth - a.s.worth);
  const base = times.map(() => 0);
  const bands = mode === "stack" ? order.map(({ s, ys }) => {
    const lo = [...base], hi = ys.map((y, i) => (base[i] += y ?? 0));
    return { s, lo, hi: [...hi] };
  }) : [];
  const putInTotal = mode === "stack" ? times.map((t) => live.reduce((sum, s) => sum + (at(s, t)?.p ?? 0), 0)) : [];

  const all = mode === "stack" ? [...base, ...putInTotal] : grid.flatMap((g) => g.ys.filter((y): y is number => y != null));
  const ref0 = mode === "growth" ? 1 : 0;
  let lo = Math.min(ref0, ...all), hi = Math.max(ref0, ...all);
  const room = (hi - lo) * 0.08 || 0.1;
  hi += room; if (mode !== "stack") lo -= room;
  const ticks = niceTicks(lo, hi, 4).filter((v) => v >= lo && v <= hi);
  const narrow = width < 520;
  const pad = { l: 8, r: narrow ? 92 : 128, t: 12, b: 24 };
  const w = Math.max(100, width - pad.l - pad.r), h = H - pad.t - pad.b;
  const X = (t: number) => pad.l + ((t - x0) / (x1 - x0 || 1)) * w;
  const Y = (v: number) => pad.t + h - ((v - lo) / (hi - lo || 1)) * h;
  const fmt = (v: number) => (mode === "growth" ? `×${v.toFixed(2)}` : mode === "profit" ? dollars(v, true) : dollars(v));
  const axis = (v: number) => (mode === "growth" ? `×${v.toFixed(v < 10 ? 1 : 0)}` : money ? (Math.abs(v) >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${Math.round(v)}`) : "");
  const path = (ys: (number | null)[]) => {
    let d = "", pen = false;
    ys.forEach((y, i) => { if (y == null) { pen = false; return; } d += `${pen ? "L" : "M"}${X(times[i]).toFixed(1)},${Y(y).toFixed(1)}`; pen = true; });
    return d;
  };
  const idx = hover == null ? N : Math.round(((hover - x0) / (x1 - x0 || 1)) * N);
  const pick = (clientX: number, box: DOMRect) => {
    const f = Math.max(0, Math.min(1, (clientX - box.left - pad.l) / w));
    setHover(x0 + f * (x1 - x0));
  };

  // Tags at the right end (or the hovered moment's values in the readout)
  const ends = mode === "stack"
    ? bands.map((b) => ({ key: b.s.key, y: Y((b.lo[N] + b.hi[N]) / 2) }))
    : grid.filter((g) => g.ys[N] != null).map((g) => ({ key: g.s.key, y: Y(g.ys[N] as number) }));
  const tagY = spread(ends, 17, pad.t + 6, pad.t + h - 4);
  const reading = (mode === "stack" ? order : grid).map((g) => ({ s: g.s, v: g.ys[idx] })).filter((r) => r.v != null)
    .sort((a, b) => (b.v as number) - (a.v as number));
  const total = mode === "stack" ? base[idx] : null;

  const label = mode === "growth" ? "What each $1 put in is worth now" : mode === "profit" ? "Profit so far (worth minus put in)" : "Everyone's money, stacked; dashed: total put in";

  return (
    <div className="chart cockpit-lines" ref={ref}>
      <div className="readout" aria-live="polite">
        <span className="muted">{hover == null ? "Now" : fmtWhen(times[idx], (x1 - x0) / 86_400_000)}</span>
        {total != null && money && <span><strong>{dollars(total)}</strong> <span className="muted">together</span></span>}
        {reading.map(({ s, v }) => (
          <span key={s.key} className="readout-item">
            <span className="swatch" style={{ background: s.color }} /> {short(s.label)}{" "}
            <strong className={mode === "stack" ? "" : (v as number) >= ref0 ? "up" : "down"}>
              {mode === "growth" || money ? fmt(v as number) : pct((v as number) / (s.putIn || 1), true, 1)}
            </strong>
          </span>
        ))}
      </div>
      <svg width="100%" height={H} role="img" aria-label={label} style={{ touchAction: "pan-y", display: "block", overflow: "visible" }}
           onPointerMove={(e) => { if (e.pointerType === "mouse" || e.buttons) pick(e.clientX, e.currentTarget.getBoundingClientRect()); }}
           onPointerDown={(e) => { e.currentTarget.setPointerCapture?.(e.pointerId); pick(e.clientX, e.currentTarget.getBoundingClientRect()); }}
           onPointerUp={(e) => { if (e.pointerType !== "mouse") setHover(null); }}
           onPointerCancel={() => setHover(null)}
           onPointerLeave={(e) => { if (e.pointerType === "mouse") setHover(null); }}>
        <defs>
          <clipPath id={clip}><rect x={pad.l} y={pad.t - 6} width={w} height={h + 12} /></clipPath>
          {live.map((s) => (
            <linearGradient key={s.key} id={`${clip}-${s.key}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity={mode === "stack" ? 0.75 : 0.22} />
              <stop offset="100%" stopColor={s.color} stopOpacity={mode === "stack" ? 0.4 : 0} />
            </linearGradient>
          ))}
        </defs>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={pad.l + w} y1={Y(v)} y2={Y(v)} stroke="var(--grid)" />
            {(money || mode === "growth") && <text x={pad.l + 4} y={Y(v) - 4} fontSize={10.5} fill="var(--text-muted)">{axis(v)}</text>}
          </g>
        ))}
        {mode !== "stack" && <line x1={pad.l} x2={pad.l + w} y1={Y(ref0)} y2={Y(ref0)} stroke="var(--axis)" strokeDasharray="4 4" />}
        {[x0, x1].map((t, k) => (
          <text key={k} x={X(t)} y={H - 6} textAnchor={k ? "end" : "start"} fontSize={11} fill="var(--text-muted)">
            {k ? "now" : fmtWhen(t, (x1 - x0) / 86_400_000)}
          </text>
        ))}
        <g clipPath={`url(#${clip})`}>
          {mode === "stack" ? <>
            {bands.map((b) => (
              <path key={b.s.key} fill={`url(#${clip}-${b.s.key})`} stroke={b.s.color} strokeWidth={1.25}
                    d={`${times.map((t, i) => `${i ? "L" : "M"}${X(t).toFixed(1)},${Y(b.hi[i]).toFixed(1)}`).join("")}${times.map((t, i) => `L${X(times[N - i]).toFixed(1)},${Y(b.lo[N - i]).toFixed(1)}`).join("")}Z`} />
            ))}
            <path d={path(putInTotal)} fill="none" stroke="var(--text-primary)" strokeWidth={1.5} strokeDasharray="5 4" opacity={0.7} />
          </> : grid.map(({ s, ys }) => (
            <g key={s.key}>
              {mode === "growth" && <path d={`${path(ys)}L${X(x1)},${Y(ref0)}L${X(times[ys.findIndex((y) => y != null)] ?? x0)},${Y(ref0)}Z`} fill={`url(#${clip}-${s.key})`} />}
              <path d={path(ys)} fill="none" stroke={s.color} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" className="glow-line"
                    style={{ "--glow": s.color } as React.CSSProperties} />
            </g>
          ))}
        </g>
        {hover != null && <line x1={X(times[idx])} x2={X(times[idx])} y1={pad.t} y2={pad.t + h} stroke="var(--axis)" strokeDasharray="3 3" />}
        {mode !== "stack" && grid.map(({ s, ys }) => ys[idx] == null ? null : (
          <circle key={s.key} cx={X(times[idx])} cy={Y(ys[idx] as number)} r={hover == null ? 4.5 : 4} fill={s.color} stroke="var(--surface-1)" strokeWidth={2} />
        ))}
        {(mode === "stack" ? bands.map((b) => ({ s: b.s, v: b.hi[N] - b.lo[N] })) : grid.map((g) => ({ s: g.s, v: g.ys[N] }))).map(({ s, v }) => v == null || tagY[s.key] == null ? null : (
          <g key={s.key} className="end-tag">
            <line x1={pad.l + w + 2} x2={pad.l + w + 8} y1={mode === "stack" ? tagY[s.key] : Y(v as number)} y2={tagY[s.key]} stroke={s.color} />
            <rect x={pad.l + w + 8} y={tagY[s.key] - 8} rx={8} width={pad.r - 12} height={16} fill={`color-mix(in srgb, ${s.color} 22%, var(--surface-1))`} stroke={s.color} strokeWidth={1} />
            <text x={pad.l + w + 15} y={tagY[s.key]} dy="0.33em" fontSize={10.5} fontWeight={650} fill="var(--text-primary)">
              {short(s.label)}{!narrow || mode === "growth" ? " " : ""}
              <tspan fill={mode === "stack" ? "var(--text-secondary)" : (v as number) >= ref0 ? "var(--up)" : "var(--down)"}>
                {narrow && mode !== "growth" ? "" : mode === "growth" ? `×${(v as number).toFixed(2)}` : money ? (mode === "profit" ? dollars(v as number, true) : dollars(v as number)) : ""}
              </tspan>
            </text>
          </g>
        ))}
      </svg>
      <div className="muted small chart-caption">{label}</div>
    </div>
  );
}

function Bars({ series, money }: { series: OfficeSeries[]; money: boolean }) {
  const sorted = [...series].sort((a, b) => (money ? b.worth - a.worth : b.worth / (b.putIn || 1) - a.worth / (a.putIn || 1)));
  const top = Math.max(1, ...sorted.map((s) => (money ? Math.max(s.worth, s.putIn) : Math.max(s.worth / (s.putIn || 1), 1))));
  return (
    <div className="money-bars">
      {sorted.map((s, i) => {
        const g = s.worth - s.putIn, r = s.putIn ? g / s.putIn : 0;
        const put = money ? s.putIn / top : 1 / top, now = money ? s.worth / top : s.worth / (s.putIn || 1) / top;
        return (
          <div key={s.key} className="money-bar-row" style={{ "--c": s.color, "--i": i } as React.CSSProperties}>
            <div className="money-bar-name"><span className="swatch" style={{ background: s.color }} /> {s.label}</div>
            <div className="money-bar-track">
              <div className="money-bar-put" style={{ width: `${put * 100}%` }} />
              <div className="money-bar-now" style={{ width: `${now * 100}%` }} />
              <div className="money-bar-mark" style={{ left: `${put * 100}%` }} />
            </div>
            <div className="money-bar-nums">
              {money && <strong>{dollars(s.worth)}</strong>}
              <span className={g >= 0 ? "up" : "down"}>{money ? `${dollars(g, true)} · ` : ""}{pct(r, true, 1)}</span>
              {money && <span className="muted small">put in {dollars(s.putIn)}</span>}
            </div>
          </div>
        );
      })}
      <div className="muted small chart-caption">Faint bar: money put in · bright bar: worth now · tick: break-even</div>
    </div>
  );
}
