import AdviceAction from "@/components/AdviceAction";
import AutoRefresh from "@/components/AutoRefresh";
import Avatar from "@/components/Avatar";
import KalshiCheck from "@/components/KalshiCheck";
import NewsFeed from "@/components/NewsFeed";
import MoneyHero from "@/components/MoneyHero";
import RangeTabs from "@/components/RangeTabs";
import Setup from "@/components/Setup";
import StatusPill from "@/components/StatusPill";
import LatestBets from "@/components/LatestBets";
import Records from "@/components/Records";
import ResumeBanner from "@/components/ResumeBanner";
import { OfficePause } from "@/components/OfficeAdmin";
import { isAdmin } from "@/lib/admin";
import { advise, betsPerDay, light } from "@/lib/advice";
import { bookLabel, getOffice, getRealBook, viewedBook, requireViewer } from "@/lib/book";
import {
  getAnalysis, getBets, getBonusPot, getHistory, getKillSwitch, getLive, getMoneyMoves, getNews, getPolicy, getRecentFills, getRoster, getSettlements, getSettlementsSince, isLive, isOffice, withRoster,
} from "@/lib/db";
import { currentUser, officeOf } from "@/lib/session";
import { dollars } from "@/lib/format";
import { headline, only, parseRange, poolKeys, profitSeries, RANGES, settledSeries } from "@/lib/portfolio";
import { poolShare } from "@/lib/hr";

export const dynamic = "force-dynamic";

const RANGE_WORDS = { day: "Today", week: "This week", month: "This month", quarter: "Last 3 months", season: "Since the start" };
// The same ranges for the stat cards ("Bets won (this week)"); a book's season is its whole life
const RANGE_SCOPE = { day: "today", week: "this week", month: "this month", quarter: "last 3 months", season: "lifetime" };

