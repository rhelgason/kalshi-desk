import { NextRequest, NextResponse } from "next/server";
import { db, getHistory, getLive, getPolicy } from "@/lib/db";
import { only, poolKeys, portfolioSeries, type RangeKey } from "@/lib/portfolio";

/**
 * Read-only numbers for the iPhone home-screen widget (Scriptable; see
 * widget/kalshi-desk.js). GET /api/widget?key=WIDGET_TOKEN&hours=6
 *
 * The office pool's value now, how much it gained or lost over the last
 * `hours`, a line of its value over that time, today's change, and whether
 * a guardrail (daily stop, slump brake) is on.
 */
export const dynamic = "force-dynamic";

const STALE_MS = 10 * 60_000; // the bot runs every 2 minutes; 10 quiet minutes means trouble

export async function GET(req: NextRequest) {
  const token = process.env.WIDGET_TOKEN;
  if (!token || req.nextUrl.searchParams.get("key") !== token) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }
  const hours = Math.min(Math.max(Number(req.nextUrl.searchParams.get("hours")) || 6, 1), 24 * 30);
  const range: RangeKey = hours <= 24 ? "day" : hours <= 24 * 7 ? "week" : "month";

  const [live, policy] = await Promise.all([getLive(), getPolicy()]);
  if (!live?.pool) return NextResponse.json({ ok: false, error: "the bot hasn't reported yet" }, { status: 503 });
  const pool = live.pool;
  const members = poolKeys(live);
  const now = Date.now();
  const start = now - hours * 3_600_000;
  const startIso = new Date(start).toISOString();

  const [history, settled] = await Promise.all([
    getHistory(policy.season, range),
    db()`SELECT strategy, count(*)::int AS n, sum(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::int AS won, sum(pnl) AS pnl
         FROM settlements WHERE season = ${policy.season} AND ts >= ${startIso}
         GROUP BY strategy`,
  ]);

  // The pool's value over the window, ending with the bot's latest number
  const all = portfolioSeries(only(history, members));
  const before = all.filter((p) => p.t <= start).pop();
  const series = [...(before ? [{ ...before, t: start }] : []), ...all.filter((p) => p.t > start)]
    .map((p) => [p.t, Math.round(p.worth * 100) / 100] as [number, number]);
  series.push([Date.parse(live.updated_at), pool.equity]);
  const startValue = series[0][1];

  const names = Object.fromEntries(live.employees.map((e) => [e.key, `${e.emoji} ${e.name}`]));
  const mine = settled.filter((r) => members.includes(r.strategy))
    .map((r) => ({ key: r.strategy as string, name: names[r.strategy] ?? r.strategy, n: r.n as number,
                   won: r.won as number, pnl: Math.round(Number(r.pnl) * 100) / 100 }))
    .sort((a, b) => b.pnl - a.pnl);
  const open = live.positions.filter((p) => members.includes(p.strategy)).length;

  const safety = pool.stopped ? { key: "stopped", text: "⏸ Stopped for today" }
    : pool.braked ? { key: "braked", text: "🐢 Bets halved" }
    : { key: "clear", text: "✅ All clear" };

  return NextResponse.json({
    ok: true,
    updated_at: live.updated_at,
    stale: now - Date.parse(live.updated_at) > STALE_MS,
    season: policy.season,
    equity: pool.equity,
    capital: pool.capital,
    pnl: pool.pnl,
    today: pool.today,
    today_dollars: Math.round((pool.equity - pool.day_open) * 100) / 100,
    in_play: pool.in_play,
    open_bets: open,
    safety,
    window: {
      hours,
      change: Math.round((pool.equity - startValue) * 100) / 100,
      settled: mine.reduce((s, r) => s + r.n, 0),
      won: mine.reduce((s, r) => s + r.won, 0),
      best: mine[0] ?? null,
      worst: mine.length > 1 ? mine[mine.length - 1] : null,
    },
    series,
  }, { headers: { "Cache-Control": "no-store" } });
}
