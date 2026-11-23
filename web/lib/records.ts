import { dayOf } from "./season";
import { dollars } from "./format";
/**
 * Streaks and records, from every settled bet of the season (lib/db getBets). Pure functions, so the home page's
 * records card and each employee's player card read the same numbers.
 */
/**
 * A finished bet. Or a whole day of one employee's bets rolled up (lib/season.ts, for the season before the latest
 * weeks): then `n` bets, `won` of them won, `best` and `worst` the day's biggest win and loss, `t` its last bet.
 */
export type Bet = {
  t: number; strategy: string; coin: string; pnl: number; cost: number | null; price: number | null;
  n?: number; won?: number; best?: number; worst?: number;
};

const won = (b: Bet) => b.pnl > 0;
/** Bets in a list, counting a rolled-up day by what it holds. */
export const countOf = (bets: Bet[]) => bets.reduce((s, b) => s + (b.n ?? 1), 0);
export const wonOf = (bets: Bet[]) => bets.reduce((s, b) => s + (b.won ?? (won(b) ? 1 : 0)), 0);

/** Profit per dollar bet (0.021 = +2.1c per $1); null with nothing priced. */
export function perDollar(bets: Bet[]): number | null {
  let pnl = 0, cost = 0;
  for (const b of bets) if (b.cost) { pnl += b.pnl; cost += b.cost; }
  return cost ? pnl / cost : null;
}

/**
 * How sure we can be that bets make money by skill, not luck (11-16, the cockpit's "Is it working?"): each bet's
 * return per $1, then the chance its average is really above zero (a one-sided t-test, normal approximation).
 * Simpler than the desk's own evidence (desk/evidence), which the employee pages use, but the same idea.
 */
export function skillOdds(bets: Bet[]) {
  const r = bets.filter((b) => b.cost).map((b) => b.pnl / b.cost!);
  const n = r.length;
  if (n < 2) return { confidence: 0.5, verdict_key: "too_early" as const, bets: n };
  const mean = r.reduce((s, v) => s + v, 0) / n;
  const sd = Math.sqrt(r.reduce((s, v) => s + (v - mean) ** 2, 0) / (n - 1)) || 1e-9;
  const t = mean / (sd / Math.sqrt(n));
  // The normal curve's area below t (Abramowitz & Stegun 7.1.26, good to 1e-7)
  const z = Math.abs(t) / Math.SQRT2, k = 1 / (1 + 0.3275911 * z);
  const erf = 1 - (((((1.061405429 * k - 1.453152027) * k) + 1.421413741) * k - 0.284496736) * k + 0.254829592) * k * Math.exp(-z * z);
  const confidence = t >= 0 ? (1 + erf) / 2 : (1 - erf) / 2;
  return { confidence, verdict_key: t < -2 ? ("losing" as const) : ("luck" as const), bets: n };
}

/** Wins in a row: the current run (from the newest bet back) and the season's longest, with when it ended. */
export function streaks(bets: Bet[]) {
  let run = 0, best = 0, bestEnd: number | null = null;
  for (const b of bets) {
    run = won(b) ? run + 1 : 0;
    if (run > best) { best = run; bestEnd = b.t; }
  }
  let current = 0;
  for (let i = bets.length - 1; i >= 0 && won(bets[i]); i--) current++;
  return { current, best, bestEnd, currentIsBest: current > 0 && current === best };
}

const dayKey = dayOf; // YYYY-MM-DD

export type Day = { day: string; pnl: number; n: number; won: number };

/** Profit and bets per calendar day in the desk's timezone, oldest first. */
export function days(bets: Bet[], tz: string): Day[] {
  const m = new Map<string, Day>();
  for (const b of bets) {
    const k = dayKey(b.t, tz);
    const d = m.get(k) ?? { day: k, pnl: 0, n: 0, won: 0 };
    d.pnl += b.pnl; d.n += b.n ?? 1; d.won += b.won ?? (won(b) ? 1 : 0);
    m.set(k, d);
  }
  return [...m.values()].sort((a, b) => a.day.localeCompare(b.day));
}

/** The last `n` calendar days ending today, empty days included (for the day strip). */
/** How many calendar days (in tz) from the day of `since` to today, both counted: an office that opened yesterday
 *  evening has 2 days, not 1 (11-22, the owner: days are Pacific calendar days for everyone). */
export function calendarDays(since: number, tz: string, now = Date.now()): number {
  const a = Date.parse(`${dayKey(since, tz)}T00:00:00Z`), b = Date.parse(`${dayKey(now, tz)}T00:00:00Z`);
  return Math.max(1, Math.round((b - a) / 86_400_000) + 1);
}

export function lastDays(all: Day[], n: number, tz: string, now = Date.now()): Day[] {
  const by = new Map(all.map((d) => [d.day, d]));
  return [...Array(n)].map((_, i) => {
    const k = dayKey(now - (n - 1 - i) * 86_400_000, tz);
    return by.get(k) ?? { day: k, pnl: 0, n: 0, won: 0 };
  });
}

