import Link from "next/link";
import type { Light } from "@/lib/advice";
import type { Employee, Point } from "@/lib/types";
import { dollars, pct } from "@/lib/format";
import Avatar from "./Avatar";
import Sparkline from "./Sparkline";
import { levelTitle } from "@/lib/hr";

export type TeamRow = { e: Employee; light: Light; trend: Point[] };

/** Every employee as a tappable row: level, status, and how much they've made or lost. */
/** star: the current Employee of the Week, marked with a trophy in their row. */
/**
 * profits: each one's profit from finished bets (11-16), so the list only moves when a bet is decided; rates: their
 * profit per $1 bet (every row gets the same kind of second line, so the columns line up); notes: a line about them.
 */
export default function TeamList({ rows, star, starTitle = "Employee of the Week", profits, rates, notes }: {
  rows: TeamRow[]; star?: string; starTitle?: string; profits?: Record<string, number>;
  rates?: Record<string, number | null>; notes?: Record<string, string>;
}) {
  return (
    <ul className="team">
      {rows.map(({ e, light, trend }) => {
        const pnl = profits ? profits[e.key] ?? 0 : e.pnl ?? 0;
        const given = e.starting_cash ?? 0;
        const rate = rates?.[e.key];
        return (
          <li key={e.key} className={[light.key === "benched" || light.key === "fired" ? "benched" : "", e.key === star ? "star" : ""].join(" ").trim() || undefined}>
            <Link href={`/employee/${e.key}`}>
              <Avatar k={e.key} emoji={e.emoji} size={36} />
              <span className="who-main">
                <span className="name-line">
                  <span className="name">{e.name}</span>
                  {e.key === star && <span className="lvl lvl-star" title={starTitle}>🏆</span>}
                  {e.control
                    ? <span className="lvl lvl-yard" title="Control group: bets at random, so the others have something to beat">Yardstick</span>
                    : <span className={`lvl lvl-${e.level ?? 1}`} title="Level: higher levels bet more of the pool">{levelTitle(e.level ?? 1)}</span>}
                </span>
                <span className="quip">{notes?.[e.key] ?? light.label}</span>
              </span>
              <span className="trend"><Sparkline points={trend} width={72} height={26} /></span>
              <span className="money-col">
                <span className={`pnl ${pnl > 0.004 ? "up" : pnl < -0.004 ? "down" : "flat"}`}>{dollars(pnl, true)}</span>
                <span className="muted small">
                  {rates ? (rate == null ? "no bets yet" : `${rate >= 0 ? "+" : ""}${(rate * 100).toFixed(1)}¢ per $1`)
                    : given > 0 ? `${pct(pnl / given, true)} of ${dollars(given).replace(".00", "")}` : `${e.fills ?? 0} bets`}
                </span>
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
