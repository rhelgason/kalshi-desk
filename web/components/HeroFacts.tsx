import type { Employee } from "@/lib/types";
import { dollars, shortName } from "@/lib/format";
import { biggest, days, lastDays, type Bet } from "@/lib/records";
import Avatar from "./Avatar";

const STRIP = 21;
const dayLabel = (d: string) => new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

/**
 * The bottom of the office's top card (11-16): four small tiles for the range on the chart (its change, the biggest
 * win, the busiest employee and the top earner), then the last three weeks as green and red squares.
 */
export default function HeroFacts({ period, change, inRange, all, employees, tz, since }: {
  period: string; change: number; inRange: Bet[]; all: Bet[]; employees: Employee[]; tz: string; since: number;
}) {
  const who = Object.fromEntries(employees.map((e) => [e.key, e]));
  const count: Record<string, number> = {}, made: Record<string, number> = {};
  for (const b of inRange) { count[b.strategy] = (count[b.strategy] ?? 0) + 1; made[b.strategy] = (made[b.strategy] ?? 0) + b.pnl; }
  const topOf = (m: Record<string, number>) => Object.entries(m).sort((a, b) => b[1] - a[1])[0] ?? null;
  const busiest = topOf(count), earner = topOf(made);
  const win = biggest(inRange).win;
  const when = (t: number) => new Date(t).toLocaleDateString("en-US", { timeZone: tz, month: "short", day: "numeric" });
  const face = (k: string) => <Avatar k={k} emoji={who[k]?.emoji ?? "•"} size={22} />;
  const name = (k: string) => (who[k] ? shortName(who[k].name) : k);

  // Up to three weeks, never from before the season started
  const n = Math.max(1, Math.min(STRIP, Math.ceil((Date.now() - since) / 86_400_000)));
  const strip = lastDays(days(all, tz), n, tz);
  const scale = Math.max(1, ...strip.map((d) => Math.abs(d.pnl)));
  const green = strip.filter((d) => d.n && d.pnl > 0).length, played = strip.filter((d) => d.n).length;

  return (
    <div className="hero-facts">
      <div className="fact-grid">
        <div className="fact">
          <span className="fact-label">{period}</span>
          <strong className={`fact-value ${change >= 0 ? "up" : "down"}`}>{dollars(change, true)}</strong>
          <span className="fact-note">{inRange.length} bets finished</span>
        </div>
        <div className="fact">
          <span className="fact-label">Biggest win</span>
          {win ? <>
            <strong className="fact-value up">{dollars(win.pnl, true)}</strong>
            <span className="fact-note">{face(win.strategy)} {name(win.strategy)} · {when(win.t)}</span>
          </> : <span className="fact-note">none yet</span>}
        </div>
        <div className="fact">
          <span className="fact-label">Busiest</span>
          {busiest ? <>
            <strong className="fact-value fact-who">{face(busiest[0])} {name(busiest[0])}</strong>
            <span className="fact-note">{busiest[1]} bets</span>
          </> : <span className="fact-note">no bets yet</span>}
        </div>
        <div className="fact">
          <span className="fact-label">Top earner</span>
          {earner ? <>
            <strong className="fact-value fact-who">{face(earner[0])} {name(earner[0])}</strong>
            <span className={`fact-note ${earner[1] >= 0 ? "up" : "down"}`}>{dollars(earner[1], true)}</span>
          </> : <span className="fact-note">no bets yet</span>}
        </div>
      </div>
      <div className="day-strip" role="img" aria-label={`Profit by day, last ${n} days`} style={{ gridTemplateColumns: `repeat(${n}, 1fr)` }}>
        {strip.map((d) => (
          <span key={d.day} className={`day ${d.n ? (d.pnl >= 0 ? "day-up" : "day-down") : "day-none"}`}
                style={{ opacity: d.n ? 0.3 + 0.7 * Math.min(1, Math.abs(d.pnl) / scale) : undefined }}
                title={`${dayLabel(d.day)}: ${d.n ? `${dollars(d.pnl, true)}, ${d.won} of ${d.n} won` : "no bets"}`} />
        ))}
      </div>
      <div className="day-strip-legend muted small">
        <span>{dayLabel(strip[0].day)}</span><span>{green} of {played} days up</span><span>today</span>
      </div>
    </div>
  );
}
