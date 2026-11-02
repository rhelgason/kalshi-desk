import type { Employee, Fill, Position } from "@/lib/types";
import { coinOfTicker } from "@/lib/coin";
import { dollars, money, shortName } from "@/lib/format";
import Avatar from "./Avatar";
import TradeFeed from "./TradeFeed";

const SHOWN = 8;

/**
 * The latest bets, up near the top and open: the part of the page that gets read every visit. A line on the last
 * 24 hours heads it, bets still riding sit above the list (only when there are any), and the rest of the
 * recent bets fold away under the first eight.
 */
export default function LatestBets({ fills, employees, positions, day }: {
  fills: Fill[]; employees: Employee[]; positions: Position[];
  day: { n: number; won: number; pnl: number };
}) {
  const who = Object.fromEntries(employees.map((e) => [e.key, e]));
  const now = Date.now();
  const riding = positions
    .map((p) => ({ ...p, mins: p.closes ? Math.max(0, Math.round((Date.parse(p.closes) - now) / 60_000)) : null }))
    .sort((a, b) => (a.mins ?? 1e9) - (b.mins ?? 1e9));
  return (
    <section className="card latest">
      <div className="latest-head">
        <h2>Latest bets</h2>
        <span className="latest-day">
          Last 24h: {day.n ? <><strong>{day.won}</strong> of {day.n} won · <strong className={day.pnl >= 0 ? "up" : "down"}>{dollars(day.pnl, true)}</strong></> : "nothing settled"}
        </span>
      </div>
      {riding.length > 0 && (
        <div className="riding" aria-label="Bets riding now">
          <span className="riding-label">🎲 Riding now</span>
          {riding.map((p) => {
            const e = who[p.strategy];
            const side = p.yes > p.no ? "YES" : "NO";
            const pays = Math.max(p.yes, p.no);
            return (
              <span key={`${p.strategy}-${p.ticker}`} className="riding-bet">
                {e && <Avatar k={e.key} emoji={e.emoji} size={18} />}
                <span><strong>{e ? shortName(e.name) : p.strategy}</strong> {coinOfTicker(p.ticker)} {side} · {money(p.cost, false)} to win {money(pays - p.cost)}</span>
                {p.mins != null && <span className="riding-clock">{p.mins ? `${p.mins}m` : "settling"}</span>}
              </span>
            );
          })}
        </div>
      )}
      <TradeFeed fills={fills.slice(0, SHOWN)} employees={employees} />
      {fills.length > SHOWN && (
        <details className="more-bets">
          <summary>Show {fills.length - SHOWN} more</summary>
          <TradeFeed fills={fills.slice(SHOWN)} employees={employees} />
        </details>
      )}
    </section>
  );
}