export default async function TeamPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  await requireViewer();
  const params = await searchParams;
  const range = parseRange(params.range, "week");
  // Bets before the range arrive rolled up (getSettlementsSince); a minute early so the roll-up sits before the chart's start
  const days = RANGES[range].days;
  const sinceIso = days == null ? null : new Date(Date.now() - days * 86_400_000 - 60_000).toISOString();
  let data;
  const book = await viewedBook();
  try {
    const realBook = await getRealBook();
    const policy = await getPolicy(book);
    const [live, fills, roster, news, analysis, history, season, admin, settled, pot, bets, kill, marks] = await Promise.all([
      getLive(book), getRecentFills(book, policy.season, 25), getRoster(book), getNews(book, 40),
      getAnalysis(book), getHistory(book, policy.season, range),
      range === "season" ? null : getHistory(book, policy.season, "season"), isAdmin(), sinceIso ? getSettlementsSince(book, policy.season, sinceIso) : getSettlements(book, policy.season),
      getBonusPot(book), getBets(book, policy.season),
      // A friend's office has its own pause; the owner's real book's pause shows on both of the owner's views
      isOffice(book) ? getKillSwitch(book) : realBook ? getKillSwitch("real") : null, getMoneyMoves(book, policy.season),
    ]);
    data = { realBook, live, fills, roster, news, policy, analysis, history, season: season ?? history, settled, pot, bets, kill, marks,
             admin: admin && !isOffice(book), office: await getOffice(book), user: await currentUser() };
  } catch (e) {
    return <Setup error={String(e)} />;
  }
  const { realBook, live, fills, roster, news, policy, analysis, history, season, admin, settled, pot, bets, kill, marks, office, user } = data;
  const label = bookLabel(book, realBook, office);
  if (!live) return <Setup error="The office hasn't reported yet." />;

  const employees = withRoster(live.employees, roster);
  const tz = live.pool?.settings?.timezone || "America/Vancouver";
  // "Your money" is the office pool: the control group's paper money isn't part of it
  const members = new Set(poolKeys(live));
  const team = employees.filter((e) => members.has(e.key));
  const outside = employees.filter((e) => !members.has(e.key) && e.control).map((e) => e.name);
  const pool = live.pool;
  const profits: Record<string, number> = {};
  for (const b of bets) profits[b.strategy] = (profits[b.strategy] ?? 0) + b.pnl;
  // Live: the headline is the Kalshi account itself (the widget shows the same number, lib/portfolio headline)
  const { worth, putIn, kalshi, books, held } = headline(live, isLive(book), season.since);
  const seasonStart = season.since;
  const now = Math.max(Date.parse(live.updated_at), Date.now() - 60_000);

  const mine = settled.filter((s) => members.has(s.strategy));
  const profit = worth - putIn;
  // Finished bets, then the headline's own number for now: bets still riding count at what they cost until the
  // last point, so the line doesn't wobble with them but always ends where the headline says
  const points = settledSeries(only(history, members), mine, Math.max(history.since, seasonStart), now, worth);
  const first = points[0];

  // Each employee's running profit from their settled bets since `since`
  const settledRuns = (since: number) => {
    const out: Record<string, { t: number; v: number }[]> = {};
    const sums: Record<string, number> = {};
    for (const s of settled) {
      sums[s.strategy] = (sums[s.strategy] ?? 0) + s.pnl;
      if (s.t >= since) (out[s.strategy] ??= [{ t: since, v: sums[s.strategy] - s.pnl }]).push({ t: s.t, v: sums[s.strategy] });
    }
    // Nothing settled since `since`: flat at what they'd made before it
    for (const [k, v] of Object.entries(sums)) out[k] ??= [{ t: since, v }];
    return { out, sums };
  };
  const trends = profitSeries(season);
  // The chart and its what-if follow finished bets (see points above)
  const rangeProfits = settledRuns(first?.t ?? seasonStart).out;
  const settledTotals = settledRuns(0).sums;

  const rows = employees
    .map((e) => ({
      e, light: light(e, analysis.evidence[e.key]), trend: trends[e.key] ?? [],
      advice: advise(e, analysis.evidence[e.key], analysis.realism[e.key], policy,
        betsPerDay(analysis.evidence[e.key]?.bets ?? 0, seasonStart)),
    }))
    .sort((a, b) => {
      const away = (r: typeof a) => (r.light.key === "benched" || r.light.key === "fired" ? 1 : 0);
      return away(a) - away(b) || (b.e.pnl ?? 0) - (a.e.pnl ?? 0);
    });
  const todo = rows.filter((r) => r.advice.tone === "act");
  // Yardsticks are supposed to lose, so they don't count as "carrying" or "dragging"
  const working = rows.filter((r) => r.light.key !== "benched" && r.light.key !== "fired" && !r.e.control);
  const best = working[0];
  const worst = working[working.length - 1];
  // This season's award only: news is newest first, so stop at the season's start
  const seasonStarted = news.findIndex((n) => n.kind === "season");
  const award = (seasonStarted < 0 ? news : news.slice(0, seasonStarted)).find((n) => n.kind === "award") ?? null;
  const since = new Date(seasonStart).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const end = points[points.length - 1].t;
  // The last 24 hours of the pool's finished bets, for the latest-bets heading
  const dayAgo = Date.now() - 86_400_000;
  const recent = bets.filter((b) => members.has(b.strategy) && b.t >= dayAgo);
  const lastDay = { n: recent.length, won: recent.filter((b) => b.pnl > 0).length, pnl: recent.reduce((s, b) => s + b.pnl, 0) };

  return (
    <div className="stack">
      <AutoRefresh seconds={60} />
      {/* A paused real book shows on both views (not a long, deliberate pause), with Resume right here */}

      {/* Friends are hands-off: the owner's playbook runs their office, so nothing here needs them */}
      {!isOffice(book) && <section className="card">
        <h2>Needs your attention</h2>
        {todo.length ? (
          <ul className="todo">
            {todo.map(({ e, advice }) => (
              <li key={e.key}>
                <Avatar k={e.key} emoji={e.emoji} size={36} />
                <div className="what">
                  <strong>{advice.headline}</strong>
                  <div className="muted">{advice.why}</div>
                  <div className="row-btns" style={{ marginTop: 6 }}>
                    {admin ? <AdviceAction k={e.key} name={e.name} advice={advice} /> : <span className="muted small">The manager decides.</span>}
                    <a href={`/employee/${e.key}`} className="small">See {e.name} →</a>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="all-good">Nothing needs you.</p>
        )}
      </section>}

      <Records bets={bets.filter((b) => members.has(b.strategy))} employees={employees} tz={tz} />


      <details className="card fold">
        <summary><h2>Office news</h2></summary>
        <NewsFeed items={news.filter((n) => n.kind !== "review").slice(0, 25)} employees={employees} />
      </details>

      <div className="row-btns" style={{ justifyContent: "center" }}>
        <StatusPill updatedAt={live.updated_at} />
      </div>
    </div>
  );
}
