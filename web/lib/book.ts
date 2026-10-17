import { cookies } from "next/headers";
import { cache } from "react";
import { db, type Book } from "./db";

export type { Book };

/**
 * Two books run side by side (desk.real.yaml): the real-money pool and the pretend
 * pool (training data). Each has its own roster, levels and records; the real
 * book's tables live in the database's "real" schema.
 *
 * While the real book trades Kalshi's demo exchange it's "Practice", not real money.
 */
export const BOOK_COOKIE = "book";

export type RealBook = { env: string; live: boolean; updated_at: string };

/** The real book, if the bot has ever reported one (null until then). live = real money (not the demo). */
export const getRealBook = cache(async (): Promise<RealBook | null> => {
  try {
    const rows = await db("real")`SELECT data FROM status WHERE key = 'live'`;
    if (!rows.length) return null;
    const live = JSON.parse(rows[0].data);
    return { env: live.env ?? "demo", live: (live.env ?? "demo") === "prod", updated_at: live.updated_at };
  } catch {
    return null; // no real schema yet
  }
});

/** The book to show when nobody has picked one: real money once it exists, the pretend pool until then. */
export async function defaultBook(): Promise<Book> {
  return (await getRealBook())?.live ? "real" : "pretend";
}

/** The book this visitor is looking at: their pick (Real/Pretend tabs), else the default. */
export const viewedBook = cache(async (): Promise<Book> => {
  const picked = (await cookies()).get(BOOK_COOKIE)?.value;
  if (picked === "pretend") return "pretend";
  if (picked === "real" && (await getRealBook())) return "real";
  return defaultBook();
});

/** What to call a book on screen. */
export function bookLabel(book: Book, real: RealBook | null): { name: string; badge: string; title: string } {
  if (book === "pretend") {
    return { name: "Pretend", badge: "🧪 Pretend money", title: "Training data: pretend money against real Kalshi prices" };
  }
  return real?.live
    ? { name: "Real", badge: "💵 Real money", title: "Real orders on Kalshi with real money" }
    : { name: "Practice", badge: "🎓 Practice", title: "The real-money setup, trading Kalshi's demo exchange with practice money" };
}
