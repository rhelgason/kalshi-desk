import type { Employee } from "@/lib/types";
import { dollars, shortName } from "@/lib/format";
import { biggest, days, lastDays, type Bet } from "@/lib/records";
import StatRow, { toneOf } from "./ui/StatRow";

const dayLabel = (d: string) => new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

/**
 * The bottom of the office's top card (11-16): the range on the chart in four cells (its change, the biggest win,
 * the busiest employee and the top earner), then the range's days as green and red (7 to 30 of them).
 */
export default function HeroFacts({ period, change, inRange, all, employees, tz, since, days: rangeDays }: {
  period: string; change: number; inRange: Bet[]; all: Bet[]; employees: Employee[]; tz: string; since: number;
  /** the chart's range in days (null: the whole season) */
  days: number | null;
}) {
  const who = Object.fromEntries(employees.map((e) => [e.key, e]));
  const count: Record<string, number> = {}, made: Record<string, number> = {};
  for (const b of inRange) { count[b.strategy] = (count[b.strategy] ?? 0) + 1; made[b.strategy] = (made[b.strategy] ?? 0) + b.pnl; }
  const topOf = (m: Record<string, number>) => Object.entries(m).sort((a, b) => b[1] - a[1])[0] ?? null;
  const busiest = topOf(count), earner = topOf(made);
  const win = biggest(inRange).win;
  const when = (t: number) => new Date(t).toLocaleDateString("en-US", { timeZone: tz, month: "short", day: "numeric" });
  const face = (k: string) => ({ k, emoji: who[k]?.emoji });
  const name = (k: string) => (who[k] ? shortName(who[k].name) : k);
  const range = period.toLowerCase();

  // The range's days, at least a week and at most a month, never from before the season started
  const want = Math.min(30, Math.max(7, rangeDays ?? 30));
  const n = Math.max(1, Math.min(want, Math.ceil((Date.now() - since) / 86_400_000)));
  const strip = lastDays(days(all, tz), n, tz);
  const scale = Math.max(1, ...strip.map((d) => Math.abs(d.pnl)));
  const green = strip.filter((d) => d.n && d.pnl > 0).length, played = strip.filter((d) => d.n).length;

  return (
    <div className="hero-facts">
      <StatRow stats={[
        { label: period, value: dollars(change, true), tone: toneOf(change), note: `${inRange.length} bets finished` },
        win
          ? { label: "Biggest Win", face: face(win.strategy), value: dollars(win.pnl, true), tone: "up", note: `${name(win.strategy)} · ${when(win.t)}` }
          : { label: "Biggest Win", value: "–", note: "none yet" },
        busiest
          ? { label: "Busiest", face: face(busiest[0]), value: name(busiest[0]), note: `${busiest[1]} bets ${range}` }
          : { label: "Busiest", value: "–", note: "no bets yet" },
        earner
          ? { label: "Top Earner", face: face(earner[0]), value: name(earner[0]), note: <><span className={toneOf(earner[1]) ?? ""}>{dollars(earner[1], true)}</span> {range}</> }
          : { label: "Top Earner", value: "–", note: "no bets yet" },
      ]} />
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
