import AdviceAction from "@/components/AdviceAction";
import AutoRefresh from "@/components/AutoRefresh";
import Avatar from "@/components/Avatar";
import NewsFeed from "@/components/NewsFeed";
import MoneyChart from "@/components/MoneyChart";
import RangeTabs from "@/components/RangeTabs";
import Setup from "@/components/Setup";
import PoolGauges from "@/components/PoolGauges";
import Spotlight from "@/components/Spotlight";
import StatusPill from "@/components/StatusPill";
import TeamList from "@/components/TeamList";
import TradeFeed from "@/components/TradeFeed";
import { isAdmin } from "@/lib/admin";
import { advise, betsPerDay, light } from "@/lib/advice";
import { getAnalysis, getHistory, getLive, getNews, getPolicy, getPoolRecord, getRecentFills, getRoster, withRoster } from "@/lib/db";
import { dollars, pct } from "@/lib/format";
import { only, parseRange, poolKeys, portfolioSeries, profitSeries } from "@/lib/portfolio";
import { poolShare } from "@/lib/hr";

export const dynamic = "force-dynamic";

const RANGE_WORDS = { day: "Today", week: "This week", month: "This month", quarter: "Last 3 months", season: "Since the start" };

export default async function Home({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const range = parseRange((await searchParams).range);
  let data;
  try {
    const policy = await getPolicy();
    const [live, fills, roster, news, analysis, history, season, admin] = await Promise.all([
      getLive(), getRecentFills(policy.season, 25), getRoster(), getNews(40), getAnalysis(),
      getHistory(policy.season, range), range === "season" ? null : getHistory(policy.season, "season"), isAdmin(),
    ]);
    data = { live, fills, roster, news, policy, analysis, history, season: season ?? history, admin };
  } catch (e) {
    return <Setup error={String(e)} />;
  }
  const { live, fills, roster, news, policy, analysis, history, season, admin } = data;
  if (!live) return <Setup error="The bot hasn't published a status yet. Is it running?" />;

  const employees = withRoster(live.employees, roster);
  const record = live.pool
    ? await getPoolRecord(policy.season, poolKeys(live), live.pool.settings?.timezone || "America/Vancouver")
      .catch((e) => { console.error("pool record failed:", e); return undefined; })
    : undefined;
  // "Your money" is the office pool: the control group's paper money isn't part of it
  const members = new Set(poolKeys(live));
  const team = employees.filter((e) => members.has(e.key));
  const pool = live.pool;
  const worth = pool?.equity ?? team.reduce((s, e) => s + (e.equity ?? 0), 0);
  const putIn = pool?.capital ?? team.reduce((s, e) => s + (e.starting_cash ?? 0), 0);
  const profit = worth - putIn;
  const seasonStart = season.since;

  // End the line at the live numbers so the chart's "now" matches the headline
  const past = portfolioSeries(only(history, members));
  const points = [...past, { t: Math.max(Date.parse(live.updated_at), past[past.length - 1]?.t ?? 0), worth, putIn }];
  const first = points[0];
  const rangeProfit = first ? profit - (first.worth - first.putIn) : null;

  const trends = profitSeries(season);
  const rangeProfits = range === "season" ? trends : profitSeries(history);
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
  const award = news.find((n) => n.kind === "award") ?? null;
  const since = new Date(seasonStart).toLocaleDateString("en-US", { month: "short", day: "numeric" });

  return (
    <div className="stack">
      <AutoRefresh seconds={60} />

      <section className="card money-hero">
        <div className="row-btns" style={{ justifyContent: "space-between" }}>
          <span className="label">Your money</span>
          <span className="badge" title="The employees trade with pretend money against real Kalshi prices">🧪 Pretend money</span>
        </div>
        <div className="big-number">{dollars(worth)}</div>
        <div className={`change ${profit >= 0 ? "up" : "down"}`}>
          {profit >= 0 ? "▲" : "▼"} {dollars(Math.abs(profit))} ({pct(Math.abs(profit / (putIn || 1)), false, 1)}) {profit >= 0 ? "profit" : "loss"} since {since}
        </div>
        <div className="muted">
          {team.length} employees share one pool. An Associate&apos;s bet is {poolShare(1, pool?.settings.bet_pct)} of it
          {pool ? <> ({dollars(pool.bet)} right now)</> : null}.
        </div>
        {pool && <PoolGauges pool={pool} record={record} />}

        <RangeTabs value={range} path="/" />
        <MoneyChart points={points} period={RANGE_WORDS[range]}
          team={rows.map(({ e, light: l }) => ({
            key: e.key, name: e.name, emoji: e.emoji, light: l.key, bets: analysis.evidence[e.key]?.bets ?? 0,
            profit: [...(rangeProfits[e.key] ?? []), { t: points[points.length - 1].t, v: e.pnl ?? 0 }],
          }))} />
        {range !== "season" && rangeProfit != null && (
          <p className="range-change">
            {RANGE_WORDS[range]}: <strong className={rangeProfit >= 0 ? "up" : "down"}>{rangeProfit >= 0 ? "▲ up" : "▼ down"} {dollars(Math.abs(rangeProfit))}</strong>
          </p>
        )}
        {best && worst && (
          <p className="summary">
            {(best.e.pnl ?? 0) > 0
              ? <><strong>{best.e.name}</strong> is carrying the team ({dollars(best.e.pnl, true)})</>
              : <>Nobody&apos;s making money yet</>}
            {worst !== best && (worst.e.pnl ?? 0) < 0 && <>, and <strong>{worst.e.name}</strong> is having the worst day ({dollars(worst.e.pnl, true)})</>}.
          </p>
        )}
      </section>

      <section className="card">
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
          <p className="all-good">✅ Nothing needs you. Go outside.</p>
        )}
      </section>

      <section className="card">
        <h2>Your team</h2>
        <TeamList rows={rows} />
      </section>

      <Spotlight award={award} employees={employees} policy={policy} />

      <details className="card fold">
        <summary><h2>Latest bets</h2></summary>
        <TradeFeed fills={fills} employees={employees} />
      </details>
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
