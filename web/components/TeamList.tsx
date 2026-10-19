import Link from "next/link";
import type { Light } from "@/lib/advice";
import type { Employee, Point } from "@/lib/types";
import { dollars, pct } from "@/lib/format";
import Avatar from "./Avatar";
import Sparkline from "./Sparkline";
import { quip } from "@/lib/voice";
import { levelTitle } from "@/lib/hr";

export type TeamRow = { e: Employee; light: Light; trend: Point[] };
/** One coin's settled bets in place of the usual totals (the coin tabs). */
export type CoinView = { name: string; stats: Record<string, { n: number; won: number; pnl: number }> };

/** Every employee as a tappable row: level, status, and how much they've made or lost. */
/** star: the current Employee of the Week, marked with a trophy in their row. */
export default function TeamList({ rows, coin, star, starTitle = "Employee of the Week" }: {
  rows: TeamRow[]; coin?: CoinView; star?: string; starTitle?: string;
}) {
  return (
    <ul className="team">
      {rows.map(({ e, light, trend }) => {
        const c = coin ? coin.stats[e.key] ?? { n: 0, won: 0, pnl: 0 } : null;
        const pnl = c ? c.pnl : e.pnl ?? 0;
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
                <span className="quip"><span title={light.label} aria-label={light.label}>{light.icon}</span> “{quip(e)}”</span>
              </span>
              {!c && <span className="trend"><Sparkline points={trend} width={72} height={26} /></span>}
              <span className="money-col">
                <span className={`pnl ${pnl > 0.004 ? "up" : pnl < -0.004 ? "down" : "flat"}`}>{dollars(pnl, true)}</span>
                <span className="muted small">
                  {c
                    ? (c.n ? `${c.won}/${c.n} won` : "no bets")
                    : `${pct(e.roi ?? 0, true)} of ${dollars(e.starting_cash ?? 0).replace(".00", "")}`}
                </span>
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
