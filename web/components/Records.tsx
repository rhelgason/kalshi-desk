import type { Employee } from "@/lib/types";
import { dollars, perDollar, shortName } from "@/lib/format";
import { bestHour, biggest, days, greenRun, hourLabel, lastDays, streaks, winsToRecover, type Bet } from "@/lib/records";
import Avatar from "./Avatar";

const when = (t: number, tz: string) => new Date(t).toLocaleDateString("en-US", { timeZone: tz, month: "short", day: "numeric" });
const dayLabel = (d: string) => new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

/**
 * Streaks and records for the season: win streaks, best and worst days, the golden hour, the biggest
 * loss (and how many wins it cost), and a strip of the last three weeks coloured by how each day went.
 */
/** strip: how many days of coloured squares to show (0: none, when the page already has them). */
export default function Records({ bets, employees, tz, strip = 21 }: { bets: Bet[]; employees: Employee[]; tz: string; strip?: number }) {
  if (bets.length < 5) return null;
  const who = Object.fromEntries(employees.map((e) => [e.key, e]));
  const s = streaks(bets);
  const all = days(bets, tz);
  const played = all.filter((d) => d.n > 0);
  const bestDay = played.reduce((a, b) => (b.pnl > a.pnl ? b : a));
  const worstDay = played.reduce((a, b) => (b.pnl < a.pnl ? b : a));
  const busiest = played.reduce((a, b) => (b.n > a.n ? b : a));
  const green = greenRun(all, tz);
  const hours = bestHour(bets, tz);
  const big = biggest(bets);
  const recover = big.loss ? winsToRecover(big.loss.pnl, bets) : null;
  // Who's on the longest current run
  const runs = Object.entries(Object.groupBy(bets, (b) => b.strategy)).map(([k, bs]) => ({ k, run: streaks(bs!).current }))
    .sort((a, b) => b.run - a.run);
  const hot = runs[0]?.run > 0 ? runs[0] : null;
  const strip21 = strip ? lastDays(all, strip, tz) : [];
  const scale = Math.max(...strip21.map((d) => Math.abs(d.pnl)), 0.01);
  const face = (k: string) => who[k] ? <Avatar k={k} emoji={who[k].emoji} size={20} /> : null;
  const name = (k: string) => (who[k] ? shortName(who[k].name) : k);

  return (
    <section className="card records">
      <h2>Streaks &amp; Records</h2>
      <div className="record-grid">
        <div className={`record ${s.currentIsBest ? "record-hot" : ""}`}>
          <span className="record-label">🔥 Win streak</span>
          <strong className="record-value">{s.current}</strong>
          <span className="record-note">{s.currentIsBest ? "a season record, still going" : `record ${s.best}${s.bestEnd ? ` (${when(s.bestEnd, tz)})` : ""}`}</span>
        </div>
        <div className="record">
          <span className="record-label">🟩 Green days in a row</span>
          <strong className="record-value">{green}</strong>
          <span className="record-note">{played.filter((d) => d.pnl > 0).length} of {played.length} days up this season</span>
        </div>
        <div className="record">
          <span className="record-label">📈 Best day</span>
          <strong className="record-value up">{dollars(bestDay.pnl, true)}</strong>
          <span className="record-note">{dayLabel(bestDay.day)} · {bestDay.won} of {bestDay.n} won</span>
        </div>
        <div className="record">
          <span className="record-label">📉 Worst day</span>
          <strong className={`record-value ${worstDay.pnl < 0 ? "down" : "up"}`}>{dollars(worstDay.pnl, true)}</strong>
          <span className="record-note">{dayLabel(worstDay.day)} · {worstDay.won} of {worstDay.n} won</span>
        </div>
        {hours && (
          <div className="record">
            <span className="record-label">⏰ Golden hour</span>
            <strong className="record-value">{hourLabel(hours.best.hour)}</strong>
            <span className="record-note">{dollars(hours.best.pnl, true)} over {hours.best.n} bets · worst {hourLabel(hours.worst.hour)}</span>
          </div>
        )}
        {hot && (
          <div className="record">
            <span className="record-label">🎯 Hot hand</span>
            <strong className="record-value record-who">{face(hot.k)} {name(hot.k)}</strong>
            <span className="record-note">{hot.run} wins in a row</span>
          </div>
        )}
        {big.loss && (
          <div className="record">
            <span className="record-label">💥 Biggest loss</span>
            <strong className="record-value down">{dollars(big.loss.pnl, true)}</strong>
            <span className="record-note record-who">{face(big.loss.strategy)} {name(big.loss.strategy)} · {when(big.loss.t, tz)}{recover ? ` · ${recover} wins to earn back` : ""}</span>
          </div>
        )}
        <div className="record">
          <span className="record-label">⚡ Busiest day</span>
          <strong className="record-value">{busiest.n} bets</strong>
          <span className="record-note">{dayLabel(busiest.day)} · {dollars(busiest.pnl, true)} · {perDollar(sumRatio(bets, busiest.day, tz))}</span>
        </div>
      </div>
      {strip > 0 && <>
      <div className="day-strip" role="img" aria-label={`Profit by day, last ${strip} days`}>
        {strip21.map((d) => {
          const a = d.n ? 0.25 + 0.75 * Math.min(1, Math.abs(d.pnl) / scale) : 0;
          return (
            <span key={d.day} className={`day ${d.n ? (d.pnl >= 0 ? "day-up" : "day-down") : "day-none"}`}
                  style={{ opacity: d.n ? a : undefined }}
                  title={`${dayLabel(d.day)}: ${d.n ? `${dollars(d.pnl, true)}, ${d.won} of ${d.n} won` : "no bets"}`} />
          );
        })}
      </div>
      <div className="day-strip-legend muted small"><span>{dayLabel(strip21[0].day)}</span><span>Each square is a day: green up, red down</span><span>today</span></div>
      </>}
    </section>
  );
}

/** Cents per $1 on one day. */
function sumRatio(bets: Bet[], day: string, tz: string) {
  let p = 0, c = 0;
  for (const b of bets) if (b.cost && new Date(b.t).toLocaleDateString("en-CA", { timeZone: tz }) === day) { p += b.pnl; c += b.cost; }
  return c ? p / c : null;
}
