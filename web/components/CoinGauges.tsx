import { COIN_NAMES, type Coin } from "@/lib/coin";
import { dollars, pct } from "@/lib/format";
import type { Position } from "@/lib/types";

type Settled = { t: number; strategy: string; coin: string; pnl: number };

/** The pool cards, narrowed to one coin: only that coin's bets count. */
export default function CoinGauges({ coin, settled: all, positions: open, tz, names, benched = [] }: {
  coin: Coin; settled: Settled[]; positions: Position[]; tz: string; names: Record<string, string>;
  /** the what-if: these employees' bets are left out */
  benched?: string[];
}) {
  const settled = all.filter((s) => !benched.includes(s.strategy));
  const positions = open.filter((p) => !benched.includes(p.strategy));
  const tag = benched.length ? "what-if" : undefined;
  const day = (t: number) => new Date(t).toLocaleDateString("en-CA", { timeZone: tz });
  const todayKey = day(Date.now());
  const today = settled.filter((s) => day(s.t) === todayKey);
  const sum = (rows: Settled[]) => rows.reduce((s, r) => s + r.pnl, 0);
  const won = (rows: Settled[]) => rows.filter((r) => r.pnl > 0).length;
  const inPlay = positions.reduce((s, p) => s + p.cost, 0);
  const byWho = new Map<string, number>();
  for (const s of settled) byWho.set(s.strategy, (byWho.get(s.strategy) ?? 0) + s.pnl);
  const best = [...byWho].sort((a, b) => b[1] - a[1])[0];
  const name = COIN_NAMES[coin];
  return (
    <div className="stat-row pool-gauges">
      <div className={tag}>
        <span className="muted small">In play now</span>
        <strong>{dollars(inPlay)}</strong>
        <span className="muted small">{positions.length} open {name} bet{positions.length === 1 ? "" : "s"}</span>
      </div>
      <div className={tag}>
        <span className="muted small">Today</span>
        <strong className={sum(today) >= 0 ? "up" : "down"}>{dollars(sum(today), true)}</strong>
        <span className="muted small">from finished {name} bets</span>
      </div>
      <div className={tag}>
        <span className="muted small">Bets won today</span>
        <strong>{today.length ? `${won(today)} of ${today.length}` : "None yet"}</strong>
        <span className="muted small">{name} only</span>
      </div>
      <div className={tag}>
        <span className="muted small">Win rate this season</span>
        <strong>{settled.length ? pct(won(settled) / settled.length, false, 0) : "–"}</strong>
        <span className="muted small">{settled.length} finished bet{settled.length === 1 ? "" : "s"}</span>
      </div>
      <div className={tag}>
        <span className="muted small">Profit per bet</span>
        <strong className={sum(settled) >= 0 ? "up" : "down"}>
          {settled.length ? dollars(sum(settled) / settled.length, true) : "–"}
        </strong>
        <span className="muted small">average, this season</span>
      </div>
      <div className={tag}>
        <span className="muted small">Best on {name}</span>
        <strong>{best ? names[best[0]] ?? best[0] : "–"}</strong>
        <span className="muted small">{best ? `${dollars(best[1], true)} this season` : "no finished bets yet"}</span>
      </div>
    </div>
  );
}
