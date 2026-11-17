import type { ReactNode } from "react";
import type { Employee } from "@/lib/types";
import { dollars } from "@/lib/format";
import { biggest, days, perDollar, streaks, winsToRecover, type Bet } from "@/lib/records";
import Avatar from "./Avatar";
import FormStrip from "./FormStrip";
import LevelChip from "./ui/LevelChip";
import StatRow, { toneOf } from "./ui/StatRow";

const dayLabel = (d: string) => new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

/**
 * The top of an employee's page (11-16): portrait, name, level, their one-line caption and last ten results, with
 * profit and win rate on the right; what they do in a sentence or two; then four numbers. Everything is from
 * finished bets, so it only moves when a bet is decided.
 */
export default function PlayerCard({ e, bets, team, tz, badges, caption, blurb }: {
  /** team: everyone's season profit per $1 and bets, for this employee's rank */
  e: Employee; bets: Bet[]; team: { key: string; n: number; perDollar: number | null }[]; tz: string;
  badges?: ReactNode; caption?: string; blurb?: string;
}) {
  const n = bets.length;
  const wins = bets.filter((b) => b.pnl > 0).length;
  const profit = bets.reduce((s, b) => s + b.pnl, 0);
  const pd = perDollar(bets);
  const ranked = team.map((t) => ({ key: t.key, pd: t.perDollar, n: t.n }))
    .filter((t) => t.pd != null && t.n >= 10).sort((a, b) => b.pd! - a.pd!);
  const rank = ranked.findIndex((t) => t.key === e.key);
  const s = streaks(bets);
  const ds = days(bets, tz).filter((d) => d.n);
  const best = ds.length ? ds.reduce((a, b) => (b.pnl > a.pnl ? b : a)) : null;
  const big = biggest(bets);
  const recover = big.loss ? winsToRecover(big.loss.pnl, bets) : null;

  return (
    <section className={`card player ${e.control ? "player-yard" : ""}`}>
      <div className="player-top">
        <div className="player-portrait"><Avatar k={e.key} emoji={e.emoji} size={88} /></div>
        <div className="player-id">
          <div className="player-title">{e.title}</div>
          <h1 className="player-name">{e.name}</h1>
          <div className="player-badges">
            <LevelChip level={e.level} control={e.control} benched={e.status === "suspended"} />
            {badges}
          </div>
          {caption && <div className="player-caption">{caption}</div>}
        </div>
        <div className="player-headline">
          <div className={`player-profit ${toneOf(profit) ?? ""}`}>{dollars(profit, true)}</div>
          <div className="muted small">profit this season</div>
          <div className="player-won">{n ? `${Math.round((wins / n) * 100)}% won` : "no bets yet"}</div>
          <div className="muted small">{n ? `${wins} of ${n} bets` : ""}</div>
        </div>
      </div>
      {blurb && <p className="player-blurb">{blurb}</p>}
      <FormStrip bets={bets} />
      <StatRow attached stats={[
        { label: "Per $1 Bet", value: pd == null ? "–" : `${pd >= 0 ? "+" : ""}${(pd * 100).toFixed(1)}¢`, tone: toneOf(pd),
          note: rank >= 0 ? `#${rank + 1} of ${ranked.length} on the team` : "needs 10 bets to rank" },
        { label: "Win Streak", value: s.current, hot: s.currentIsBest, note: s.currentIsBest ? "a personal best, still going" : `best ${s.best}` },
        { label: "Best Day", value: best ? dollars(best.pnl, true) : "–", tone: best ? toneOf(best.pnl) : null,
          note: best ? `${dayLabel(best.day)} · ${best.won} of ${best.n} won` : "no bets yet" },
        { label: "Biggest Win / Loss",
          value: <><span className="up">{big.win ? dollars(big.win.pnl, true) : "–"}</span> <span className="muted">/</span>{" "}
            <span className={big.loss ? "down" : ""}>{big.loss ? dollars(big.loss.pnl, true) : "none"}</span></>,
          note: big.loss ? (recover ? `the loss took ${recover} wins to earn back` : "") : "a perfect record so far" },
      ]} />
    </section>
  );
}
