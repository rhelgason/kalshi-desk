import { NextResponse } from "next/server";
import {
  getAnalysis, getBetsSince, getBonusPot, getDays, getLive, getMoneyIn, getMoneyMoves, getNews, getPolicy, getRecentFills, getRoster,
  home, type Book,
} from "@/lib/db";
import { betWindow } from "@/lib/season";

/**
 * Fills the caches for the owner's two offices on the week (11-16), so nobody waits for the first load after each
 * bot run: the server's bot calls this when it finishes (desk/cloud.py warm_site). It asks for exactly what the home
 * page asks for, with the same arguments, then answers only "ok"; nothing is shown or changed. Anyone may call it:
 * a second call within a run finds everything already cached.
 */
export const dynamic = "force-dynamic";

async function warm(book: Book) {
  const policy = await getPolicy(book);
  const tz = policy.pool.timezone || "America/Vancouver";
  const { since, today } = betWindow(tz);
  await Promise.all([
    getLive(book), getRecentFills(book, policy.season, 100), getRoster(book), getMoneyIn(book, policy.season),
    getDays(book, policy.season, tz), getBetsSince(book, policy.season, since, today), getMoneyMoves(book, policy.season),
  ]);
  // The team and the news come just after the top card on the page; same here
  await Promise.all([getAnalysis(book), getNews(book, 40), getBonusPot(book)]);
}

export async function GET() {
  const t = Date.now();
  // Nobody on the site for 20 minutes: nothing to warm (the next visitor's first load fills the caches)
  const seen = await home()`SELECT updated_at FROM public.status WHERE key = '_seen'`.catch(() => []);
  const last = seen[0] ? Date.parse(String(seen[0].updated_at)) : 0;
  if (Date.now() - last > 20 * 60_000) return NextResponse.json({ ok: true, skipped: "nobody on the site" });
  // 11-23: the real book only (Training is pretend; its first visitor after a change waits a moment)
  const done = await Promise.allSettled((["real"] as Book[]).map(warm));
  return NextResponse.json({ ok: done.every((d) => d.status === "fulfilled"), ms: Date.now() - t });
}
