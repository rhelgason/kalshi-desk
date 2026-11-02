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
const hourOf = (t: number, tz: string) => Number(new Date(t).toLocaleString("en-US", { timeZone: tz, hour: "numeric", hourCycle: "h23" }));

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

/** The hour of the day (desk time) that has made the most, with enough bets to mean something. */
export function bestHour(bets: Bet[], tz: string, minBets = 8) {
  const h = [...Array(24)].map(() => ({ pnl: 0, n: 0 }));
  for (const b of bets) { const x = h[hourOf(b.t, tz)]; x.pnl += b.pnl; x.n++; }
  const ok = h.map((x, hour) => ({ hour, ...x })).filter((x) => x.n >= minBets);
  if (!ok.length) return null;
  const best = ok.reduce((a, b) => (b.pnl > a.pnl ? b : a));
  const worst = ok.reduce((a, b) => (b.pnl < a.pnl ? b : a));
  return { best, worst, hours: h };
}

export const hourLabel = (h: number) => {
  const f = (x: number) => `${x % 12 || 12}${x < 12 ? "am" : "pm"}`;
  return `${f(h)}–${f((h + 1) % 24)}`;
};

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
