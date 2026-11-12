import { NextRequest, NextResponse } from "next/server";
import { defaultBook, getRealBook } from "@/lib/book";
import { getHistory, getTodayRows, getKillSwitch, getLive, getPolicy, getSeasonStart, getSettlementsSince } from "@/lib/db";
import { headline, only, poolKeys, settledSeries, type RangeKey } from "@/lib/portfolio";

/**
 * Read-only numbers for the iPhone home-screen widget (Scriptable; the design
 * is public/widget/kalshi-desk.js). GET /api/widget?key=WIDGET_TOKEN&days=7
 *
 * The office pool's value now, a line of it over the last `days`, and a short
 * plain-English summary of today: up or down, bets won, who led, what's riding.
 * Real money once a real-money book exists (not the demo practice), the pretend pool until then
 * and while real trading is on a long pause.
 */
export const dynamic = "force-dynamic";

const STALE_MS = 10 * 60_000; // the bot runs every 2 minutes; 10 quiet minutes means trouble

const money = (v: number) =>
  "$" + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (v: number) => (v >= 0 ? "+" : "−") + Math.abs(v * 100).toFixed(1) + "%";

type Row = { key: string; name: string; n: number; won: number; pnl: number };

type Day = { dollars: number; today: number; stopped: boolean; braked: boolean; rows: Row[]; inPlay: number; open: number };

/** Two sentences for the medium widget: up or down, bets won, what's riding. */
function briefText(p: Day): string {
  const settled = p.rows.reduce((s, r) => s + r.n, 0);
  const won = p.rows.reduce((s, r) => s + r.won, 0);
  const head = p.stopped ? `Daily stop hit (${pct(p.today)}): no new bets until midnight.`
    : !settled && Math.abs(p.dollars) < 0.005 ? "Quiet so far today."
    : `${p.dollars >= 0 ? "Up" : "Down"} ${money(p.dollars)} today (${pct(p.today)}).`;
  const bits = [];
  if (settled) bits.push(`${won} of ${settled} bets won`);
  if (p.open) bits.push(`${money(p.inPlay)} riding now`);
  if (p.braked) bits.push("bets halved");
  return bits.length ? `${head} ${bits.join(", ").replace(/^./, (c) => c.toUpperCase())}.` : head;
}

/** The full story of today for the large widget. */
function todayText(p: Day): string {
  const out: string[] = [];
  const settled = p.rows.reduce((s, r) => s + r.n, 0);
  const won = p.rows.reduce((s, r) => s + r.won, 0);
  if (p.stopped) out.push(`Daily stop hit: down ${pct(p.today)} today, no new bets until midnight.`);
  else if (!settled && Math.abs(p.dollars) < 0.005) out.push("Quiet so far today: no bets settled yet.");
  else out.push(`${p.dollars >= 0 ? "Up" : "Down"} ${money(p.dollars)} today (${pct(p.today)}).`);
  if (settled) {
    const best = p.rows[0], worst = p.rows[p.rows.length - 1];
    let s = `${won} of ${settled} bet${settled === 1 ? "" : "s"} won`;
    if (best.pnl > 0) s += `; ${best.name} led with +${money(best.pnl)}`;
    if (worst.pnl < 0) s += `; ${worst.name} lost ${money(worst.pnl)}`;
    out.push(s + ".");
  }
  if (p.open) out.push(`${money(p.inPlay)} riding on ${p.open} bet${p.open === 1 ? "" : "s"} now.`);
  if (p.braked) out.push("Bets are halved until the pool recovers.");
  return out.join(" ");
}

