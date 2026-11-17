import { cookies } from "next/headers";
import type { History } from "./portfolio";
import type { LiveStatus } from "./types";

/**
 * The manager's preview of the new-user tour shows their office as a friend's looks on day one (11-17): no money in,
 * no bets yet. Only for the manager, only while the preview runs (a cookie the tour sets and clears).
 */
export const FRESH_COOKIE = "nux_fresh";

export async function previewFresh(admin: boolean): Promise<boolean> {
  return admin && (await cookies()).get(FRESH_COOKIE)?.value === "1";
}

/** A live status with nothing in it yet: the same staff, $0, nothing riding. */
export function emptyLive(live: LiveStatus): LiveStatus {
  return {
    ...live,
    positions: [],
    employees: live.employees.map((e) => ({ ...e, equity: 0, starting_cash: 0, pnl: 0, fills: 0, cash: 0 })),
    pool: live.pool ? { ...live.pool, equity: 0, capital: 0, pnl: 0, cash: 0, in_play: 0, day_open: 0, today: 0, peak: 0,
                        stopped: false, stopped_at: null, braked: false } : live.pool,
    trading: live.trading ? { ...live.trading, books: undefined } : live.trading,
  } as LiveStatus;
}

export function emptyHistory(h: History, now: number): History {
  return { ...h, since: now, points: {}, seeds: {}, starting: {}, transfers: [] };
}
