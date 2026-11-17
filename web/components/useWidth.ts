"use client";

import { useEffect, useRef, useState } from "react";

/** Measure an element's width so SVG charts can draw at true pixel size. */
export function useWidth<T extends HTMLElement>(initial = 640) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(initial);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(160, entry.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Round, human-friendly axis ticks covering [lo, hi]. */
export function niceTicks(lo: number, hi: number, count = 5): number[] {
  if (lo === hi) {
    lo -= 1;
    hi += 1;
  }
  const span = hi - lo;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= count) ?? 10 * mag;
  const start = Math.floor(lo / step) * step;
  const ticks = [];
  // Up to the first tick at or above hi, so the top of every line stays inside the chart
  for (let v = start; ticks.length === 0 || ticks[ticks.length - 1] < hi - 1e-9; v += step) ticks.push(Math.round(v * 1e6) / 1e6);
  return ticks;
}

/**
 * A gently smoothed line (11-16): points closer than a few pixels are merged (the last one wins), then joined by a
 * monotone curve, which bends without overshooting, so a run of tiny wins reads as a slope instead of a staircase.
 */
export function smoothPath(xy: [number, number][], gap = 4): string {
  // Each kept point at least `gap` px after the one before (bets that settle together share a moment); a merged
  // point keeps its place and takes the latest value; the very last point (now) is always kept where it is
  const pts: [number, number][] = [];
  for (const p of xy) {
    const last = pts[pts.length - 1];
    if (last && p[0] - last[0] < gap) { if (pts.length > 1) last[1] = p[1]; else pts.push([last[0] + gap, p[1]]); }
    else pts.push([p[0], p[1]]);
  }
  const end = xy[xy.length - 1];
  if (end && pts[pts.length - 1][0] !== end[0]) {
    if (end[0] - pts[pts.length - 2]?.[0] < gap) pts[pts.length - 1] = [end[0], end[1]];
    else pts.push([end[0], end[1]]);
  }
  if (pts.length < 3) return pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
  const n = pts.length, d: number[] = [], m: number[] = [];
  for (let i = 0; i < n - 1; i++) d.push((pts[i + 1][1] - pts[i][1]) / (pts[i + 1][0] - pts[i][0] || 1));
  m.push(d[0]);
  for (let i = 1; i < n - 1; i++) m.push(d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2);
  m.push(d[n - 2]);
  let out = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  for (let i = 0; i < n - 1; i++) {
    const [x0, y0] = pts[i], [x1, y1] = pts[i + 1], h = (x1 - x0) / 3;
    out += `C${(x0 + h).toFixed(1)},${(y0 + m[i] * h).toFixed(1)} ${(x1 - h).toFixed(1)},${(y1 - m[i + 1] * h).toFixed(1)} ${x1.toFixed(1)},${y1.toFixed(1)}`;
  }
  return out;
}
