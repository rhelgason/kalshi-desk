import { cookies } from "next/headers";
import type { History } from "./portfolio";
import type { LiveStatus } from "./types";

/**
 * The manager's preview of the new-user tour shows the app as a new friend sees it on day one (11-17): their pretend
 * Kalshi balance and no bets yet, with a friend's header, cockpit and Office Rules. Only for the manager, only while
 * the preview runs (a cookie holding the pretend balance, which the tour sets and clears).
 * Returns the pretend balance in dollars, or null when no preview is running.
 */
export const FRESH_COOKIE = "nux_fresh";

export async function previewFresh(admin: boolean): Promise<number | null> {
  if (!admin) return null;
  const v = (await cookies()).get(FRESH_COOKIE)?.value;
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

/** A live status with nothing done yet: the same staff, `cash` in the pool, nothing riding. */
export function emptyLive(live: LiveStatus, cash = 0): LiveStatus {
  return {
    ...live,
    positions: [],
    employees: live.employees.map((e) => ({ ...e, equity: 0, starting_cash: 0, pnl: 0, fills: 0, cash: 0 })),
    pool: live.pool ? { ...live.pool, equity: cash, capital: cash, pnl: 0, cash, in_play: 0, day_open: cash, today: 0, peak: cash,
                        stopped: false, stopped_at: null, braked: false } : live.pool,
    trading: live.trading ? { ...live.trading, books: undefined } : live.trading,
  } as LiveStatus;
}

/** A season that starts now, with `cash` put in (given to `who`, any one member: only the total is drawn). */
export function emptyHistory(h: History, now: number, cash = 0, who?: string): History {
  return { ...h, since: now, points: {}, seeds: {}, starting: who && cash ? { [who]: cash } : {}, transfers: [] };
}
