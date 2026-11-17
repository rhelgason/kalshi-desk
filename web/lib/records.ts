import { dollars } from "./format";
/**
 * Streaks and records, from every settled bet of the season (lib/db getBets). Pure functions, so the home page's
 * records card and each employee's player card read the same numbers.
 */
export type Bet = { t: number; strategy: string; coin: string; pnl: number; cost: number | null; price: number | null };

const won = (b: Bet) => b.pnl > 0;

/** Profit per dollar bet (0.021 = +2.1c per $1); null with nothing priced. */
export function perDollar(bets: Bet[]): number | null {
  let pnl = 0, cost = 0;
  for (const b of bets) if (b.cost) { pnl += b.pnl; cost += b.cost; }
  return cost ? pnl / cost : null;
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

const dayKey = (t: number, tz: string) => new Date(t).toLocaleDateString("en-CA", { timeZone: tz }); // YYYY-MM-DD

export type Day = { day: string; pnl: number; n: number; won: number };

/** Profit and bets per calendar day in the desk's timezone, oldest first. */
export function days(bets: Bet[], tz: string): Day[] {
  const m = new Map<string, Day>();
  for (const b of bets) {
    const k = dayKey(b.t, tz);
    const d = m.get(k) ?? { day: k, pnl: 0, n: 0, won: 0 };
    d.pnl += b.pnl; d.n++; if (won(b)) d.won++;
    m.set(k, d);
  }
  return [...m.values()].sort((a, b) => a.day.localeCompare(b.day));
}

/** The last `n` calendar days ending today, empty days included (for the day strip). */
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
  win: bets.reduce<Bet | null>((a, b) => (b.pnl > 0 && (!a || b.pnl > a.pnl) ? b : a), null),
  loss: bets.reduce<Bet | null>((a, b) => (b.pnl < 0 && (!a || b.pnl < a.pnl) ? b : a), null),
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
export function teamNotes(people: { key: string; benchedUntil?: string | null; benched?: boolean }[], bets: Bet[], tz: string,
                          now = Date.now()): Record<string, string> {
  const by: Record<string, Bet[]> = {};
  for (const b of bets) (by[b.strategy] ??= []).push(b);
  const today = dayKey(now, tz);
  const short = (t: number) => new Date(t).toLocaleDateString("en-US", { timeZone: tz, month: "short", day: "numeric" });
  const rate = (k: string) => (by[k]?.length ?? 0) >= 30 ? perDollar(by[k]) : null;
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
    const n = mine.length, pnl = mine.reduce((s, b) => s + b.pnl, 0);
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
      : s.current >= 5 && s.current < n ? `No loss since ${short(mine[n - s.current - 1].t)} · ${s.current} wins since`
      : s.current === n ? `Hasn't lost yet · ${n} bets`
      : run >= 3 ? `Up ${run} days running`
      : `${Math.round((mine.filter(won).length / n) * 100)}% won over ${n} bets`;
  }
  return out;
}
