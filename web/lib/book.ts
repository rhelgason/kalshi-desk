import { cookies } from "next/headers";
import { cache } from "react";
import { getKillSwitch, getLive, isLongPause, type Book } from "./db";

export type { Book };

/**
 * Two books run side by side (desk.real.yaml): the real-money pool and the pretend
 * pool (training data). Each has its own roster, levels and records; the real
 * book's tables live in the database's "real" schema.
 *
 * While the real book trades Kalshi's demo exchange it's "Practice", not real money.
 */
export const BOOK_COOKIE = "book";

export type RealBook = { env: string; live: boolean; updated_at: string; paused: boolean };

/**
 * The real book, if the bot has ever reported one (null until then). live = real money (not the demo);
 * paused = real trading is on a long pause (see isLongPause).
 */
export const getRealBook = cache(async (): Promise<RealBook | null> => {
  try {
    const [live, kill] = await Promise.all([getLive("real"), getKillSwitch("real")]);
    if (!live) return null;
    return { env: live.env ?? "demo", live: (live.env ?? "demo") === "prod", updated_at: live.updated_at,
             paused: isLongPause(kill) };
  } catch {
    return null; // no real schema yet
  }
});

/**
 * The book to show when nobody has picked one (and on the phone widget): real money once it exists,
 * the pretend pool until then or while real trading is on a long pause.
 */
export async function defaultBook(): Promise<Book> {
  const real = await getRealBook();
  return real?.live && !real.paused ? "real" : "pretend";
}

/** The book this visitor is looking at: their pick (Real/Pretend tabs), else the default. */
export const viewedBook = cache(async (): Promise<Book> => {
  const picked = (await cookies()).get(BOOK_COOKIE)?.value;
  if (picked === "pretend") return "pretend";
  if (picked === "real" && (await getRealBook())) return "real";
  return defaultBook();
});

/**
 * What to call a book on screen: Live (orders on Kalshi, numbers from the Kalshi account)
 * or Training (pretend money against real prices, for learning).
 */
export function bookLabel(book: Book, real: RealBook | null): { name: string; badge: string; title: string } {
  if (book === "pretend") {
    return { name: "Training", badge: "🧪 Training", title: "Pretend money against real Kalshi prices: training data" };
  }
  return real?.live
    ? { name: "Live", badge: "💵 Live: real money", title: "Real orders on Kalshi with real money" }
    : { name: "Live", badge: "🎓 Live: Kalshi demo", title: "Real orders on Kalshi's demo exchange (practice money) until the real-money switch" };
}
