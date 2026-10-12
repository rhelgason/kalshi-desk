import Link from "next/link";
import type { Employee, NewsItem, Policy } from "@/lib/types";
import { awardName } from "@/lib/hr";
import { money } from "@/lib/format";
import Avatar from "./Avatar";

/** Employee of the Week/Month, plus when the next review happens and what's in the bonus pot. */
export default function Spotlight({ award, employees, policy }: { award: NewsItem | null; employees: Employee[]; policy: Policy }) {
  const winner = award?.strategy ? employees.find((e) => e.key === award.strategy) : null;
  const next = policy.last_review ? new Date(Date.parse(policy.last_review) + policy.review_days * 86_400_000) : null;
  const title = awardName(policy.review_days);
  return (
    <section className="card spotlight">
      <div className="spot-main">
        {winner ? (
          <>
            <Avatar k={winner.key} emoji={winner.emoji} size={56} />
            <div>
              <div className="label">🏆 {award!.detail.title ?? title}</div>
              <Link href={`/employee/${winner.key}`} className="spot-name">{winner.name}</Link>
              <div className="muted">{money(award!.detail.pnl)} last period{award!.detail.bonus ? ` · earned a ${money(award!.detail.bonus, false)} bonus` : ""}</div>
            </div>
          </>
        ) : (
          <>
            <div className="spot-emoji" aria-hidden>🏆</div>
            <div>
              <div className="label">{title}</div>
              <div className="spot-name">To be decided</div>
              <div className="muted">Best earner wins. No pressure.</div>
            </div>
          </>
        )}
      </div>
      <div className="spot-side">
        <div><span className="muted">Next review</span><br /><strong>{next ? next.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "soon"}</strong></div>
        <div><span className="muted">Bonus reserve</span><br /><strong>{money(policy.reserve, false)}</strong></div>
      </div>
    </section>
  );
}
