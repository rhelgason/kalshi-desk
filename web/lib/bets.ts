import { coinOfTicker } from "./coin";
import type { Position } from "./types";

/** One bet riding on a coin's price: "BTC ends above $84,380 at 12:45" (employees on the same side share it). */
export type RidingBet = {
  ticker: string;
  coin: string;
  side: "yes" | "no"; // yes = the price ends at or above the target
  strike: number;
  closes: number; // ms
  who: string[];
  cost: number; // what was paid
  payout: number; // what comes back if it wins ($1 a contract)
};

/** "Target Price: $84,380.28" -> 84380.28 (older statuses carry no strike field). */
const strikeOf = (p: Position) => p.strike ?? (Number(/\$([\d,.]+)/.exec(p.subtitle)?.[1]?.replace(/,/g, "")) || null);

export function ridingBets(positions: Position[], names: Record<string, string>): RidingBet[] {
  const out = new Map<string, RidingBet>();
  for (const p of positions) {
    const strike = strikeOf(p);
    if (strike == null || !p.closes) continue;
    for (const side of ["yes", "no"] as const) {
      const n = p[side];
      if (n <= 0) continue;
      const id = `${p.ticker}:${side}`;
      const b = out.get(id) ?? { ticker: p.ticker, coin: coinOfTicker(p.ticker), side, strike, closes: Date.parse(p.closes), who: [], cost: 0, payout: 0 };
      const name = names[p.strategy] ?? p.strategy;
      if (!b.who.includes(name)) b.who.push(name);
      // A position holding both sides splits its cost by contracts
      b.cost += p.cost * (n / (p.yes + p.no));
      b.payout += n;
      out.set(id, b);
    }
  }
  return [...out.values()].sort((a, b) => a.closes - b.closes || a.strike - b.strike);
}
