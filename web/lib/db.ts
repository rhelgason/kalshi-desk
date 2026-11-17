import { unstable_cache } from "next/cache";
import { cache } from "react";
import postgres from "postgres";
import { LEVELS, mergePolicy } from "./hr";
import { coinOfTicker } from "./coin";
import type { Bet } from "./records";
import { binFor, RANGES, type History, type RangeKey, type Settlement } from "./portfolio";
import type {
  Accuracy, BacktestSummary, Evidence, Fill, LiveStatus, MoneyMove, NewsItem, Point, Policy, Realism, RosterRow, TuningRun,
} from "./types";

// Use Supabase's SESSION pooler (port 5432) for the dashboard. Through the
// transaction pooler (6543), back-to-back queries on one connection could lose
// their responses under concurrent page loads, leaving connections stuck
// (and those stuck queries then blocked the bot). prepare:false and
// fetch_types:false keep each connection's setup minimal.
const globalForDb = globalThis as unknown as { sql?: ReturnType<typeof postgres> };

function connection() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is not set");
  if (!globalForDb.sql) {
    const local = /localhost|127\.0\.0\.1|%2F|\/tmp/.test(url);
    // max: 2 per instance. Supabase's session pooler allows 15 clients in all, and idle
    // Vercel instances hold theirs: max 5 once locked the dashboard out for 10+ minutes.
    globalForDb.sql = postgres(url, {
      prepare: false, max: 2, fetch_types: false, idle_timeout: 10, connect_timeout: 10,
      ssl: local ? false : "require",
    });
  }
  return globalForDb.sql;
}

// Each book's own tables (desk/paper/ledger.py BOOK_TABLES); market data is shared and stays in public
const BOOK_TABLES = ["accounts", "fills", "settlements", "equity", "events", "status", "transfers", "employees",
  "settings", "decisions", "market_tape", "runs", "orders"];
const BOOK_TABLE_RE = new RegExp(`\\b(FROM|INTO|UPDATE|JOIN|TABLE|EXISTS|ON)(\\s+)(${BOOK_TABLES.join("|")})\\b(?!\\.)`, "gi");

/** The owner's two books, or a friend's office (desk/offices.py: real money in the friend's own Kalshi account). */
export type Book = "real" | "pretend" | `office_${string}`;
type Tag = (strings: TemplateStringsArray, ...values: any[]) => postgres.PendingQuery<postgres.Row[]>;

const OFFICE_RE = /^office_[a-z][a-z0-9]{1,23}$/;
export const isOffice = (b: unknown): b is `office_${string}` => typeof b === "string" && OFFICE_RE.test(b);
export const isBook = (b: unknown): b is Book => b === "real" || b === "pretend" || isOffice(b);
/** Real money: the owner's real book or a friend's office (numbers from a Kalshi account). */
export const isLive = (b: Book) => b !== "pretend";

/** The shared tables in public (users, sessions, offices...), outside any book. */
export const home = () => connection();

/**
 * Queries against one book. The real-money book's tables live in the "real" schema, and an office's in its own,
 * so their queries name it: "FROM fills" becomes "FROM real.fills".
 */
export function db(book: Book = "pretend"): Tag {
  const sql = connection();
  if (book === "pretend") return sql as unknown as Tag;
  if (!isBook(book)) throw new Error(`no such book: ${book}`);
  return (strings, ...values) => {
    const named = strings.map((s) => s.replace(BOOK_TABLE_RE, `$1$2${book}.$3`));
    return sql(Object.assign(named, { raw: named }) as unknown as TemplateStringsArray, ...values);
  };
}

/**
 * Sturdy reads. Every page load used to ask the database again, and when its connection limit
 * filled up (15 for everyone, see connection()) every page showed an error. Now each read is
 * kept for a short while and shared by all visitors and the widget:
 *  - a copy under FRESH_MS old is used as is (the bot only reports every 2 minutes anyway);
 *  - an older copy: ask the database again, but if it's down or slow, show the old copy
 *    instead of an error page.
 * Manager changes (app/actions.ts) clear the copies straight away (revalidateTag).
 * A book's reads are also keyed by when its bot last reported (11-16, `reported`): one tiny query per page load,
 * so a refresh after the bot's run reads everything afresh, and between runs the copies serve.
 */
