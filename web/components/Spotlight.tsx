import Link from "next/link";
import type { Employee, NewsItem, Policy } from "@/lib/types";
import { awardName } from "@/lib/hr";
import { money, perDollar } from "@/lib/format";
import type { BonusPot } from "@/lib/db";
import Avatar from "./Avatar";

/** Employee of the Week/Month, plus when the next review happens and what's in the bonus pot (heads the team card). */
export default function Spotlight({ award, employees, policy, pot, startsAt, pool }: {
  award: NewsItem | null; employees: Employee[]; policy: Policy;
  pot: BonusPot; startsAt: number; pool: number; // startsAt: desk.real.yaml bonus_pot.min_pool
}) {
  const winner = award?.strategy ? employees.find((e) => e.key === award.strategy) : null;
  const next = policy.last_review ? new Date(Date.parse(policy.last_review) + policy.review_days * 86_400_000) : null;
  const title = awardName(policy.review_days);
  return (
    <div className="spotlight">
      <div className="spot-main">
        {winner ? (
          <>
            <Avatar k={winner.key} emoji={winner.emoji} size={44} />
            <div>
              <div className="label">🏆 {award!.detail.title ?? title}</div>
              <Link href={`/employee/${winner.key}`} className="spot-name">{winner.name}</Link>
              <div className="muted">{award!.detail.roi != null ? <>{perDollar(award!.detail.roi)} · </> : null}{award!.detail.why ? <>{money(award!.detail.pnl)} · {award!.detail.why}</> : <>{money(award!.detail.pnl)} last period</>}{award!.detail.bonus ? ` · earned a ${money(award!.detail.bonus, false)} bonus` : ""}</div>
            </div>
          </>
        ) : (
          <>
            <div className="spot-emoji" aria-hidden>🏆</div>
            <div>
              <div className="label">{title}</div>
              <div className="spot-name">To be decided</div>
              <div className="muted">Best cents per $1 wins, not most dollars. No pressure.</div>
            </div>
          </>
        )}
      </div>
      <div className="spot-side">
        <div><span className="muted">Next review</span><br /><strong>{next ? next.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "soon"}</strong></div>
        <div><span className="muted">🎁 Bonus pot</span><br /><strong>{
          pool < startsAt && !pot.winner ? `starts at ${money(startsAt, false)}`
            : pot.winner ? `${money(pot.left, false)} of ${money(pot.given, false)} left`
            : money(pot.pot, false)}</strong>{pot.winner && <div className="muted">{employees.find((e) => e.key === pot.winner)?.name ?? pot.winner} bets it on top this week</div>}</div>
      </div>
    </div>
  );
}
