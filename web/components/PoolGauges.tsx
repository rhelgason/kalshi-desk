import { dollars, pct } from "@/lib/format";
import type { PoolSummary } from "@/lib/types";

/**
 * The pool at a glance: what's riding now, today vs the daily stop, the brake, bets won,
 * how far it is below its high, and the cash free for new bets.
 */
export type PoolRecord = { today: { n: number; won: number }; season: { n: number; won: number } };

export default function PoolGauges({ pool, record }: { pool: PoolSummary; record?: PoolRecord }) {
  const s = pool.settings;
  const safety = pool.stopped
    ? { text: "⏸ Stopped for today", note: `Down ${pct(-pool.today, false, 1)} since midnight; back tomorrow` }
    : pool.braked
      ? { text: "🐢 Bets halved", note: `More than ${pct(s.brake_drawdown, false, 0)} below the high of ${dollars(pool.peak)}` }
      : { text: "✅ All clear", note: `Stops at −${pct(s.daily_stop, false, 0)} in a day` };
  const offHigh = pool.peak > 0 ? Math.max(0, 1 - pool.equity / pool.peak) : 0;
  const rate = (r: { n: number; won: number }) => (r.n ? pct(r.won / r.n, false, 0) : "–");
  return (
    <div className="stat-row pool-gauges">
      <div>
        <span className="muted small">In play now</span>
        <strong>{dollars(pool.in_play)}</strong>
        <span className="muted small">max {dollars(pool.window_cap).replace(".00", "")} per 15 min</span>
      </div>
      <div>
        <span className="muted small">Today</span>
        <strong className={pool.today >= 0 ? "up" : "down"}>{pct(pool.today, true, 1)}</strong>
        <span className="muted small">{dollars(pool.equity - pool.day_open, true)}</span>
      </div>
      <div>
        <span className="muted small">Safety</span>
        <strong>{safety.text}</strong>
        <span className="muted small">{safety.note}</span>
      </div>
      <div>
        <span className="muted small">Bets won today</span>
        <strong>{record ? (record.today.n ? `${record.today.won} of ${record.today.n}` : "None yet") : "–"}</strong>
        <span className="muted small">{record ? `${rate(record.season)} all season (${record.season.n})` : ""}</span>
      </div>
      <div>
        <span className="muted small">From the high</span>
        <strong className={offHigh > 0.0005 ? "down" : "up"}>{offHigh > 0.0005 ? `−${pct(offHigh, false, 1)}` : "At the high"}</strong>
        <span className="muted small">high {dollars(pool.peak)}; brake at −{pct(s.brake_drawdown, false, 0)}</span>
      </div>
      <div>
        <span className="muted small">Free cash</span>
        <strong>{dollars(pool.cash)}</strong>
        <span className="muted small">{pct(pool.cash / (pool.equity || 1), false, 0)} of the pool, ready to bet</span>
      </div>
    </div>
  );
}
