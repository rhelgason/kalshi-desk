import { dollars } from "@/lib/format";
import type { Bet } from "@/lib/records";

/**
 * Their last bets as a strip of thin bars (11-16): wins up in green, losses down in red, each as tall as what it
 * made or lost. Favorite-buying in one picture: a row of small wins and, now and then, one long red drop.
 */
export default function FormStrip({ bets, n = 50 }: { bets: Bet[]; n?: number }) {
  const last = bets.slice(-n);
  if (!last.length) return null;
  const big = Math.max(...last.map((b) => Math.abs(b.pnl)), 0.01);
  const won = last.filter((b) => b.pnl > 0).length;
  return (
    <div className="form-strip">
      <div className="form-strip-head">
        <span className="stat-label">Last {last.length} bets</span>
        <span className="muted small">{won} won · {last.length - won} lost · {dollars(last.reduce((s, b) => s + b.pnl, 0), true)}</span>
      </div>
      <div className="form-bars" role="img" aria-label={`Last ${last.length} bets: ${won} won`}>
        {last.map((b, i) => (
          <span key={i} className="form-col" title={dollars(b.pnl, true)}>
            <i className={b.pnl > 0 ? "w" : "l"} style={{ height: `${Math.max(6, (Math.abs(b.pnl) / big) * 50)}%` }} />
          </span>
        ))}
      </div>
    </div>
  );
}
