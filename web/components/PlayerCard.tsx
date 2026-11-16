import type { ReactNode } from "react";
import type { Employee } from "@/lib/types";
import { dollars, perDollar } from "@/lib/format";
import { bestHour, biggest, days, hourLabel, perDollar as ratio, streaks, winsToRecover, type Bet } from "@/lib/records";
import Avatar from "./Avatar";

const COIN_NAMES: Record<string, string> = { BTC: "Bitcoin", ETH: "Ether", SOL: "Solana", XRP: "XRP", DOGE: "Dogecoin",
  HYPE: "HYPE", BNB: "BNB", NEAR: "NEAR", ZEC: "Zcash" };

/**
 * An employee as a trading card: big portrait, name and title, their season's numbers on the back of the card,
 * their rank on the team by cents per $1 (the stat the award goes by), and their form: the last 10 results.
 */
export default function PlayerCard({ e, bets, team, tz, badges, quote }: {
  e: Employee; bets: Bet[]; team: { key: string; bets: Bet[] }[]; tz: string; badges: ReactNode; quote?: string;
}) {
  const mine = bets;
  const n = mine.length;
  const wins = mine.filter((b) => b.pnl > 0).length;
  const pd = ratio(mine);
  const ranked = team.map((t) => ({ key: t.key, pd: ratio(t.bets), n: t.bets.length }))
    .filter((t) => t.pd != null && t.n >= 10).sort((a, b) => b.pd! - a.pd!);
  const rank = ranked.findIndex((t) => t.key === e.key);
  const s = streaks(mine);
  const ds = days(mine, tz).filter((d) => d.n);
  const best = ds.length ? ds.reduce((a, b) => (b.pnl > a.pnl ? b : a)) : null;
  const hour = bestHour(mine, tz, 5);
  const big = biggest(mine);
  const recover = big.loss ? winsToRecover(big.loss.pnl, mine) : null;
  const coins = [...new Set(mine.map((b) => b.coin))];
  const form = mine.slice(-10);
  const avgPrice = mine.filter((b) => b.price != null);
  const price = avgPrice.length ? avgPrice.reduce((s2, b) => s2 + b.price!, 0) / avgPrice.length : null;
  const dayLabel = (d: string) => new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

  const stats: [string, ReactNode, string?][] = [
    ["¢ per $1", <span className={pd == null ? "" : pd >= 0 ? "up" : "down"}>{perDollar(pd).replace(" per $1", "")}</span>,
      rank >= 0 ? `#${rank + 1} of ${ranked.length} on the team` : "needs 10 bets to rank"],
    ["Won", n ? `${Math.round((wins / n) * 100)}%` : "–", `${wins} of ${n} bets`],
    ["Profit", <span className={(e.pnl ?? 0) >= 0 ? "up" : "down"}>{dollars(e.pnl ?? 0, true)}</span>, "this season"],
    ["Win streak", String(s.current), `best ${s.best}`],
    ["Best day", best ? dollars(best.pnl, true) : "–", best ? dayLabel(best.day) : ""],
    ["Golden hour", hour ? hourLabel(hour.best.hour) : "–", hour ? `${dollars(hour.best.pnl, true)} over ${hour.best.n} bets` : "not enough bets"],
    ["Biggest loss", big.loss ? <span className="down">{dollars(big.loss.pnl, true)}</span> : "none yet",
      big.loss ? (recover ? `${recover} wins to earn back` : "") : "a perfect record"],
    ["Typical price", price != null ? `${Math.round(price * 100)}¢` : "–", coins.length ? coins.map((c) => COIN_NAMES[c] ?? c).join(", ") : ""],
  ];

  return (
    <section className={`player-card ${e.control ? "player-yard" : ""}`}>
      <div className="player-front">
        <div className="player-portrait"><Avatar k={e.key} emoji={e.emoji} size={112} /></div>
        <div className="player-id">
          <div className="player-title">{e.title}</div>
          <h1 className="player-name">{e.name}</h1>
          <div className="row-btns player-badges">{badges}</div>
          {quote && <div className="player-quote">“{quote}”</div>}
          {form.length > 0 && (
            <div className="player-form" aria-label={`Last ${form.length} results`}>
              <span className="muted small">Form</span>
              {form.map((b, i) => <span key={i} className={`form-pip ${b.pnl > 0 ? "w" : "l"}`} title={dollars(b.pnl, true)}>{b.pnl > 0 ? "W" : "L"}</span>)}
            </div>
          )}
        </div>
      </div>
      <dl className="player-stats">
        {stats.map(([k, v, note]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
            {note && <dd className="player-note">{note}</dd>}
          </div>
        ))}
      </dl>
    </section>
  );
}

