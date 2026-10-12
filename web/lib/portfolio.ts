import type { Point } from "./types";

/** Chart time ranges. Each picks its own point spacing so a chart has ~150-200 points. */
export const RANGES = {
  day: { label: "Day", days: 1 },
  week: { label: "Week", days: 7 },
  month: { label: "Month", days: 30 },
  quarter: { label: "3 months", days: 90 },
  season: { label: "Season", days: null },
} as const;
export type RangeKey = keyof typeof RANGES;

export const parseRange = (v: unknown, fallback: RangeKey = "season"): RangeKey =>
  typeof v === "string" && v in RANGES ? (v as RangeKey) : fallback;

/** Point spacing (a Postgres interval) for a span of time. */
export function binFor(spanMs: number): string {
  const days = spanMs / 86_400_000;
  if (days <= 1.5) return "10 minutes";
  if (days <= 8) return "1 hour";
  if (days <= 35) return "4 hours";
  if (days <= 100) return "12 hours";
  return "1 day";
}

/** Raw equity snapshots for every employee over a range (see getHistory in db.ts). */
export type History = {
  since: number;
  /** strategy -> [time, account value], one per time bucket, oldest first */
  points: Record<string, { b: number; t: number; equity: number }[]>;
  /** account value just before the range starts (employees already working then) */
  seeds: Record<string, number>;
  /** bankroll each employee started the season with */
  starting: Record<string, number>;
  /** money given (+) or taken (-) after the start: bonuses */
  transfers: { t: number; strategy: string; amount: number }[];
};

export type PortfolioPoint = { t: number; worth: number; putIn: number };

function givenBy(h: History, strategy: string, t: number): number {
  let total = h.starting[strategy] ?? 0;
  for (const x of h.transfers) if (x.strategy === strategy && x.t <= t) total += x.amount;
  return total;
}

/**
 * The whole desk over time: what everything is worth, and how much money was
 * put in (each employee's bankroll from when they started, plus bonuses).
 */
export function portfolioSeries(h: History): PortfolioPoint[] {
  const last: Record<string, number> = { ...h.seeds };
  // Someone hired partway through counts as sitting on their starting money until
  // their first snapshot, so the total doesn't jump up when they arrive
  for (const [k, pts] of Object.entries(h.points)) {
    if (!(k in last) && pts.length) last[k] = h.starting[k] ?? pts[0].equity;
  }
  const buckets = new Map<number, { t: number; rows: [string, number][] }>();
  for (const [k, pts] of Object.entries(h.points)) {
    for (const p of pts) {
      const b = buckets.get(p.b) ?? { t: p.t, rows: [] };
      b.t = Math.max(b.t, p.t);
      b.rows.push([k, p.equity]);
      buckets.set(p.b, b);
    }
  }
  const total = (t: number): PortfolioPoint => {
    let worth = 0, putIn = 0;
    for (const [k, v] of Object.entries(last)) {
      worth += v;
      putIn += givenBy(h, k, t);
    }
    return { t, worth, putIn };
  };
  const out: (PortfolioPoint & { n: number })[] = [];
  if (Object.keys(last).length) out.push({ ...total(h.since), n: Object.keys(last).length });
  for (const [, b] of [...buckets.entries()].sort((a, b) => a[0] - b[0])) {
    for (const [k, v] of b.rows) last[k] = v;
    out.push({ ...total(b.t), n: Object.keys(last).length });
  }
  // The first snapshot of a season can straddle a bucket edge and catch only
  // some employees; drop those partial leading points (later hires still step up)
  while (out.length > 1 && out[0].n < out[1].n) out.shift();
  return out.map(({ t, worth, putIn }) => ({ t, worth, putIn }));
}

/** Each employee's profit over time: account value minus the money they were given. */
export function profitSeries(h: History): Record<string, Point[]> {
  const out: Record<string, Point[]> = {};
  for (const [k, pts] of Object.entries(h.points)) {
    const series: Point[] = [];
    if (k in h.seeds) series.push({ t: h.since, v: h.seeds[k] - givenBy(h, k, h.since) });
    for (const p of pts) series.push({ t: p.t, v: p.equity - givenBy(h, k, p.t) });
    out[k] = series;
  }
  return out;
}