export async function GET(req: NextRequest) {
  const token = process.env.WIDGET_TOKEN;
  const q = req.nextUrl.searchParams;
  if (!token || q.get("key") !== token) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }
  // days=7 by default (or hours=N)
  const hours = Math.min(Math.max(q.get("hours") ? Number(q.get("hours")) : (Number(q.get("days")) || 7) * 24, 1), 24 * 90);
  const range: RangeKey = hours <= 24 ? "day" : hours <= 24 * 7 ? "week" : hours <= 24 * 30 ? "month" : "quarter";

  const [book, real] = await Promise.all([defaultBook(), getRealBook()]);
  const [live, policy, kill] = await Promise.all([getLive(book), getPolicy(book), getKillSwitch(book)]);
  const note = kill.halted ? "Real trading stopped" : book === "pretend" && real?.live && real.paused ? "Real money paused; showing Training" : "";
  if (!live?.pool) return NextResponse.json({ ok: false, error: "the bot hasn't reported yet" }, { status: 503 });
  const pool = live.pool;
  const tz = pool.settings?.timezone || "America/Vancouver";
  const members = poolKeys(live);
  const now = Date.now();
  const start = now - hours * 3_600_000;

  const [history, seasonStart, todayRows] = await Promise.all([
    getHistory(book, policy.season, range),
    getSeasonStart(book, policy.season),
    getTodayRows(book, policy.season, tz),
  ]);

  // The pool's value over the window (or since the season began if that's more recent),
  // counting finished bets only: bets still riding count at what they cost
  const from = Math.max(start, seasonStart ?? start);
  const settled = await getSettlementsSince(book, policy.season, new Date(from).toISOString());
  const full = from === start;
  // The same headline as the website (Kalshi's own balance for real money), not the bot's pool figure,
  // which can be a few cents off it; the chart ends on it too
  const top = headline(live, book === "real", seasonStart ?? now - 86_400_000);
  const series = settledSeries(only(history, members), settled, from, Math.max(now, Date.parse(live.updated_at)), top.worth)
    .map((p) => [p.t, Math.round(p.worth * 100) / 100] as [number, number]);
  const startValue = series[0][1];
  const endValue = series[series.length - 1][1];

  const names = Object.fromEntries(live.employees.map((e) => [e.key, e.name]));
  const rows: Row[] = todayRows.filter((r) => members.includes(r.strategy))
    .map((r) => ({ key: r.strategy, name: names[r.strategy] ?? r.strategy, n: r.n, won: r.won,
                   pnl: Math.round(Number(r.pnl) * 100) / 100 }))
    .sort((a, b) => b.pnl - a.pnl);
  const open = live.positions.filter((p) => members.includes(p.strategy)).length;
  const dollars = Math.round((pool.equity - pool.day_open) * 100) / 100;
  const day: Day = { dollars, today: pool.today, stopped: pool.stopped, braked: pool.braked, rows,
                     inPlay: pool.in_play, open };

  return NextResponse.json({
    ok: true,
    updated_at: live.updated_at,
    stale: now - Date.parse(live.updated_at) > STALE_MS,
    season: policy.season,
    book, // "real" (real money) or "pretend"
    equity: Math.round(top.worth * 100) / 100,
    capital: top.putIn,
    pnl: Math.round(top.profit * 100) / 100,
    in_play: pool.in_play,
    open_bets: open,
    safety: kill.halted ? "halted" : pool.stopped ? "stopped" : pool.braked ? "braked" : "clear",
    mode: live.trading?.mode ?? "paper",
    chart: {
      days: hours / 24,
      since: series[0][0],
      full, // false: the season is younger than the window
      change: Math.round((endValue - startValue) * 100) / 100,
      high: Math.max(...series.map((p) => p[1])),
      low: Math.min(...series.map((p) => p[1])),
    },
    today: {
      dollars,
      pct: pool.today,
      settled: rows.reduce((s, r) => s + r.n, 0),
      won: rows.reduce((s, r) => s + r.won, 0),
      text: (kill.halted ? `${note}: ${kill.reason ?? "by you"}. ` : note ? `${note}. ` : "") + todayText(day),
      brief: (note ? `${note}. ` : "") + briefText(day),
    },
    series,
  }, { headers: { "Cache-Control": "no-store" } });
}
