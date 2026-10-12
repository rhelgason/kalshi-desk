import postgres from "postgres";
import { LEVELS, mergePolicy } from "./hr";
import { binFor, RANGES, type History, type RangeKey } from "./portfolio";
import type {
  Accuracy, BacktestSummary, Evidence, Fill, LiveStatus, NewsItem, Policy, Realism, RosterRow, TuningRun,
} from "./types";

// Use Supabase's SESSION pooler (port 5432) for the dashboard. Through the
// transaction pooler (6543), back-to-back queries on one connection could lose
// their responses under concurrent page loads, leaving connections stuck
// (and those stuck queries then blocked the bot). prepare:false and
// fetch_types:false keep each connection's setup minimal.
const globalForDb = globalThis as unknown as { sql?: ReturnType<typeof postgres> };

export function db() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is not set");
  if (!globalForDb.sql) {
    const local = /localhost|127\.0\.0\.1|%2F|\/tmp/.test(url);
    globalForDb.sql = postgres(url, {
      prepare: false, max: 2, fetch_types: false, idle_timeout: 10, connect_timeout: 10,
      ssl: local ? false : "require",
    });
  }
  return globalForDb.sql;
}

async function status<T>(key: string): Promise<T | null> {
  const rows = await db()`SELECT data FROM status WHERE key = ${key}`;
  return rows.length ? (JSON.parse(rows[0].data) as T) : null;
}

export const getLive = () => status<LiveStatus>("live");

export async function getPolicy(): Promise<Policy> {
  const rows = await db()`SELECT data FROM settings WHERE key = 'desk'`;
  return mergePolicy(rows.length ? JSON.parse(rows[0].data) : null);
}

/** HR records straight from the table, so admin changes show up before the bot's next run. */
export async function getRoster(): Promise<Record<string, RosterRow>> {
  const rows = await db()`SELECT * FROM employees`;
  return Object.fromEntries(
    rows.map((r) => [
      r.key,
      { ...r, params: JSON.parse(r.params || "{}"), autotune: !!r.autotune, control: !!r.control } as RosterRow,
    ]),
  );
}

export async function getNews(limit = 30, strategy?: string): Promise<NewsItem[]> {
  const rows = await db()`
    SELECT id, ts, strategy, kind, detail FROM events
    WHERE kind IN ('hr', 'award', 'tune', 'review', 'season', 'admin')
    ${strategy ? db()`AND strategy = ${strategy}` : db()``}
    ORDER BY id DESC LIMIT ${limit}`;
  return rows.map((r) => ({ ...r, detail: safeJson(r.detail) })) as NewsItem[];
}

export async function getTuningRuns(strategy: string, limit = 5): Promise<TuningRun[]> {
  const rows = await db()`SELECT id, created_at, strategy, summary FROM tuning_runs
    WHERE strategy = ${strategy} ORDER BY id DESC LIMIT ${limit}`;
  return rows.map((r) => ({ ...r, summary: JSON.parse(r.summary) })) as TuningRun[];
}

export async function getJobs(): Promise<{ finished_at: string; [k: string]: any } | null> {
  return status("jobs");
}

export async function getCoverage(): Promise<{ series: string; markets: number; oldest: number; newest: number }[]> {
  const rows = await db()`SELECT series, count(*)::int AS markets, min(close_ts)::bigint AS oldest,
    max(close_ts)::bigint AS newest FROM market_history GROUP BY series ORDER BY series`;
  return rows.map((r) => ({ series: r.series, markets: r.markets, oldest: Number(r.oldest), newest: Number(r.newest) }));
}

function safeJson(text: string | null): Record<string, any> {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { text };
  }
}

type AccuracyStatus = {
  updated_at: string;
  summaries: Accuracy[];
  evidence?: Record<string, Evidence>;
  realism?: Record<string, Realism>;
};

/** Accuracy, skill-or-luck evidence, and the fill reality check (refreshed every ~30 min by the bot). */
export async function getAnalysis() {
  const a = await status<AccuracyStatus>("accuracy");
  return { accuracy: a?.summaries ?? [], evidence: a?.evidence ?? {}, realism: a?.realism ?? {} };
}
export const getAccuracy = async () => (await getAnalysis()).accuracy;

// Note: never `await` inside a sql`` template. Building a query that pauses
// mid-way (while other queries share the connection) can leave it half-sent.

/** When the season's first snapshot was taken (ms), or null before any. */
export async function getSeasonStart(season: number): Promise<number | null> {
  const rows = await db()`SELECT min(ts) AS ts FROM equity WHERE season = ${season}`;
  return rows[0]?.ts ? Date.parse(rows[0].ts) : null;
}

