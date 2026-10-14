import { dollars, pct } from "@/lib/format";
import type { PoolSummary } from "@/lib/types";

/** The pool's guardrails at a glance: what's riding now, today vs the daily stop, and the brake. */
export default function PoolGauges({ pool }: { pool: PoolSummary }) {
  const s = pool.settings;
  const safety = pool.stopped
    ? { text: "⏸ Stopped for today", note: `Down ${pct(-pool.today, false, 1)} since midnight; back tomorrow` }
    : pool.braked
      ? { text: "🐢 Bets halved", note: `More than ${pct(s.brake_drawdown, false, 0)} below the high of ${dollars(pool.peak)}` }
      : { text: "✅ All clear", note: `Stops at −${pct(s.daily_stop, false, 0)} in a day` };
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
    </div>
  );
}
