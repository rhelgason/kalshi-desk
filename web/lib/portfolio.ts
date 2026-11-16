import type { LiveStatus, Point } from "./types";

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

const UNIT_MS: Record<string, number> = { minute: 60_000, hour: 3_600_000, day: 86_400_000 };
const binMs = (spanMs: number) => {
  const [n, unit] = binFor(spanMs).split(" ");
  return Number(n) * UNIT_MS[unit.replace(/s$/, "")];
};

export type Settled = { t: number; strategy: string; pnl: number };
/** A settled bet, or (with `n`) several earlier ones rolled into one row: see getSettlementsSince in db.ts. */
export type Settlement = { t: number; strategy: string; coin: string; pnl: number; n?: number; won?: number };
/** How many bets, and how many won, counting rolled-up rows by what they hold. */
export const betCount = (rows: Settlement[]) => rows.reduce((s, r) => s + (r.n ?? 1), 0);
export const winCount = (rows: Settlement[]) => rows.reduce((s, r) => s + (r.won ?? (r.pnl > 0 ? 1 : 0)), 0);

/**
 * The pool's value counting finished bets only: money put in plus every settled bet's
 * profit. A bet that's still riding counts at what it cost until it settles, so it never
 * shows as a loss just because its price wobbled. Employees are the ones in `h.starting`;
 * one point per time bucket (binFor) from `from` to `now`.
 *
 * `end` (the headline's worth, see headline below) is the last point: the line finishes on the number shown above
 * it, open bets at what they're worth now (2026-11-12: a weather bet already lost, but not paid out until the next
 * morning, had the chart $16 above the headline).
 */
export function settledSeries(h: History, settled: Settled[], from: number, now: number, end?: number): PortfolioPoint[] {
  const keys = Object.keys(h.starting);
  const mine = settled.filter((s) => s.strategy in h.starting);
  const putInAt = (t: number) => keys.reduce((s, k) => s + givenBy(h, k, t), 0);
  let profit = mine.filter((s) => s.t < from).reduce((s, r) => s + r.pnl, 0);
  const out: PortfolioPoint[] = [{ t: from, worth: putInAt(from) + profit, putIn: putInAt(from) }];
  const bin = binMs(now - from);
  const push = (t: number) => {
    const p = { t, worth: putInAt(t) + profit, putIn: putInAt(t) };
    const last = out[out.length - 1];
    if (out.length > 1 && Math.floor((last.t - from) / bin) === Math.floor((t - from) / bin)) out[out.length - 1] = p;
    else out.push(p);
  };
  // Settlements and bonuses, in time order (a bonus moves money put in, not profit)
  const events = [...mine.filter((s) => s.t >= from && s.t <= now).map((s) => ({ t: s.t, pnl: s.pnl })),
    ...h.transfers.filter((x) => x.strategy in h.starting && x.t >= from && x.t <= now).map((x) => ({ t: x.t, pnl: 0 }))]
    .sort((a, b) => a.t - b.t);
  for (const e of events) {
    profit += e.pnl;
    push(e.t);
  }
  out.push({ t: Math.max(now, out[out.length - 1].t), worth: end ?? putInAt(now) + profit, putIn: putInAt(now) });
  return out;
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

/** The same history, limited to some employees (the office pool leaves out the control group). */
export function only(h: History, keys: Iterable<string>): History {
  const keep = new Set(keys);
  const pick = <T,>(o: Record<string, T>) => Object.fromEntries(Object.entries(o).filter(([k]) => keep.has(k)));
  return { ...h, points: pick(h.points), seeds: pick(h.seeds), starting: pick(h.starting),
    transfers: h.transfers.filter((x) => keep.has(x.strategy)) };
}

/** Who's in the office pool: the bot says; before it does, everyone but the control group. */
export const poolKeys = (live: { pool?: { members: string[] }; employees: { key: string; control?: boolean }[] }) =>
  live.pool?.members ?? live.employees.filter((e) => !e.control).map((e) => e.key);

/**
 * The headline: what the book is worth and how much was put in. Shared by the website and the phone widget so
 * they never disagree. For real money it's Kalshi's own account (cash + what Kalshi says open bets are worth)
 * once this season has a check; otherwise the office pool's own figure.
 */
export function headline(live: LiveStatus, real: boolean, seasonStart: number) {
  const members = new Set(poolKeys(live));
  const team = live.employees.filter((e) => members.has(e.key));
  const check = real ? live.trading?.books ?? null : null;
  // Only a check from this season counts: an older one may be another account (the demo)
  const books = check && Date.parse(check.at) >= seasonStart ? check : null;
  // Kalshi's own two numbers: `balance` also counts payouts on their way, which Kalshi still values in `held`
  const kalshi = books ? (books.cash ?? books.balance) + (books.held ?? 0) : null;
  // ...but only while Kalshi and our books agree. A bid can fill seconds after it goes up, and Kalshi counts it
  // before our books do (up to one run, 2 min): Kalshi's figure then held a bet the open-bets list didn't show
  // (11-15, a friend's first bet: -$0.03 on the chart, nothing open). Meanwhile our own figure, which the
  // open bets come from, is used; the two agree to the cent once the fill is booked.
  const agree = books && books.ok && Math.abs(books.drift ?? 0) < 0.02;
  const own = live.pool?.equity ?? team.reduce((s, e) => s + (e.equity ?? 0), 0);
  const worth = kalshi != null && agree ? kalshi : own;
  const putIn = live.pool?.capital ?? team.reduce((s, e) => s + (e.starting_cash ?? 0), 0);
  // What the open bets in `worth` are valued at: Kalshi's figure when that's the one used, else ours from marks.
  // Bets that have ended but aren't paid yet are still in Kalshi's `held`, and in `balance` minus `cash`: not riding
  const held = kalshi != null && agree
    ? Math.max(0, (books.held ?? 0) - (books.cash != null ? books.balance - books.cash : 0)) : null;
  return { worth, putIn, profit: worth - putIn, kalshi, books, held };
}