/** Days in a row that finished up, counting back from the last finished day (today counts once it's up). */
export function greenRun(all: Day[], tz: string, now = Date.now()) {
  const today = dayKey(now, tz);
  const list = all.filter((d) => d.n > 0);
  let i = list.length - 1;
  if (i >= 0 && list[i].day === today && list[i].pnl <= 0) i--; // today isn't over yet
  let run = 0;
  for (; i >= 0 && list[i].pnl > 0; i--) run++;
  return run;
}

export const biggest = (bets: Bet[]) => ({
  win: bets.map((b) => (b.best != null ? { ...b, pnl: b.best } : b))
    .reduce<Bet | null>((a, b) => (b.pnl > 0 && (!a || b.pnl > a.pnl) ? b : a), null),
  loss: bets.map((b) => (b.worst != null ? { ...b, pnl: b.worst } : b))
    .reduce<Bet | null>((a, b) => (b.pnl < 0 && (!a || b.pnl < a.pnl) ? b : a), null),
});

/** Wins it takes to earn back a loss, at this employee's (or the desk's) average win. */
export function winsToRecover(loss: number, bets: Bet[]) {
  const w = bets.filter(won);
  const avg = w.length ? w.reduce((s, b) => s + b.pnl, 0) / w.length : 0;
  return avg > 0 ? Math.ceil(Math.abs(loss) / avg) : null;
}

/**
 * One short line per employee for the team list (11-16): the most telling fact about them right now, worded plainly.
 * Team-wide firsts (best rate, busiest today) go to one person each, so neighbouring rows read differently.
 */
/**
 * Each employee's one-line caption on the team list. `bets` may be just the latest weeks (11-16: Training's whole
 * season is too much to send); then `totals` (the season added up by the database) gives the season-long numbers:
 * how many bets, the profit, the rate and the share won. Streaks and recent losses come from the bets.
 */
export function teamNotes(people: { key: string; benchedUntil?: string | null; benched?: boolean }[], bets: Bet[], tz: string,
                          now = Date.now(), totals?: Record<string, { n: number; won: number; pnl: number; cost: number }>): Record<string, string> {
  const by: Record<string, Bet[]> = {};
  for (const b of bets) (by[b.strategy] ??= []).push(b);
  const today = dayKey(now, tz);
  const short = (t: number) => new Date(t).toLocaleDateString("en-US", { timeZone: tz, month: "short", day: "numeric" });
  const count = (k: string) => totals ? totals[k]?.n ?? 0 : by[k]?.length ?? 0;
  const rate = (k: string) => count(k) < 30 ? null : totals ? (totals[k].cost ? totals[k].pnl / totals[k].cost : null) : perDollar(by[k]);
  const todays = (k: string) => (by[k] ?? []).filter((b) => dayKey(b.t, tz) === today).length;
  const top = (f: (k: string) => number | null) => {
    let best: string | null = null, v = -Infinity;
    for (const p of people) { const x = f(p.key); if (x != null && x > v && !p.benched) { v = x; best = p.key; } }
    return best;
  };
  const bestRate = top(rate), busiest = top((k) => todays(k) || null);
  const longest = top((k) => streaks(by[k] ?? []).current || null);
  const out: Record<string, string> = {};
  for (const p of people) {
    const mine = by[p.key] ?? [];
    const t = totals?.[p.key];
    const n = t ? t.n : mine.length, pnl = t ? t.pnl : mine.reduce((s, b) => s + b.pnl, 0);
    const wonAll = t ? t.won : mine.filter(won).length;
    const s = streaks(mine);
    const last = mine.length ? biggest(mine.filter((b) => now - b.t < 86_400_000)).loss : null;
    const run = greenRun(days(mine, tz), tz, now);
    out[p.key] =
      p.benched ? (p.benchedUntil && !p.benchedUntil.startsWith("9999") ? `Benched until ${short(Date.parse(p.benchedUntil))}` : "On the bench")
      : !n ? "Waiting for a first bet"
      : n < 20 ? `New here · ${n} ${n === 1 ? "bet" : "bets"} so far`
      : p.key === bestRate ? `Best rate on the team · ${((rate(p.key) ?? 0) * 100).toFixed(1)}¢ per $1`
      : p.key === longest && s.current >= 10 ? `${s.current} wins in a row, the team's longest run`
      : last ? `Lost ${dollars(-last.pnl)} ${dayKey(last.t, tz) === today ? "today" : "yesterday"}, ${winsToRecover(last.pnl, mine) ?? "a few"} wins to earn it back`
      : p.key === busiest ? `Busiest today · ${todays(p.key)} bets`
      : pnl < 0 ? `Down ${dollars(-pnl)} so far · needs a good week`
      : s.current >= 5 && s.current < mine.length ? `No loss since ${short(mine[mine.length - s.current - 1].t)} · ${s.current} wins since`
      : wonAll === n ? `Hasn't lost yet · ${n} bets`
      : run >= 3 ? `Up ${run} days running`
      : `${Math.round((wonAll / n) * 100)}% won over ${n} bets`;
  }
  return out;
}
