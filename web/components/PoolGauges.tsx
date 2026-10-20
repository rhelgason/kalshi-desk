import { dollars, pct } from "@/lib/format";
import type { PoolSummary } from "@/lib/types";

/**
 * The pool at a glance: what's riding now, the change over the chart's range, the safety
 * switches, bets won in the range (and ever), how far it is below its high, and free cash.
 * The range cards follow the chart's tabs; the rest are about right now.
 */
type Count = { n: number; won: number };
export type PoolRecord = { range: Count; lifetime: Count };

/** What the what-if changes: the numbers with the benched employees' bets taken out. */
export type PoolWhatIf = { inPlay: number; change: number; record: PoolRecord };

/**
 * halted: the real-money kill switch is on (why), which outranks the pool's own stops.
 * change / start: the chart's change over its range and the pool's value at its start.
 * scope: that range in words ("today", "this week", "lifetime").
 */
export default function PoolGauges({ pool, record, whatIf, halted, change, start, scope }: {
  pool: PoolSummary; record?: PoolRecord; whatIf?: PoolWhatIf | null; halted?: string | null;
  change: number; start: number; scope: string;
}) {
  const s = pool.settings;
  const inPlay = whatIf ? whatIf.inPlay : pool.in_play;
  const moved = whatIf ? whatIf.change : change;
  const movedPct = moved / (start || 1);
  const Scope = scope.charAt(0).toUpperCase() + scope.slice(1);
  const lifetime = scope === "lifetime";
  record = whatIf?.record ?? record;
  const tag = whatIf ? "what-if" : undefined;
  const safety = halted
    ? { text: "⏸ Real trading paused", note: halted }
    : pool.stopped
    ? { text: "⏸ Stopped for today", note: `Down ${pct(-pool.today, false, 1)} since midnight; back tomorrow` }
    : pool.braked
      ? { text: "🐢 Bets halved", note: `More than ${pct(s.brake_drawdown, false, 0)} below the high of ${dollars(pool.peak)}` }
      : { text: "✅ All clear", note: `Stops at −${pct(s.daily_stop, false, 0)} in a day` };
  const offHigh = pool.peak > 0 ? Math.max(0, 1 - pool.equity / pool.peak) : 0;
  const rate = (r: { n: number; won: number }) => (r.n ? pct(r.won / r.n, false, 0) : "–");
  return (
    <div className="stat-row pool-gauges">
      <div className={tag}>
        <span className="muted small">In play now</span>
        <strong>{dollars(inPlay)}</strong>
        <span className="muted small">max {dollars(pool.window_cap).replace(".00", "")} per 15 min</span>
      </div>
      <div className={tag}>
        <span className="muted small">{Scope}</span>
        <strong className={moved >= 0 ? "up" : "down"}>{pct(movedPct, true, 1)}</strong>
        <span className="muted small">{dollars(moved, true)}</span>
      </div>
      <div>
        <span className="muted small">Safety</span>
        <strong>{safety.text}</strong>
        <span className="muted small">{safety.note}</span>
      </div>
      <div className={tag}>
        <span className="muted small">Bets won ({scope})</span>
        <strong>{record ? (record.range.n ? `${record.range.won} of ${record.range.n}` : "None yet") : "–"}</strong>
        <span className="muted small">{record ? (lifetime ? `${rate(record.lifetime)} won` : `lifetime: ${record.lifetime.won} of ${record.lifetime.n} (${rate(record.lifetime)})`) : ""}</span>
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