/**
 * Every employee's account value over a time range, one point per time bucket
 * (spacing picked by binFor), plus what's needed to work out money put in.
 */
export async function getHistory(season: number, range: RangeKey): Promise<History> {
  const days = RANGES[range].days;
  let sinceMs: number;
  if (days == null) {
    sinceMs = (await getSeasonStart(season)) ?? Date.now() - 86_400_000;
  } else {
    sinceMs = Date.now() - days * 86_400_000;
  }
  const since = new Date(sinceMs).toISOString();
  const bin = binFor(Date.now() - sinceMs);
  const [rows, seeds, accounts, transfers] = await Promise.all([
    db()`
      SELECT DISTINCT ON (strategy, b) strategy, b, ts, equity FROM (
        SELECT strategy, ts, equity,
               date_bin(${bin}::interval, ts::timestamptz, timestamptz '2000-01-01') AS b
        FROM equity WHERE season = ${season} AND ts >= ${since}
      ) x
      ORDER BY strategy, b, ts DESC`,
    db()`
      SELECT a.strategy, e.equity FROM accounts a
      CROSS JOIN LATERAL (
        SELECT equity FROM equity
        WHERE strategy = a.strategy AND season = ${season} AND ts < ${since}
        ORDER BY ts DESC LIMIT 1
      ) e`,
    db()`SELECT strategy, starting_cash FROM accounts`,
    db()`SELECT ts, strategy, amount FROM transfers WHERE season = ${season} ORDER BY ts`,
  ]);
  const points: History["points"] = {};
  for (const r of rows) {
    (points[r.strategy] ??= []).push({ b: new Date(r.b).getTime(), t: Date.parse(r.ts), equity: Number(r.equity) });
  }
  for (const k of Object.keys(points)) points[k].sort((a, b) => a.b - b.b);
  return {
    since: sinceMs,
    points,
    seeds: Object.fromEntries(seeds.map((r) => [r.strategy, Number(r.equity)])),
    starting: Object.fromEntries(accounts.map((r) => [r.strategy, Number(r.starting_cash)])),
    transfers: transfers.map((r) => ({ t: Date.parse(r.ts), strategy: r.strategy, amount: Number(r.amount) })),
  };
}

export async function getRecentFills(season: number, limit = 30, strategy?: string): Promise<Fill[]> {
  const rows = await db()`
    SELECT f.id, f.ts, f.strategy, f.ticker, f.side, f.count, f.price, f.fee, f.model_prob, f.reason,
           s.yes_value, s.pnl
    FROM fills f
    LEFT JOIN settlements s ON s.strategy = f.strategy AND s.ticker = f.ticker AND s.season = f.season
    WHERE f.season = ${season} ${strategy ? db()`AND f.strategy = ${strategy}` : db()``}
    ORDER BY f.id DESC LIMIT ${limit}`;
  return rows.map((r) => ({ ...r, count: Number(r.count), price: Number(r.price), fee: Number(r.fee) })) as Fill[];
}

export async function getSettledCount(season: number): Promise<number> {
  const rows = await db()`SELECT count(*)::int AS n FROM settlements WHERE season = ${season}`;
  return rows[0].n;
}

export async function listBacktests(): Promise<{ id: string; created_at: string; summary: BacktestSummary }[]> {
  const rows = await db()`SELECT id, created_at, summary FROM backtests ORDER BY id DESC LIMIT 50`;
  return rows.map((r) => ({ id: r.id, created_at: r.created_at, summary: JSON.parse(r.summary) }));
}

export async function getBacktest(id: string): Promise<BacktestSummary | null> {
  const rows = await db()`SELECT summary FROM backtests WHERE id = ${id}`;
  return rows.length ? JSON.parse(rows[0].summary) : null;
}

/** Live employee stats with the latest HR fields from the table (admin edits show immediately). */
export function withRoster<T extends { key: string }>(employees: T[], roster: Record<string, RosterRow>) {
  return employees.map((e) => {
    const r = roster[e.key];
    if (!r) return e;
    const params = (e as { params?: Record<string, unknown> }).params;
    const lvl = LEVELS[Math.max(0, Math.min(r.level, LEVELS.length - 1))];
    return {
      ...e, status: r.status, suspended_until: r.suspended_until, level: r.level,
      level_title: lvl.title, multiplier: lvl.multiplier,
      strikes: r.strikes, awards: r.awards, control: r.control, autotune: r.autotune, note: r.note, overrides: r.params,
      // Saved overrides win over the bot's last snapshot, so edits show before its next run
      ...(params ? { params: { ...params, ...r.params } } : {}),
    };
  });
}
