"use client";

import { useState } from "react";
import type { Employee, Position } from "@/lib/types";
import { marketLabel } from "@/lib/coin";
import { dollars, shortName } from "@/lib/format";
import Avatar from "./Avatar";
import Card from "./ui/Card";
import StatRow, { toneOf } from "./ui/StatRow";

const SHOWN = 3; // lanes per employee before "more"

/** What one open bet is worth at the market's latest price (the bot's mark, as Kalshi values it). */
const worthNow = (p: Position) => (p.mark == null ? p.cost : p.yes * p.mark + p.no * (1 - p.mark));

/** When a bet probably started, if its fill isn't in the recent list: a typical length for its kind of market. */
const typicalStart = (ticker: string, closes: number) =>
  closes - (/^KXHIGH/.test(ticker) ? 24 * 3600_000 : /15M-/.test(ticker) ? 10 * 60_000 : /^KXBTCD/.test(ticker) ? 25 * 60_000 : 3 * 3600_000);

const left = (ms: number) => {
  const m = Math.round(ms / 60_000);
  return m < 1 ? "any second" : m < 60 ? `${m}m` : `${Math.floor(m / 60)}h ${m % 60}m`;
};

/**
 * Bets riding now as a race (11-16): one lane per bet, grouped by employee. The employee runs from when the bet was
 * placed to a chequered line at the moment it's decided; their trail is green while the bet is ahead at today's
 * price and red while it's behind. The only place on the page a number moves before a bet is decided.
 */
export default function RaceTrack({ positions, employees, held, started, now }: {
  positions: Position[]; employees: Employee[]; held?: number | null;
  /** when each open bet filled, by "strategy|ticker" (from the recent fills) */
  started: Record<string, number>; now: number;
}) {
  const [all, setAll] = useState<string[]>([]);
  if (!positions.length) return null;
  const who = Object.fromEntries(employees.map((e) => [e.key, e]));

  // Nearest to an answer first (11-22, owner): settling (Kalshi stopped listing it, the result is on its way), then
  // deciding (past closing), then bets still trading by time left
  const rank = (c: number | null) => (c == null ? [0, 0] : c <= now ? [1, c] : [2, c]);
  const soonest = (a: { closes: number | null }, b: { closes: number | null }) => {
    const [x, y] = [rank(a.closes), rank(b.closes)];
    return x[0] - y[0] || x[1] - y[1];
  };
  const lanes = positions.map((p) => {
    const closes = p.closes ? Date.parse(p.closes) : null;
    const start = started[`${p.strategy}|${p.ticker}`] ?? (closes ? typicalStart(p.ticker, closes) : now);
    const progress = closes ? Math.max(0.02, Math.min(1, (now - start) / Math.max(60_000, closes - start))) : 1;
    const count = Math.max(p.yes, p.no);
    const yes = p.yes > p.no;
    const paid = count ? p.cost / count : null;
    const price = p.mark == null ? null : yes ? p.mark : 1 - p.mark;
    const what = p.subtitle ? (yes ? p.subtitle : `not ${p.subtitle}`) : yes ? "YES" : "NO";
    return { p, closes, progress, paid, price, what, gain: worthNow(p) - p.cost, win: count - p.cost };
  });
  const groups = Object.values(lanes.reduce<Record<string, typeof lanes>>((g, l) => ((g[l.p.strategy] ??= []).push(l), g), {}))
    // 11-17: a closing time of "none" sorted as Infinity, and
    // Infinity minus Infinity is NaN, which scrambled the whole list (Wendell's soonest bets hid behind "more")
    .map((ls) => ls.sort(soonest))
    .sort((a, b) => soonest(a[0], b[0]));
  const cost = positions.reduce((s, p) => s + p.cost, 0);
  const worth = held ?? positions.reduce((s, p) => s + worthNow(p), 0);
  const pays = lanes.reduce((s, l) => s + l.win + l.p.cost, 0);

  return (
    <Card title="Riding Now" className="race">
      {/* What went in, what Kalshi would pay to buy them back today, and what they pay if every one wins */}
      <StatRow stats={[
        { label: "Put In", value: dollars(cost), note: `${positions.length} open ${positions.length === 1 ? "bet" : "bets"}` },
        { label: "Worth Now", value: dollars(worth), tone: toneOf(worth - cost), note: <>{dollars(worth - cost, true)} at today&apos;s prices</> },
        { label: "If All Win", value: dollars(pays), note: <>{dollars(pays - cost, true)} profit</> },
      ]} />
      {groups.map((ls) => {
        const k = ls[0].p.strategy, e = who[k];
        const open = all.includes(k);
        const gain = ls.reduce((s, l) => s + l.gain, 0);
        return (
          <div key={k} className="race-group">
            <div className="race-group-head">
              <Avatar k={k} emoji={e?.emoji ?? "•"} size={26} />
              <strong>{e ? e.name : k}</strong>
              <span className="muted small">{ls.length} open</span>
              <span className={`race-group-gain ${gain >= 0 ? "up" : "down"}`}>{dollars(gain, true)}</span>
            </div>
            {(open ? ls : ls.slice(0, SHOWN)).map((l) => (
              <div key={l.p.ticker} className={`lane ${l.gain >= 0 ? "ahead" : "behind"}`}>
                <div className="lane-what">
                  <div className="lane-market"><strong>{marketLabel(l.p.ticker)}</strong> · {l.what}</div>
                  <div className="muted small">
                    {dollars(l.p.cost)}{l.paid != null && <> at {Math.round(l.paid * 100)}¢{l.price != null && <> → {Math.round(l.price * 100)}¢</>}</>}
                    {" "}· to win {dollars(l.win)}
                  </div>
                </div>
                <div className="track" aria-label={`${Math.round(l.progress * 100)}% of the way to the finish`}>
                  <div className="track-trail" style={{ width: `${l.progress * 100}%` }} />
                  <div className="track-runner" style={{ left: `${l.progress * 100}%` }}>
                    <Avatar k={k} emoji={e?.emoji ?? "•"} size={22} />
                  </div>
                  <div className="track-finish" />
                </div>
                <div className="lane-side">
                  <div className="lane-left">{l.closes == null ? "settling" : l.closes <= now ? "deciding" : left(l.closes - now)}</div>
                  <div className={l.gain >= 0 ? "up" : "down"}>{dollars(l.gain, true)}</div>
                </div>
              </div>
            ))}
            {ls.length > SHOWN && (
              <button type="button" className="link-btn race-more" onClick={() => setAll((a) => (open ? a.filter((x) => x !== k) : [...a, k]))}>
                {open ? "Show fewer" : `${ls.length - SHOWN} more of ${e ? shortName(e.name) : k}'s bets`}
              </button>
            )}
          </div>
        );
      })}
    </Card>
  );
}
