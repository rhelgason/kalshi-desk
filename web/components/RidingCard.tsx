import type { Employee, Position } from "@/lib/types";
import { coinOfTicker } from "@/lib/coin";
import { dollars, shortName } from "@/lib/format";
import Avatar from "./Avatar";

/** What one open bet is worth at the market's latest price (the bot's mark, as Kalshi values it). */
const worthNow = (p: Position) => (p.mark == null ? p.cost : p.yes * p.mark + p.no * (1 - p.mark));

/**
 * Bets riding now (11-16): its own card, soonest to finish first. The only place a number moves before a bet is
 * decided: each bet's value at today's price, and the total, which is Kalshi's own figure when it agrees with
 * our books (`held`, lib/portfolio headline).
 */
export default function RidingCard({ positions, employees, held }: {
  positions: Position[]; employees: Employee[]; held?: number | null;
}) {
  if (!positions.length) return null;
  const who = Object.fromEntries(employees.map((e) => [e.key, e]));
  const now = Date.now();
  const rows = positions
    .map((p) => ({ ...p, mins: p.closes ? Math.max(0, Math.round((Date.parse(p.closes) - now) / 60_000)) : null }))
    .sort((a, b) => (a.mins ?? 1e9) - (b.mins ?? 1e9));
  const cost = rows.reduce((s, p) => s + p.cost, 0);
  const worth = held ?? rows.reduce((s, p) => s + worthNow(p), 0);
  const pays = rows.reduce((s, p) => s + Math.max(p.yes, p.no), 0);
  return (
    <section className="card riding-card">
      <div className="card-head">
        <h2>Riding now</h2>
        <span className="muted small">
          {rows.length} {rows.length === 1 ? "bet" : "bets"} · {dollars(cost)} in · pays {dollars(pays)} if all win ·{" "}
          worth <strong className={worth >= cost ? "up" : "down"}>{dollars(worth)}</strong> now
        </span>
      </div>
      <ul className="bet-rows">
        {rows.map((p) => {
          const e = who[p.strategy];
          const side = p.yes > p.no ? "YES" : "NO";
          const now = worthNow(p);
          return (
            <li key={`${p.strategy}-${p.ticker}`} className="bet-row">
              <Avatar k={p.strategy} emoji={e?.emoji ?? "•"} size={28} />
              <div className="bet-what">
                <div><strong>{e ? shortName(e.name) : p.strategy}</strong> · {coinOfTicker(p.ticker)} {side}</div>
                <div className="muted small">{dollars(p.cost)} to win {dollars(Math.max(p.yes, p.no) - p.cost)}</div>
              </div>
              <div className="bet-side">
                <div className={now >= p.cost ? "up" : "down"}>{dollars(now - p.cost, true)}</div>
                <div className="muted small">{p.mins == null ? "" : p.mins ? `${p.mins} min left` : "settling"}</div>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
