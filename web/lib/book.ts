import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";
import { passwordCookie } from "./admin";
import { getKillSwitch, getLive, home, isLongPause, isOffice, type Book } from "./db";
import { currentUser, officeOf, sessionLookup } from "./session";

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

/**
 * The book this visitor is looking at. A friend: always their own office, nothing else. Everyone else: their pick
 * (Live/Training tabs), else the default; the owner can also open any friend's office (seeing it is a condition of
 * joining, 11-16).
 */
export const viewedBook = cache(async (): Promise<Book> => {
  const user = await currentUser();
  if (user?.role === "friend") return officeOf(user)!;
  const picked = (await cookies()).get(BOOK_COOKIE)?.value;
  if (picked === "pretend") return "pretend";
  if (picked === "real" && (await getRealBook())) return "real";
  // The manager, signed in by passkey or by the manager password (11-16: the password alone opened their own office)
  if (isOffice(picked) && (user?.role === "owner" || (await passwordCookie())) && (await getOffice(picked))) return picked;
  return defaultBook();
});

/**
 * Pages with anyone's numbers need a login (11-15: the owner's books were open to anyone with the link, so a
 * friend could see them). A visitor goes to sign in; a login the database can't check right now gets a "try
 * again" page, never somebody else's books.
 */
export async function requireViewer(): Promise<void> {
  const { user, failed } = await sessionLookup();
  if (user || (await passwordCookie())) return;
  if (failed) throw new Error("Couldn't check your login just now (the database is busy). Try again in a minute.");
  redirect("/login");
}

export type OfficeInfo = { slug: string; name: string; status: string; note: string | null; share: boolean };

/** A friend's office, by its book name; null if there's no such office. */
export const getOffice = cache(async (book: Book): Promise<OfficeInfo | null> => {
  if (!isOffice(book)) return null;
  const rows = await home()`
    SELECT o.slug, coalesce(u.name, o.name) AS name, o.status, o.note, coalesce(u.share_overview, false) AS share
    FROM public.users u LEFT JOIN public.offices o ON o.slug = u.office
    WHERE u.office = ${book.slice("office_".length)}`.catch(() => []);
  if (!rows.length) return null;
  const r = rows[0];
  return { slug: book.slice("office_".length), name: r.name, status: r.status ?? "setup", note: r.note, share: !!r.share };
});


/**
 * What to call a book on screen: Live (orders on Kalshi, numbers from the Kalshi account)
 * or Training (pretend money against real prices, for learning).
 */
export function bookLabel(book: Book, real: RealBook | null, office?: OfficeInfo | null): { name: string; badge: string; title: string } {
  if (isOffice(book)) {
    return { name: "Live", badge: `💵 ${office?.name ?? "Friend"}'s office`, title: "Real orders in their own Kalshi account" };
  }
  if (book === "pretend") {
    return { name: "Training", badge: "🧪 Training", title: "Pretend money against real Kalshi prices: training data" };
  }
  return real?.live
    ? { name: "Live", badge: "💵 Live: real money", title: "Real orders on Kalshi with real money" }
    : { name: "Live", badge: "🎓 Live: Kalshi demo", title: "Real orders on Kalshi's demo exchange (practice money) until the real-money switch" };
}
