import { dollars } from "@/lib/format";
import type { Bet } from "@/lib/records";

/**
 * Their latest results as a row of dots (11-16), oldest first: green won, red lost. 50 on a wide screen, the newest
 * 30 on a phone (CSS hides the rest), so the row always fills its line.
 */
export default function FormStrip({ bets, n = 50, phone = 30 }: { bets: Bet[]; n?: number; phone?: number }) {
  const last = bets.slice(-n);
  if (!last.length) return null;
  const won = last.filter((b) => b.pnl > 0).length;
  const recent = last.slice(-phone), wonRecent = recent.filter((b) => b.pnl > 0).length;
  return (
    <div className="form-strip">
      <div className="form-strip-head">
        <span className="stat-label">
          <span className="wide-only">Last {last.length} bets</span><span className="phone-only">Last {recent.length} bets</span>
        </span>
        <span className="muted small">
          <span className="wide-only">{won} won · {last.length - won} lost</span>
          <span className="phone-only">{wonRecent} won · {recent.length - wonRecent} lost</span>
        </span>
      </div>
      <div className="form-dots" role="img" aria-label={`Last ${last.length} bets: ${won} won`}>
        {last.map((b, i) => (
          <span key={i} className={`form-dot ${b.pnl > 0 ? "w" : "l"} ${i < last.length - phone ? "wide-only" : ""}`} title={dollars(b.pnl, true)} />
        ))}
      </div>
    </div>
  );
}
