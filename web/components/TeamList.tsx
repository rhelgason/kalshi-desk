import Link from "next/link";
import type { Light } from "@/lib/advice";
import type { Employee, Point } from "@/lib/types";
import { dollars, pct } from "@/lib/format";
import Avatar from "./Avatar";
import Sparkline from "./Sparkline";
import { quip } from "@/lib/voice";
import { levelTitle } from "@/lib/hr";

export type TeamRow = { e: Employee; light: Light; trend: Point[] };

/** Every employee as a tappable row: level, status, and how much they've made or lost. */
export default function TeamList({ rows }: { rows: TeamRow[] }) {
  return (
    <ul className="team">
      {rows.map(({ e, light, trend }) => {
        const pnl = e.pnl ?? 0;
        return (
          <li key={e.key} className={light.key === "benched" || light.key === "fired" ? "benched" : ""}>
            <Link href={`/employee/${e.key}`}>
              <Avatar k={e.key} emoji={e.emoji} size={36} />
              <span className="who-main">
                <span className="name-line">
                  <span className="name">{e.name}</span>
                  {e.control
                    ? <span className="lvl lvl-yard" title="Control group: bets at random, so the others have something to beat">Yardstick</span>
                    : <span className={`lvl lvl-${e.level ?? 1}`} title="Level: higher levels bet more of the pool">{levelTitle(e.level ?? 1)}</span>}
                </span>
                <span className="quip"><span title={light.label} aria-label={light.label}>{light.icon}</span> “{quip(e)}”</span>
              </span>
              <span className="trend"><Sparkline points={trend} width={72} height={26} /></span>
              <span className="money-col">
                <span className={`pnl ${pnl > 0.004 ? "up" : pnl < -0.004 ? "down" : "flat"}`}>{dollars(pnl, true)}</span>
                <span className="muted small">{pct(e.roi ?? 0, true)} of {dollars(e.starting_cash ?? 0).replace(".00", "")}</span>
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
