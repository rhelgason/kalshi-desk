/**
 * The season by day (11-16): the bot adds up each employee's finished bets per day (in the office's time zone) after
 * every run (desk/paper/ledger.py publish_page_summary, the status row `_page`), so a page reads ~1,300 small rows
 * instead of Training's ~40,000 bets. Pages take single bets only for the latest weeks and these rows before that.
 */
import type { Bet } from "./records";
import type { Point } from "./types";

/** One employee's day: bets, wins, profit, money bet, biggest win and loss, and when its last bet finished. */
export type DayRow = [day: string, strategy: string, n: number, won: number, pnl: number, cost: number, best: number, worst: number, last: number];
/** An employee's whole season in four numbers: bets, wins, profit, money bet. */
export type Totals = { n: number; won: number; pnl: number; cost: number };

/** Each employee's season, added up from their days. */
export function totalsOf(rows: DayRow[]): Record<string, Totals> {
  const out: Record<string, Totals> = {};
  for (const [, k, n, won, pnl, cost] of rows) {
    const t = (out[k] ??= { n: 0, won: 0, pnl: 0, cost: 0 });
    t.n += n; t.won += won; t.pnl += pnl; t.cost += cost;
  }
  return out;
}

/** Profit per $1 bet over a season's totals (null before anything was bet). */
export const rateOf = (t?: Totals) => (t?.cost ? t.pnl / t.cost : null);

/** Days before `day` (YYYY-MM-DD) as one rolled-up bet each, to put in front of the single bets from `day` on. */
export const daysBefore = (rows: DayRow[], day: string, keep?: (k: string) => boolean): Bet[] =>
  rows.filter((r) => r[0] < day && (!keep || keep(r[1])))
    .map(([, strategy, n, won, pnl, cost, best, worst, last]) => ({ t: last, strategy, coin: "", pnl, cost, price: null, n, won, best, worst }));

/** Each employee's running profit after each day (their sparkline on the team list). */
export function trendsOf(rows: DayRow[]): Record<string, Point[]> {
  const out: Record<string, Point[]> = {}, run: Record<string, number> = {};
  for (const [, k, , , pnl, , , , last] of rows) (out[k] ??= []).push({ t: last, v: (run[k] = (run[k] ?? 0) + pnl) });
  return out;
}

/**
 * The day (YYYY-MM-DD) a moment falls on in time zone `tz`. One formatter per time zone, reused: making a new one
 * for each of thousands of bets (toLocaleDateString) took a few hundred milliseconds per page.
 */
const formatters = new Map<string, Intl.DateTimeFormat>();
export function dayOf(t: number, tz: string): string {
  let f = formatters.get(tz);
  if (!f) formatters.set(tz, (f = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" })));
  return f.format(t);
}

/** The moment day `day` (YYYY-MM-DD) starts in time zone `tz`. */
export function midnight(day: string, tz: string): number {
  const offset = (t: number) => Date.parse(new Date(t).toLocaleString("sv-SE", { timeZone: tz }).replace(" ", "T") + "Z") - t;
  const guess = Date.parse(`${day}T00:00:00Z`);
  return guess - offset(guess - offset(guess));
}

/**
 * Which single bets a page takes (lib/db getBetsSince): from the start of the day `days` days ago, split at the
 * start of today. Whole days, so the cache keys repeat all day; every page (and /api/warm) uses this to share them.
 */
export function betWindow(tz: string, days = 14, now = Date.now()) {
  const todayStart = midnight(dayOf(now, tz), tz);
  const firstDay = dayOf(todayStart - days * 86_400_000, tz);
  return { firstDay, since: new Date(midnight(firstDay, tz)).toISOString(), today: new Date(todayStart).toISOString() };
}

/**
 * Finished bets for the what-if replay (components/HeroChart), merged per employee: by day before the chart starts,
 * and between two of the chart's points after (the replay is only read at the points, so the line is the same).
 * Training's two weeks of single bets (~4,500) become a few hundred rows, a much smaller page.
 */
export function forReplay(bets: Bet[], points: { t: number }[], tz: string): [t: number, strategy: string, pnl: number][] {
  const start = points[0]?.t ?? Infinity;
  const at = (t: number) => {          // the first point at or after t
    let lo = 0, hi = points.length - 1;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (points[mid].t >= t) hi = mid; else lo = mid + 1; }
    return points[lo].t;
  };
  const m = new Map<string, [number, string, number]>();
  for (const b of bets) {
    const slot = b.t < start ? dayOf(b.t, tz) : String(at(b.t));
    const row = m.get(`${slot}|${b.strategy}`);
    if (row) { row[0] = Math.max(row[0], b.t < start ? b.t : row[0]); row[2] += b.pnl; }
    else m.set(`${slot}|${b.strategy}`, [b.t < start ? b.t : at(b.t), b.strategy, b.pnl]);
  }
  return [...m.values()].map(([t, s, p]) => [t, s, Math.round(p * 100) / 100] as [number, string, number]).sort((a, b) => a[0] - b[0]);
}
