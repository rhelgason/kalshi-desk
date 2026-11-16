import Link from "next/link";
import type { Employee } from "@/lib/types";
import { dollars, shortName } from "@/lib/format";
import { levelTitle } from "@/lib/hr";
import Avatar from "./Avatar";

/**
 * The staff in one row (11-16): face, level and profit from finished bets since the start (not open bets, so it
 * only moves when a bet is decided); the full team page is a tap away.
 */
export default function TeamStrip({ team, profits, attention = 0 }: {
  team: Employee[]; profits: Record<string, number>; attention?: number;
}) {
  const pnl = (e: Employee) => profits[e.key] ?? 0;
  const sorted = [...team].sort((a, b) => pnl(b) - pnl(a));
  return (
    <section className="card team-strip">
      <div className="card-head">
        <h2>Team</h2>
        <Link href="/team" className="small">
          {attention > 0 ? <strong>{attention} {attention === 1 ? "needs" : "need"} you · </strong> : null}See the team →
        </Link>
      </div>
      <ul className="strip">
        {sorted.map((e) => (
          <li key={e.key}>
            <Link href={`/employee/${e.key}`} className="strip-person" title={e.name}>
              <Avatar k={e.key} emoji={e.emoji} size={40} />
              <span className="strip-name">{shortName(e.name)}</span>
              <span className="strip-level">{e.status === "suspended" ? "Benched" : levelTitle(e.level ?? 1)}</span>
              <span className={`strip-pnl ${pnl(e) >= 0 ? "up" : "down"}`}>{dollars(pnl(e), true)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