const FRESH_MS = 60_000;
const TRY_MS = 3_000;
const REST_MS = 30_000; // after the database fails to answer, don't wait on it again for this long
let downUntil = 0;
export const bookTag = (book: Book | "shared") => `db:${book}`;

/** When the book's bot last wrote its status (once per page load); null if the database doesn't answer quickly. */
const reported = cache(async (book: Book): Promise<string | null> => {
  if (Date.now() < downUntil) return null;
  try {
    const rows = await Promise.race([
      db(book)`SELECT updated_at FROM status WHERE key = 'live'`,
      new Promise<never>((_, no) => setTimeout(() => no(new Error("database slow")), TRY_MS)),
    ]);
    return rows.length ? String(rows[0].updated_at) : null;
  } catch {
    return null;
  }
});

function sturdy<A extends unknown[], R>(name: string, query: (...a: A) => Promise<R>): (...a: A) => Promise<R> {
  return async (...a: A) => {
    const book = isBook(a[0]) ? a[0] : "shared";
    const stamp = book === "shared" ? null : await reported(book);
    const kept = unstable_cache(async () => ({ at: Date.now(), v: await query(...a) }), [name, JSON.stringify(a), stamp ?? ""],
      { revalidate: stamp ? 600 : 30, tags: [bookTag(book)] });
    const copy = await kept();
    // Nothing new since the bot's last report: this copy is the latest there is
    if (stamp || Date.now() - copy.at < FRESH_MS || Date.now() < downUntil) return copy.v;
    try {
      return await Promise.race([
        query(...a),
        new Promise<never>((_, no) => setTimeout(() => no(new Error("database slow")), TRY_MS)),
      ]);
    } catch (e) {
      downUntil = Date.now() + REST_MS;
      console.warn(`${name}: showing a copy from ${Math.round((Date.now() - copy.at) / 1000)}s ago (${e})`);
      return copy.v;
    }
  };
}

async function statusQuery(book: Book, key: string): Promise<unknown> {
  const rows = await db(book)`SELECT data FROM status WHERE key = ${key}`;
  return rows.length ? JSON.parse(rows[0].data) : null;
}
const statusRow = sturdy("status", statusQuery);
const status = async <T,>(book: Book, key: string) => (await statusRow(book, key)) as T | null;

export const getLive = (book: Book) => status<LiveStatus>(book, "live");

/** The weekly bonus pot (desk/bonus.py): money saved up, and what the Employee of the Week has left to bet. */
export type BonusPot = { pot: number; winner: string | null; given: number; left: number; since: string | null };
export const getBonusPot = async (book: Book): Promise<BonusPot> =>
  (await status<BonusPot>(book, "_bonus_pot")) ?? { pot: 0, winner: null, given: 0, left: 0, since: null };

/** The kill switch straight from the table (the bot's status lags a run behind a press of the button). */
export type KillSwitch = { halted: boolean; reason?: string; by?: string; at?: string; long?: boolean };
export async function getKillSwitch(book: Book): Promise<KillSwitch> {
  const rows = await db(book)`SELECT data FROM settings WHERE key = 'trading'`;
  return rows.length ? JSON.parse(rows[0].data) : { halted: false };
}

/** A long pause (marked long, or halted for over a day), not an afternoon's stop: show Training meanwhile. */
export function isLongPause(kill: KillSwitch, now = Date.now()): boolean {
  if (!kill.halted) return false;
  return !!kill.long || (!!kill.at && now - Date.parse(kill.at) > 24 * 3_600_000);
}

async function getPolicyQuery(book: Book): Promise<Policy> {
  const rows = await db(book)`SELECT data FROM settings WHERE key = 'desk'`;
  return mergePolicy(rows.length ? JSON.parse(rows[0].data) : null);
}

