/**
 * The what-if replay (11-16, its own file 11-17 so it can be tested): the season's finished bets in time order,
 * with the real pool and the what-if pool side by side.
 *
 * - Bets are a share of the pool, so each bet's result scales with what-if pool / real pool at that moment, times
 *   the bet-size change (`ratio`).
 * - Money in or out (`moves`) and the starting pot scale by `k` (the money-put-in change).
 * - Leaving employees out (`out`) drops their bets; everyone else's later bets resize with the smaller or bigger pool.
 * - A what-if pool that reaches $0 is broke and stays at $0 (it can't bet with nothing); only new money put in
 *   brings it back. 11-17: it used to go negative behind the scenes, so at 100% bets a loss took it below $0 and
 *   every later loss (a negative times a negative) pushed it back up.
 *
 * Returns the what-if pool's value at each of `times` (the last value at or before each).
 */
export function replayWhatIf({ bets, moves, putIn, k, ratio, out, times }: {
  bets: [t: number, strategy: string, pnl: number][];
  moves: { t: number; amount: number }[];
  putIn: number; k: number; ratio: number; out: string[]; times: number[];
}): number[] {
  const start = putIn - moves.reduce((s, x) => s + x.amount, 0);
  let real = start, what = start * k;
  const skip = new Set(out);
  const events: [number, number, string | null, number][] = [
    ...moves.map((x) => [x.t, 0, null, x.amount] as [number, number, string | null, number]),
    ...bets.map(([t, s, p]) => [t, 1, s, p] as [number, number, string | null, number]),
  ].sort((a, c) => a[0] - c[0] || a[1] - c[1]);
  const timeline: [number, number][] = [];
  for (const [t, kind, who, v] of events) {
    if (kind === 0) what = Math.max(0, what + v * k);
    else {
      if (!skip.has(who!) && real > 0 && what > 0) what = Math.max(0, what + v * (what / real) * ratio);
      real += v;
    }
    timeline.push([t, what]);
  }
  let i = 0, last = start * k;
  return times.map((t) => {
    while (i < timeline.length && timeline[i][0] <= t) last = timeline[i++][1];
    return last;
  });
}
