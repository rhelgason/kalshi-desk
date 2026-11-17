import { dollars } from "@/lib/format";
import { days, lastDays, type Bet } from "@/lib/records";

const dayLabel = (d: string) => new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

/**
 * The last n days as green and red squares (11-16), stronger for a bigger day, with "N of M days up" under them.
 * The office's top card and the cockpit's "Is it working?" both use it.
 */
export default function DayStrip({ bets, tz, n }: { bets: Bet[]; tz: string; n: number }) {
  const strip = lastDays(days(bets, tz), Math.max(1, n), tz);
  const scale = Math.max(1, ...strip.map((d) => Math.abs(d.pnl)));
  const green = strip.filter((d) => d.n && d.pnl > 0).length, played = strip.filter((d) => d.n).length;
  return (
    <>
      <div className="day-strip" role="img" aria-label={`Profit by day, last ${strip.length} days: ${green} of ${played} up`}
           style={{ gridTemplateColumns: `repeat(${strip.length}, 1fr)` }}>
        {strip.map((d) => (
          <span key={d.day} className={`day ${d.n ? (d.pnl >= 0 ? "day-up" : "day-down") : "day-none"}`}
                style={{ opacity: d.n ? 0.3 + 0.7 * Math.min(1, Math.abs(d.pnl) / scale) : undefined }}
                title={`${dayLabel(d.day)}: ${d.n ? `${dollars(d.pnl, true)}, ${d.won} of ${d.n} won` : "no bets"}`} />
        ))}
      </div>
      <div className="day-strip-legend muted small">
        <span>{dayLabel(strip[0].day)}</span><span>{green} of {played} days up</span><span>today</span>
      </div>
    </>
  );
}
