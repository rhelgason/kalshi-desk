import Link from "next/link";
import type { CoinRow } from "@/lib/db";
import { dollars, pct } from "@/lib/format";

export type Coin = "all" | "BTC" | "ETH";
export type CoinTotal = { n: number; won: number; pnl: number };

const NAMES: Record<Coin, string> = { all: "All coins", BTC: "Bitcoin", ETH: "Ether" };

export const parseCoin = (v?: string): Coin => (v === "BTC" || v === "ETH" ? v : "all");

/** Settled bets for one coin, per employee. */
export function coinByEmployee(rows: CoinRow[], coin: Coin): Record<string, CoinTotal> {
  const out: Record<string, CoinTotal> = {};
  for (const r of rows) {
    if (coin !== "all" && r.coin !== coin) continue;
    const t = (out[r.strategy] ??= { n: 0, won: 0, pnl: 0 });
    t.n += r.n; t.won += r.won; t.pnl += r.pnl;
  }
  return out;
}

/** Settled bets for one coin, added up across the pool's members. */
export function coinTotal(rows: CoinRow[], coin: Coin, members: Set<string>): CoinTotal {
  const t = { n: 0, won: 0, pnl: 0 };
  for (const [k, v] of Object.entries(coinByEmployee(rows, coin))) {
    if (!members.has(k)) continue;
    t.n += v.n; t.won += v.won; t.pnl += v.pnl;
  }
  return t;
}

/** All coins / Bitcoin / Ether, shown only once more than one coin has settled bets. */
export default function CoinTabs({ value, coins, params }: { value: Coin; coins: CoinRow[]; params: Record<string, string | undefined> }) {
  const seen = new Set(coins.map((r) => r.coin));
  if (seen.size < 2 && value === "all") return null;
  return (
    <nav className="seg seg-mini" aria-label="Coin">
      {(["all", "BTC", "ETH"] as Coin[]).filter((c) => c === "all" || seen.has(c)).map((c) => {
        const q = new URLSearchParams();
        for (const [k, v] of Object.entries(params)) if (v != null && k !== "coin") q.set(k, v);
        if (c !== "all") q.set("coin", c);
        return (
          <Link key={c} href={`/?${q}`} aria-current={c === value ? "true" : undefined} scroll={false} replace>
            {NAMES[c]}
          </Link>
        );
      })}
    </nav>
  );
}

/** One line under the tabs: how the pool's settled bets on this coin went. */
export function CoinSummary({ coin, total }: { coin: Coin; total: CoinTotal }) {
  if (!total.n) return <p className="muted small">No {NAMES[coin].toLowerCase()} bets settled this season yet.</p>;
  return (
    <p className="small coin-summary">
      {NAMES[coin]} only: {total.n} settled bet{total.n === 1 ? "" : "s"}, {pct(total.won / total.n, false, 0)} won,{" "}
      <strong className={total.pnl >= 0 ? "up" : "down"}>{dollars(total.pnl, true)}</strong>
      <span className="muted"> (finished bets only; the team&apos;s numbers below are {NAMES[coin].toLowerCase()} too)</span>
    </p>
  );
}
