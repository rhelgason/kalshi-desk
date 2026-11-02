import { getLive, getPolicy, getRecentFills, type Book } from "@/lib/db";
import { coinOfTicker } from "@/lib/coin";
import { money, shortName } from "@/lib/format";

/**
 * Broadcast look only: the scrolling results crawl along the top of the screen, like the bottom line on a
 * sports channel. Finished bets, newest first, then the desk's score.
 */
export default async function Ticker({ book }: { book: Book }) {
  let items: { k: string; text: string; tone: "up" | "down" | "flat" }[] = [];
  try {
    const [live, policy] = await Promise.all([getLive(book), getPolicy(book)]);
    const fills = await getRecentFills(book, policy.season, 20);
    const names = Object.fromEntries((live?.employees ?? []).map((e) => [e.key, `${e.emoji} ${shortName(e.name)}`]));
    items = fills.filter((f) => f.pnl != null).map((f) => ({
      k: String(f.id),
      text: `${names[f.strategy] ?? f.strategy} ${coinOfTicker(f.ticker) || ""} ${Math.round(f.price * 100)}¢ · ${f.pnl! > 0 ? "W" : "L"} ${money(f.pnl)}`,
      tone: f.pnl! > 0 ? "up" : "down",
    }));
    const pool = live?.pool;
    if (pool) items.unshift({ k: "desk", text: `DESK ${money(pool.equity, false)} · ${money(pool.pnl)} SEASON`, tone: pool.pnl >= 0 ? "up" : "down" });
  } catch {
    return null;
  }
  if (!items.length) return null;
  const run = items.map((i) => <span key={i.k} className={`tick ${i.tone}`}>{i.text}</span>);
  return (
    <div className="ticker" aria-label="Latest results">
      <span className="ticker-tag">LIVE</span>
      <div className="ticker-track"><div className="ticker-inner">{run}{run}</div></div>
    </div>
  );
}
