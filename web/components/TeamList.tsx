import Link from "next/link";
import type { Light } from "@/lib/advice";
import type { Employee, Point } from "@/lib/types";
import { dollars, pct } from "@/lib/format";
import Avatar from "./Avatar";
import Sparkline from "./Sparkline";

export type TeamRow = { e: Employee; light: Light; trend: Point[] };

/** Every employee as a tappable row: status, money given, and how much they've made or lost. */
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
                <span className="name">{e.name}</span>
                <span className={`light ${light.key}`}>{light.icon} {light.label}</span>
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
