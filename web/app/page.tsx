import AdviceAction from "@/components/AdviceAction";
import AutoRefresh from "@/components/AutoRefresh";
import Avatar from "@/components/Avatar";
import CoinGauges from "@/components/CoinGauges";
import KalshiCheck from "@/components/KalshiCheck";
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
import { bookLabel, getRealBook, viewedBook, viewedCoin } from "@/lib/book";
import { COIN_NAMES, onCoin } from "@/lib/coin";
import {
  getAnalysis, getHistory, getLive, getNews, getPolicy, getPoolRecord, getRecentFills, getRoster, getSettlements, withRoster,
} from "@/lib/db";
import { dollars, pct } from "@/lib/format";
import { only, parseRange, poolKeys, portfolioSeries, profitSeries, RANGES } from "@/lib/portfolio";
import { poolShare } from "@/lib/hr";

export const dynamic = "force-dynamic";

const RANGE_WORDS = { day: "Today", week: "This week", month: "This month", quarter: "Last 3 months", season: "Since the start" };

export default async function Home({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = await searchParams;
  const range = parseRange(params.range);
  let data;
  try {
    const [book, realBook, coin] = await Promise.all([viewedBook(), getRealBook(), viewedCoin()]);
    const policy = await getPolicy(book);
    const [live, fills, roster, news, analysis, history, season, admin, settled] = await Promise.all([
      getLive(book), getRecentFills(book, policy.season, coin === "all" ? 25 : 80), getRoster(book), getNews(book, 40),
      getAnalysis(book), getHistory(book, policy.season, range),
      range === "season" ? null : getHistory(book, policy.season, "season"), isAdmin(), getSettlements(book, policy.season),
    ]);
    data = { book, realBook, coin, live, fills, roster, news, policy, analysis, history, season: season ?? history, admin, settled };
  } catch (e) {
    return <Setup error={String(e)} />;
  }
  const { book, realBook, coin, live, fills, roster, news, policy, analysis, history, season, admin, settled } = data;
  const label = bookLabel(book, realBook);
  if (!live) return <Setup error="The bot hasn't published a status yet. Is it running?" />;

  const employees = withRoster(live.employees, roster);
  const tz = live.pool?.settings?.timezone || "America/Vancouver";
  const record = live.pool
    ? await getPoolRecord(book, policy.season, poolKeys(live), tz)
      .catch((e) => { console.error("pool record failed:", e); return undefined; })
    : undefined;
  // "Your money" is the office pool: the control group's paper money isn't part of it
  const members = new Set(poolKeys(live));
  const team = employees.filter((e) => members.has(e.key));
  const pool = live.pool;
  const books = book === "real" ? live.trading?.books ?? null : null;
  // Live: the headline is the Kalshi account itself (cash + what Kalshi says open bets are worth)
  const kalshi = books ? books.balance + (books.held ?? 0) : null;
  const worth = kalshi ?? pool?.equity ?? team.reduce((s, e) => s + (e.equity ?? 0), 0);
  const putIn = pool?.capital ?? team.reduce((s, e) => s + (e.starting_cash ?? 0), 0);
  const seasonStart = season.since;
  const now = Math.max(Date.parse(live.updated_at), Date.now() - 60_000);

  // One coin: everything below comes from that coin's finished bets (an account value can't be split by coin)
  const coinView = coin !== "all";
  const mine = settled.filter((s) => members.has(s.strategy) && (!coinView || s.coin === coin));
  const coinProfit = mine.reduce((s, r) => s + r.pnl, 0);
  const profit = coinView ? coinProfit : worth - putIn;

  let points;
  if (coinView) {
    const days = RANGES[range].days;
    const from = days == null ? seasonStart : Math.max(seasonStart, now - days * 86_400_000);
    let run = mine.filter((s) => s.t < from).reduce((s, r) => s + r.pnl, 0);
    points = [{ t: from, worth: run, putIn: 0 }];
    for (const s of mine.filter((s) => s.t >= from)) points.push({ t: s.t, worth: (run += s.pnl), putIn: 0 });
    points.push({ t: now, worth: coinProfit, putIn: 0 });
  } else {
    // End the line at the live numbers so the chart's "now" matches the headline
    const past = portfolioSeries(only(history, members));
    points = [...past, { t: Math.max(Date.parse(live.updated_at), past[past.length - 1]?.t ?? 0), worth, putIn }];
  }
  const first = points[0];
  const rangeProfit = first ? (coinView ? coinProfit - first.worth : profit - (first.worth - first.putIn)) : null;

  // Each employee's running profit on this coin, from their settled bets since `since`
  const coinRuns = (since: number) => {
    const out: Record<string, { t: number; v: number }[]> = {};
    const sums: Record<string, number> = {};
    for (const s of settled.filter((s) => s.coin === coin)) {
      sums[s.strategy] = (sums[s.strategy] ?? 0) + s.pnl;
      if (s.t >= since) (out[s.strategy] ??= [{ t: since, v: sums[s.strategy] - s.pnl }]).push({ t: s.t, v: sums[s.strategy] });
    }
    return { out, sums };
  };
  const trends = coinView ? coinRuns(seasonStart).out : profitSeries(season);
  const rangeProfits = coinView ? coinRuns(first?.t ?? seasonStart).out : range === "season" ? trends : profitSeries(history);
  const coinTotals = coinView ? coinRuns(0).sums : {};
  const pnlOf = (k: string, all?: number) => (coinView ? coinTotals[k] ?? 0 : all ?? 0);
  const coinCounts: Record<string, { n: number; won: number; pnl: number }> = {};
  for (const s of settled.filter((s) => s.coin === coin)) {
    const c = (coinCounts[s.strategy] ??= { n: 0, won: 0, pnl: 0 });
    c.n += 1; c.won += s.pnl > 0 ? 1 : 0; c.pnl += s.pnl;
  }

  const rows = employees
    .map((e) => ({
      e, light: light(e, analysis.evidence[e.key]), trend: trends[e.key] ?? [],
      advice: advise(e, analysis.evidence[e.key], analysis.realism[e.key], policy,
        betsPerDay(analysis.evidence[e.key]?.bets ?? 0, seasonStart)),
    }))
    .sort((a, b) => {
      const away = (r: typeof a) => (r.light.key === "benched" || r.light.key === "fired" ? 1 : 0);
      return away(a) - away(b) || pnlOf(b.e.key, b.e.pnl) - pnlOf(a.e.key, a.e.pnl);
    });
  const todo = rows.filter((r) => r.advice.tone === "act");
  // Yardsticks are supposed to lose, so they don't count as "carrying" or "dragging"
  const working = rows.filter((r) => r.light.key !== "benched" && r.light.key !== "fired" && !r.e.control);
  const best = working[0];
  const worst = working[working.length - 1];
  const award = news.find((n) => n.kind === "award") ?? null;
  const since = new Date(seasonStart).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const coinName = COIN_NAMES[coin].toLowerCase();
  const on = coinView ? ` on ${coinName}` : "";

  return (
    <div className="stack">
      <AutoRefresh seconds={60} />

      <section className="card money-hero">
        <div className="row-btns" style={{ justifyContent: "space-between" }}>
          <span className="label">{coinView ? `${COIN_NAMES[coin]} only` : kalshi != null ? "On Kalshi" : "Your money"}</span>
          <span className={`badge book-${label.name.toLowerCase()}`} title={label.title}>{label.badge}</span>
        </div>
        {coinView ? (
          <>
            <div className={`big-number ${coinProfit >= 0 ? "up" : "down"}`}>{dollars(coinProfit, true)}</div>
            <div className="muted">
              Profit from {mine.length} finished {coinName} bet{mine.length === 1 ? "" : "s"} since {since}
              {mine.length ? <> ({pct(mine.filter((s) => s.pnl > 0).length / mine.length, false, 0)} won)</> : null}.
              {" "}The whole pool is {dollars(worth)} across all coins.
            </div>
          </>
        ) : (
          <>
            <div className="big-number">{dollars(worth)}</div>
            <div className={`change ${profit >= 0 ? "up" : "down"}`}>
              {profit >= 0 ? "▲" : "▼"} {dollars(Math.abs(profit))} ({pct(Math.abs(profit / (putIn || 1)), false, 1)}) {profit >= 0 ? "profit" : "loss"} since {since}
            </div>
            {books && <KalshiCheck books={books} env={realBook?.env ?? "demo"} equity={pool?.equity ?? null} />}
            <div className="muted">
              {team.length} employees share one pool. An Associate&apos;s bet is {poolShare(1, pool?.settings.bet_pct)} of it
              {pool ? <> ({dollars(pool.bet)} right now)</> : null}.
            </div>
          </>
        )}
        {pool && (coinView
          ? <CoinGauges coin={coin} settled={mine} tz={tz} names={Object.fromEntries(employees.map((e) => [e.key, e.name]))}
              positions={live.positions.filter((p) => members.has(p.strategy) && onCoin(p.ticker, coin))} />
          : <PoolGauges pool={pool} record={record} />)}

        <RangeTabs value={range} path="/" />
        <MoneyChart points={points} period={RANGE_WORDS[range]} profitOnly={coinView ? `${coinName} profit` : undefined}
          team={rows.map(({ e, light: l }) => ({
            key: e.key, name: e.name, emoji: e.emoji, light: l.key, bets: analysis.evidence[e.key]?.bets ?? 0,
            profit: [...(rangeProfits[e.key] ?? []), { t: points[points.length - 1].t, v: pnlOf(e.key, e.pnl) }],
          }))} />
        {range !== "season" && rangeProfit != null && (
          <p className="range-change">
            {RANGE_WORDS[range]}: <strong className={rangeProfit >= 0 ? "up" : "down"}>{rangeProfit >= 0 ? "▲ up" : "▼ down"} {dollars(Math.abs(rangeProfit))}</strong>
          </p>
        )}
        {best && worst && (
          <p className="summary">
            {pnlOf(best.e.key, best.e.pnl) > 0
              ? <><strong>{best.e.name}</strong> is carrying the team{on} ({dollars(pnlOf(best.e.key, best.e.pnl), true)})</>
              : <>Nobody&apos;s making money{on} yet</>}
            {worst !== best && pnlOf(worst.e.key, worst.e.pnl) < 0 && <>, and <strong>{worst.e.name}</strong> is doing worst ({dollars(pnlOf(worst.e.key, worst.e.pnl), true)})</>}.
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
        <h2>Your team{coinView ? `: ${coinName} only` : ""}</h2>
        <TeamList rows={rows} coin={coinView ? { name: coin, stats: coinCounts } : undefined} />
      </section>

      <Spotlight award={award} employees={employees} policy={policy} />

      <details className="card fold">
        <summary><h2>Latest bets{on}</h2></summary>
        <TradeFeed fills={fills.filter((f) => onCoin(f.ticker, coin)).slice(0, 25)} employees={employees} />
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