/** HR records straight from the table, so admin changes show up before the bot's next run. */
async function getRosterQuery(book: Book): Promise<Record<string, RosterRow>> {
  const rows = await db(book)`SELECT * FROM employees`;
  return Object.fromEntries(
    rows.map((r) => [
      r.key,
      { ...r, params: JSON.parse(r.params || "{}"), autotune: !!r.autotune, control: !!r.control } as RosterRow,
    ]),
  );
}

async function getNewsQuery(book: Book, limit = 30, strategy?: string): Promise<NewsItem[]> {
  const rows = await db(book)`
    SELECT id, ts, strategy, kind, detail FROM events
    WHERE kind IN ('hr', 'award', 'tune', 'review', 'season', 'admin', 'money')
    ${strategy ? db(book)`AND strategy = ${strategy}` : db(book)``}
    ORDER BY id DESC LIMIT ${limit}`;
  return rows.map((r) => ({ ...r, detail: safeJson(r.detail) })) as NewsItem[];
}

async function getTuningRunsQuery(strategy: string, limit = 5): Promise<TuningRun[]> {
  const rows = await db()`SELECT id, created_at, strategy, summary FROM tuning_runs
    WHERE strategy = ${strategy} ORDER BY id DESC LIMIT ${limit}`;
  return rows.map((r) => ({ ...r, summary: JSON.parse(r.summary) })) as TuningRun[];
}

async function getJobsQuery(): Promise<{ finished_at: string; [k: string]: any } | null> {
  return status("pretend", "jobs"); // the background jobs report to the pretend book
}

async function getCoverageQuery(): Promise<{ series: string; markets: number; oldest: number; newest: number }[]> {
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
async function getAnalysisQuery(book: Book) {
  const a = await status<AccuracyStatus>(book, "accuracy");
  return { accuracy: a?.summaries ?? [], evidence: a?.evidence ?? {}, realism: a?.realism ?? {} };
}
export const getAccuracy = async (book: Book) => (await getAnalysis(book)).accuracy;

// Note: never `await` inside a sql`` template. Building a query that pauses
// mid-way (while other queries share the connection) can leave it half-sent.

/** When the season's first snapshot was taken (ms), or null before any. */
async function getSeasonStartQuery(book: Book, season: number): Promise<number | null> {
  const rows = await db(book)`SELECT min(ts) AS ts FROM equity WHERE season = ${season}`;
  return rows[0]?.ts ? Date.parse(rows[0].ts) : null;
}

/**
 * Every employee's account value over a time range, one point per time bucket
 * (spacing picked by binFor), plus what's needed to work out money put in.
 */
async function getHistoryQuery(book: Book, season: number, range: RangeKey): Promise<History> {
  const days = RANGES[range].days;
  let sinceMs: number;
  if (days == null) {
    sinceMs = (await getSeasonStart(book, season)) ?? Date.now() - 86_400_000;
  } else {
    sinceMs = Date.now() - days * 86_400_000;
  }
  const since = new Date(sinceMs).toISOString();
  const bin = binFor(Date.now() - sinceMs);
  const [rows, seeds, accounts, transfers, staffRows] = await Promise.all([
    db(book)`
      SELECT DISTINCT ON (strategy, b) strategy, b, ts, equity FROM (
        SELECT strategy, ts, equity,
               date_bin(${bin}::interval, ts::timestamptz, timestamptz '2000-01-01') AS b
        FROM equity WHERE season = ${season} AND ts >= ${since}
      ) x
      ORDER BY strategy, b, ts DESC`,
    db(book)`
      SELECT a.strategy, e.equity FROM accounts a
      CROSS JOIN LATERAL (
        SELECT equity FROM equity
        WHERE strategy = a.strategy AND season = ${season} AND ts < ${since}
        ORDER BY ts DESC LIMIT 1
      ) e`,
    db(book)`SELECT strategy, starting_cash FROM accounts`,
    db(book)`SELECT ts, strategy, amount FROM transfers WHERE season = ${season} ORDER BY ts`,
    // Who's on staff now: retired employees' old rows shouldn't count toward the totals
    db(book)`SELECT e->>'key' AS key FROM status, jsonb_array_elements(data::jsonb -> 'employees') e WHERE status.key = 'live'`,
  ]);
  const staff = new Set(staffRows.map((r) => r.key as string));
  const onStaff = (k: string) => !staff.size || staff.has(k);
  const points: History["points"] = {};
  for (const r of rows) {
    if (!onStaff(r.strategy)) continue;
    (points[r.strategy] ??= []).push({ b: new Date(r.b).getTime(), t: Date.parse(r.ts), equity: Number(r.equity) });
  }
  for (const k of Object.keys(points)) points[k].sort((a, b) => a.b - b.b);
  return {
    since: sinceMs,
    points,
    seeds: Object.fromEntries(seeds.filter((r) => onStaff(r.strategy)).map((r) => [r.strategy, Number(r.equity)])),
    starting: Object.fromEntries(accounts.filter((r) => onStaff(r.strategy)).map((r) => [r.strategy, Number(r.starting_cash)])),
    transfers: transfers.filter((r) => onStaff(r.strategy)).map((r) => ({ t: Date.parse(r.ts), strategy: r.strategy, amount: Number(r.amount) })),
  };
}

async function getRecentFillsQuery(book: Book, season: number, limit = 30, strategy?: string): Promise<Fill[]> {
  // One row per bet: Kalshi can fill one bid in pieces, and each piece would otherwise repeat the bet's whole result
  const rows = await db(book)`
    SELECT max(f.id) AS id, max(f.ts) AS ts, f.strategy, f.ticker, f.side, sum(f.count) AS count,
           sum(f.count * f.price) / nullif(sum(f.count), 0) AS price, sum(f.fee) AS fee, max(f.model_prob) AS model_prob,
           max(f.reason) AS reason, s.yes_value, s.pnl
    FROM fills f
    LEFT JOIN settlements s ON s.strategy = f.strategy AND s.ticker = f.ticker AND s.season = f.season
    WHERE f.season = ${season} ${strategy ? db(book)`AND f.strategy = ${strategy}` : db(book)``}
      -- Only the newest fills (a few per bet at most), not the whole season's (11-16: 2.7 s on Training)
      AND f.id >= (SELECT coalesce(min(id), 0) FROM (
        SELECT id FROM fills WHERE season = ${season} ${strategy ? db(book)`AND strategy = ${strategy}` : db(book)``}
        ORDER BY id DESC LIMIT ${limit * 4}) newest)
    GROUP BY f.strategy, f.ticker, f.side, s.yes_value, s.pnl
    ORDER BY max(f.id) DESC LIMIT ${limit}`;
  return rows.map((r) => ({ ...r, count: Number(r.count), price: Number(r.price), fee: Number(r.fee) })) as Fill[];
}

// Days start at midnight in the manager's time zone
const DESK_TZ = "America/Vancouver";

export type SettlementStats = {
  wins: number;
  losses: number;
  won: number; // dollars made on winning bets
  lost: number; // dollars lost on losing bets (negative)
  days: { day: string; pnl: number; bets: number }[];
};

/** Finished bets for one employee this season: wins vs losses and profit per day. */
async function getSettlementStatsQuery(book: Book, season: number, strategy: string): Promise<SettlementStats> {
  const [totals, days] = await Promise.all([
    db(book)`
      SELECT count(*) FILTER (WHERE pnl > 0)::int AS wins, count(*) FILTER (WHERE pnl <= 0)::int AS losses,
             coalesce(sum(pnl) FILTER (WHERE pnl > 0), 0) AS won, coalesce(sum(pnl) FILTER (WHERE pnl <= 0), 0) AS lost
      FROM settlements WHERE season = ${season} AND strategy = ${strategy}`,
    db(book)`
      SELECT to_char(ts::timestamptz AT TIME ZONE ${DESK_TZ}, 'YYYY-MM-DD') AS day, sum(pnl) AS pnl, count(*)::int AS bets
      FROM settlements WHERE season = ${season} AND strategy = ${strategy}
      GROUP BY 1 ORDER BY 1`,
  ]);
  const t = totals[0];
  return {
    wins: t.wins, losses: t.losses, won: Number(t.won), lost: Number(t.lost),
    days: days.map((r) => ({ day: r.day, pnl: Number(r.pnl), bets: r.bets })),
  };
}

/**
 * Settled bets this season with what they cost (fills joined by employee and market): records and player cards.
 * With `since` (ISO), only bets settled from then (11-16: Training's season is ~40,000 bets, 5 MB, far too much to
 * send for a week's page); their fills are looked for from a few days earlier (weather bets fill a day or so ahead).
 */
async function getBetsQuery(book: Book, season: number, since?: string | null, strategy?: string): Promise<Bet[]> {
  const fillsFrom = since ? new Date(Date.parse(since) - 4 * 86_400_000).toISOString() : null;
  const rows = await db(book)`
    SELECT s.ts, s.strategy, s.ticker, s.pnl, f.cost, f.price
    FROM settlements s
    LEFT JOIN (
      SELECT strategy, ticker, sum(count * price + fee) AS cost, max(price) AS price
      FROM fills WHERE season = ${season} ${fillsFrom ? db(book)`AND ts >= ${fillsFrom}` : db(book)``}
        ${strategy ? db(book)`AND strategy = ${strategy}` : db(book)``}
      GROUP BY strategy, ticker
    ) f ON f.strategy = s.strategy AND f.ticker = s.ticker
    WHERE s.season = ${season} ${since ? db(book)`AND s.ts >= ${since}` : db(book)``}
      ${strategy ? db(book)`AND s.strategy = ${strategy}` : db(book)``}
    ORDER BY s.ts`;
  return rows.map((r) => ({
    t: Date.parse(r.ts), strategy: r.strategy, coin: coinOfTicker(r.ticker), pnl: Number(r.pnl),
    cost: r.cost == null ? null : Number(r.cost), price: r.price == null ? null : Number(r.price),
  }));
}

/** An employee's whole season in four numbers, added up by the database (11-16): bets, wins, profit, money bet. */
export type Totals = { n: number; won: number; pnl: number; cost: number };

async function getTotalsQuery(book: Book, season: number): Promise<Record<string, Totals>> {
  const rows = await db(book)`
    SELECT s.strategy, count(*)::int AS n, count(*) FILTER (WHERE s.pnl > 0)::int AS won, sum(s.pnl) AS pnl,
           coalesce(sum(f.cost), 0) AS cost
    FROM settlements s
    LEFT JOIN (
      SELECT strategy, ticker, sum(count * price + fee) AS cost FROM fills WHERE season = ${season} GROUP BY strategy, ticker
    ) f ON f.strategy = s.strategy AND f.ticker = s.ticker
    WHERE s.season = ${season}
    GROUP BY s.strategy`;
  return Object.fromEntries(rows.map((r) => [r.strategy, { n: r.n, won: r.won, pnl: Number(r.pnl), cost: Number(r.cost) }]));
}
export const getTotals = sturdy("getTotals", getTotalsQuery);

/** Deposits and withdrawals this season (one per move: the bot writes each employee's share at the same moment). */
async function getMoneyMovesQuery(book: Book, season: number): Promise<MoneyMove[]> {
  const rows = await db(book)`
    SELECT ts, sum(amount) AS amount FROM transfers
    WHERE season = ${season} AND reason IN ('deposit', 'withdrawal') GROUP BY ts ORDER BY ts`;
  return rows.map((r) => ({ t: Date.parse(r.ts), amount: Number(r.amount) }));
}

export type Activity = {
  lastFill: { ts: string; side: string; count: number; price: number } | null;
  betsLastHour: number;
  pnlLastHour: number;
  settledLastHour: number;
};

/** What each employee has been up to lately, for the office floor. */
async function getActivityQuery(book: Book, season: number): Promise<Record<string, Activity>> {
  const hourAgo = new Date(Date.now() - 3_600_000).toISOString();
  const [last, recent, settled] = await Promise.all([
    db(book)`SELECT DISTINCT ON (strategy) strategy, ts, side, count, price FROM fills
         WHERE season = ${season} ORDER BY strategy, id DESC`,
    db(book)`SELECT strategy, count(*)::int AS n FROM fills WHERE season = ${season} AND ts >= ${hourAgo} GROUP BY strategy`,
    db(book)`SELECT strategy, sum(pnl) AS pnl, count(*)::int AS n FROM settlements
         WHERE season = ${season} AND ts >= ${hourAgo} GROUP BY strategy`,
  ]);
  const out: Record<string, Activity> = {};
  const get = (k: string) => (out[k] ??= { lastFill: null, betsLastHour: 0, pnlLastHour: 0, settledLastHour: 0 });
  for (const r of last) get(r.strategy).lastFill = { ts: r.ts, side: r.side, count: Number(r.count), price: Number(r.price) };
  for (const r of recent) get(r.strategy).betsLastHour = r.n;
  for (const r of settled) Object.assign(get(r.strategy), { pnlLastHour: Number(r.pnl), settledLastHour: r.n });
  return out;
}

async function getSettledCountQuery(book: Book, season: number): Promise<number> {
  const rows = await db(book)`SELECT count(*)::int AS n FROM settlements WHERE season = ${season}`;
  return rows[0].n;
}

async function listBacktestsQuery(): Promise<{ id: string; created_at: string; summary: BacktestSummary }[]> {
  const rows = await db()`SELECT id, created_at, summary FROM backtests ORDER BY id DESC LIMIT 50`;
  return rows.map((r) => ({ id: r.id, created_at: r.created_at, summary: JSON.parse(r.summary) }));
}

async function getBacktestQuery(id: string): Promise<BacktestSummary | null> {
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

/** Bitcoin's price over the last few hours, from the bot's market tape (for the office TV). */
async function getBtcSeriesQuery(book: Book, hours = 3): Promise<Point[]> {
  const since = new Date(Date.now() - hours * 3_600_000).toISOString();
  try {
    const rows = await db(book)`SELECT ts, max(spot) AS spot FROM market_tape WHERE ts >= ${since} AND spot IS NOT NULL
                            GROUP BY ts ORDER BY ts`;
    return rows.map((r) => ({ t: Date.parse(r.ts), v: Number(r.spot) }));
  } catch {
    return [];
  }
}

/** Bets settled and won by the pool's members, today (in the pool's time zone) and all season. */
async function getPoolRecordQuery(book: Book, season: number, members: string[], tz: string) {
  // Grouped by employee and filtered here: with fetch_types off, postgres.js can't send an array parameter
  const rows = await db(book)`
    SELECT strategy, count(*)::int AS n, coalesce(sum(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0)::int AS won,
           count(*) FILTER (WHERE (ts::timestamptz AT TIME ZONE ${tz})::date = (now() AT TIME ZONE ${tz})::date)::int AS n_today,
           coalesce(sum(CASE WHEN pnl > 0 AND (ts::timestamptz AT TIME ZONE ${tz})::date = (now() AT TIME ZONE ${tz})::date
                        THEN 1 ELSE 0 END), 0)::int AS won_today
    FROM settlements WHERE season = ${season} GROUP BY strategy`;
  const mine = rows.filter((r) => members.includes(r.strategy));
  const sum = (k: string) => mine.reduce((s, r) => s + Number(r[k]), 0);
  return { today: { n: sum("n_today"), won: sum("won_today") }, season: { n: sum("n"), won: sum("won") } };
}

export type CoinRow = { strategy: string; coin: string; n: number; won: number; pnl: number };

/** Settled bets per employee per coin ("BTC", "ETH"), from each market's series (KXBTC15M-... is bitcoin). */
async function getCoinStatsQuery(book: Book, season: number): Promise<CoinRow[]> {
  const rows = await db(book)`
    SELECT strategy, split_part(ticker, '-', 1) AS series, count(*)::int AS n,
           coalesce(sum(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0)::int AS won, coalesce(sum(pnl), 0) AS pnl
    FROM settlements WHERE season = ${season} GROUP BY 1, 2`;
  return rows.map((r) => ({ strategy: r.strategy, coin: coinOfTicker(r.series), n: r.n, won: r.won, pnl: Number(r.pnl) }));
}

/** Every settled bet this season since `sinceIso`, oldest first: what the coin views add up. */
async function getSettlementsQuery(book: Book, season: number, sinceIso = "1970-01-01"): Promise<Settlement[]> {
  const rows = await db(book)`SELECT ts, strategy, ticker, pnl FROM settlements
    WHERE season = ${season} AND ts >= ${sinceIso} ORDER BY ts`;
  return rows.map((r) => ({ t: Date.parse(r.ts), strategy: r.strategy, coin: coinOfTicker(r.ticker), pnl: Number(r.pnl) }));
}

/**
 * The same, but only bets since `sinceIso` one by one: everything earlier arrives as one row per employee
 * and coin, timed just before `sinceIso`, carrying their profit, bet count (`n`) and wins (`won`) up to then.
 * Enough for charts that start at `sinceIso` and for lifetime totals, and far less to download than a
 * seeded season's ~35k bets on every page view (Supabase's free plan allows 5 GB of downloads a month).
 */
async function getSettlementsSinceQuery(book: Book, season: number, sinceIso: string): Promise<Settlement[]> {
  const before = await db(book)`SELECT strategy, split_part(ticker, '-', 1) AS series, coalesce(sum(pnl), 0) AS pnl,
      count(*)::int AS n, coalesce(sum(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0)::int AS won
    FROM settlements WHERE season = ${season} AND ts < ${sinceIso} GROUP BY 1, 2`;
  const t0 = Date.parse(sinceIso) - 1;
  return [
    ...before.map((r) => ({ t: t0, strategy: r.strategy, coin: coinOfTicker(r.series), pnl: Number(r.pnl), n: r.n, won: r.won })),
    ...(await getSettlementsQuery(book, season, sinceIso)),
  ];
}

// The exported, sturdy versions (see sturdy() above)
export const getPolicy = sturdy("getPolicy", getPolicyQuery);
export const getRoster = sturdy("getRoster", getRosterQuery);
export const getNews = sturdy("getNews", getNewsQuery);
export const getTuningRuns = sturdy("getTuningRuns", getTuningRunsQuery);
export const getJobs = sturdy("getJobs", getJobsQuery);
export const getCoverage = sturdy("getCoverage", getCoverageQuery);
export const getAnalysis = sturdy("getAnalysis", getAnalysisQuery);
export const getSeasonStart = sturdy("getSeasonStart", getSeasonStartQuery);
export const getHistory = sturdy("getHistory", getHistoryQuery);
export const getRecentFills = sturdy("getRecentFills", getRecentFillsQuery);
export const getSettlementStats = sturdy("getSettlementStats", getSettlementStatsQuery);
export const getActivity = sturdy("getActivity", getActivityQuery);
export const getSettledCount = sturdy("getSettledCount", getSettledCountQuery);
export const listBacktests = sturdy("listBacktests", listBacktestsQuery);
export const getBacktest = sturdy("getBacktest", getBacktestQuery);
export const getBtcSeries = sturdy("getBtcSeries", getBtcSeriesQuery);
export const getPoolRecord = sturdy("getPoolRecord", getPoolRecordQuery);
export const getCoinStats = sturdy("getCoinStats", getCoinStatsQuery);
export const getSettlements = sturdy("getSettlements", getSettlementsQuery);
export const getBets = sturdy("getBets", getBetsQuery);
export const getMoneyMoves = sturdy("getMoneyMoves", getMoneyMovesQuery);
export const getSettlementsSince = sturdy("getSettlementsSince", getSettlementsSinceQuery);

/** Each employee's bets settled today (in the pool's timezone): the widget's "today" story. */
export const getTodayRows = sturdy("getTodayRows", async (book: Book, season: number, tz: string) =>
  (await db(book)`SELECT strategy, count(*)::int AS n, sum(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::int AS won, sum(pnl) AS pnl
     FROM settlements
     WHERE season = ${season}
       AND (ts::timestamptz AT TIME ZONE ${tz})::date = (now() AT TIME ZONE ${tz})::date
     GROUP BY strategy`).map((r) => ({ strategy: String(r.strategy), n: Number(r.n), won: Number(r.won), pnl: Number(r.pnl) })));
