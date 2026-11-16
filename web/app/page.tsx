import AutoRefresh from "@/components/AutoRefresh";
import LatestBets from "@/components/LatestBets";
import HeroChart, { type WhatIfBet, type WhatIfMember } from "@/components/HeroChart";
import HeroFacts from "@/components/HeroFacts";
import OfficeHero from "@/components/OfficeHero";
import { toneOf, type Stat } from "@/components/ui/StatRow";
import RangeTabs from "@/components/RangeTabs";
import ResumeBanner from "@/components/ResumeBanner";
import RaceTrack from "@/components/RaceTrack";
import Setup from "@/components/Setup";
import StatusPill from "@/components/StatusPill";
import Spotlight from "@/components/Spotlight";
import TeamList from "@/components/TeamList";
import Link from "next/link";
import Card from "@/components/ui/Card";
import { OfficePause } from "@/components/OfficeAdmin";
import { isAdmin } from "@/lib/admin";
import { advise, betsPerDay, light } from "@/lib/advice";
import { bookLabel, getOffice, getRealBook, viewedBook, requireViewer } from "@/lib/book";
import {
  getAnalysis, getBets, getBonusPot, getHistory, getNews, getKillSwitch, getLive, getMoneyMoves, getPolicy, getRecentFills, getRoster,
  getSettlements, getSettlementsSince, isLive, isOffice, withRoster,
} from "@/lib/db";
import { currentUser, officeOf } from "@/lib/session";
import { dollars, pct } from "@/lib/format";
import { perDollar, teamNotes } from "@/lib/records";
import { headline, only, parseRange, poolKeys, profitSeries, RANGES, settledSeries } from "@/lib/portfolio";

export const dynamic = "force-dynamic";

const RANGE_WORDS = { day: "Today", week: "This Week", month: "This Month", quarter: "Last 3 Months", season: "All Time" };

/** The day (in the office's time zone) a moment falls on, as YYYY-MM-DD. */
const dayOf = (t: number, tz: string) => new Date(t).toLocaleDateString("en-CA", { timeZone: tz });

/**
 * An office (11-16): the owner's own on opening the app, a friend's only one. Top to bottom: what it's worth and the
 * chart, the bets riding now, the latest bets, and the team in one row. The rest of the old page (award, records,
 * needs-attention, news) is on /team.
 */
export default async function Home({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  await requireViewer();
  const params = await searchParams;
  const range = parseRange(params.range, "week");
  // Bets before the range arrive rolled up (getSettlementsSince); a minute early so the roll-up sits before the chart's start
  const days = RANGES[range].days;
  const sinceIso = days == null ? null : new Date(Date.now() - days * 86_400_000 - 60_000).toISOString();
  const book = await viewedBook();
  let data;
  try {
    const realBook = await getRealBook();
    const policy = await getPolicy(book);
    const [live, fills, roster, history, season, admin, settled, bets, kill, marks, office, user] = await Promise.all([
      getLive(book), getRecentFills(book, policy.season, 100), getRoster(book), getHistory(book, policy.season, range),
      range === "season" ? null : getHistory(book, policy.season, "season"), isAdmin(),
      sinceIso ? getSettlementsSince(book, policy.season, sinceIso) : getSettlements(book, policy.season),
      getBets(book, policy.season),
      // A friend's office has its own pause; the owner's real book's pause shows on both of the owner's views
      isOffice(book) ? getKillSwitch(book) : realBook ? getKillSwitch("real") : null, getMoneyMoves(book, policy.season),
      getOffice(book), currentUser(),
    ]);
    const [analysis, news, pot] = await Promise.all([getAnalysis(book), getNews(book, 40), getBonusPot(book)]);
    data = { realBook, live, fills, roster, policy, history, season: season ?? history, admin: admin && !isOffice(book),
             settled, bets, kill, marks, office, user, analysis, news, pot };
  } catch (e) {
    if (isOffice(book)) return <OfficeSoon />;
    return <Setup error={String(e)} />;
  }
  const { realBook, live, fills, roster, policy, history, season, admin, settled, bets, kill, marks, office, user, analysis, news, pot } = data;
  if (!live) return isOffice(book) ? <OfficeSoon /> : <Setup error="The bot hasn't published a status yet. Is it running?" />;

  const label = bookLabel(book, realBook, office);
  const employees = withRoster(live.employees, roster);
  const tz = live.pool?.settings?.timezone || "America/Vancouver";
  const members = new Set(poolKeys(live));
  const team = employees.filter((e) => members.has(e.key) && e.status !== "fired");
  const { worth, putIn, books, held } = headline(live, isLive(book), season.since);
  const now = Math.max(Date.parse(live.updated_at), Date.now() - 60_000);
  const mine = settled.filter((s) => members.has(s.strategy));
  // Finished bets, ending on the headline's own number: open bets count at cost until they're decided
  const points = settledSeries(only(history, members), mine, Math.max(history.since, season.since), now, worth);

  // The three numbers: finished bets today and in the last 7 days, and the return since the start
  const pool = bets.filter((b) => members.has(b.strategy));
  const today = dayOf(Date.now(), tz);
  const weekAgo = Date.now() - 7 * 86_400_000;
  const sum = (xs: typeof pool) => xs.reduce((s, b) => s + b.pnl, 0);
  const todays = pool.filter((b) => dayOf(b.t, tz) === today);
  const weeks = pool.filter((b) => b.t >= weekAgo);
  const won = (xs: typeof pool) => xs.filter((b) => b.pnl > 0).length;
  const record = (xs: typeof pool) => xs.length ? `${won(xs)} of ${xs.length} won (${Math.round((won(xs) / xs.length) * 100)}%)` : "nothing finished yet";
  const allTime = (worth - putIn) / (putIn || 1);
  const stats: Stat[] = [
    { label: "Today", value: dollars(sum(todays), true), tone: toneOf(sum(todays)), note: record(todays) },
    { label: "Last 7 Days", value: dollars(sum(weeks), true), tone: toneOf(sum(weeks)), note: record(weeks) },
    { label: "All Time", value: pct(allTime, true, 1), tone: toneOf(allTime), note: record(pool) },
  ];
  const profits: Record<string, number> = {};
  for (const b of pool) profits[b.strategy] = (profits[b.strategy] ?? 0) + b.pnl;
  const dayAgo = Date.now() - 86_400_000;
  const recent = pool.filter((b) => b.t >= dayAgo);
  const lastDay = { n: recent.length, won: won(recent), pnl: sum(recent) };
  // The team as it always looked: award, then everyone with their status light and profit line
  const trends = profitSeries(season);
  const away = (r: { light: { key: string } }) => (r.light.key === "benched" || r.light.key === "fired" ? 1 : 0);
  const rows = employees
    .filter((e) => members.has(e.key) || e.control)
    .map((e) => ({ e, light: light(e, analysis.evidence[e.key]), trend: trends[e.key] ?? [] }))
    .sort((a, b) => away(a) - away(b) || (profits[b.e.key] ?? 0) - (profits[a.e.key] ?? 0));
  const attention = admin
    ? team.filter((e) => advise(e, analysis.evidence[e.key], analysis.realism[e.key], policy,
        betsPerDay(analysis.evidence[e.key]?.bets ?? 0, season.since)).tone === "act").length
    : 0;
  const rates = Object.fromEntries(rows.map((r) => [r.e.key, perDollar(bets.filter((b) => b.strategy === r.e.key))]));
  const notes = teamNotes(rows.map((r) => ({ key: r.e.key, benched: r.light.key === "benched" || r.light.key === "fired",
    benchedUntil: r.e.suspended_until })), bets, tz);
  // The chart's range: where it starts, what changed over it, and each member's running profit for the what-if
  const chartStart = points[0]?.t ?? season.since;
  const rangeChange = Math.round(pool.filter((b) => b.t >= chartStart).reduce((s, b) => s + b.pnl, 0) * 100) / 100 || 0;
  const whatIf: WhatIfMember[] = team.filter((e) => !e.control && pool.some((b) => b.strategy === e.key)).map((e) => ({
    key: e.key, name: e.name, emoji: e.emoji,
    inRange: Math.round(pool.filter((b) => b.strategy === e.key && b.t >= chartStart).reduce((s, b) => s + b.pnl, 0) * 100) / 100,
  })).sort((a, b) => a.inRange - b.inRange);
  // When each open bet filled (its first fill), so the race knows where each lane started
  const started: Record<string, number> = {};
  for (const f of fills) if (f.yes_value == null) {
    const k = `${f.strategy}|${f.ticker}`, t = Date.parse(f.ts);
    started[k] = Math.min(started[k] ?? t, t);
  }
  const seasonStarted = news.findIndex((n) => n.kind === "season");
  const award = (seasonStarted < 0 ? news : news.slice(0, seasonStarted)).find((n) => n.kind === "award") ?? null;
  const name = isOffice(book) ? (officeOf(user) === book ? "Your office" : `${office?.name ?? "Friend"}'s office`)
    : book === "pretend" ? "Training" : "My Office";

  return (
    <div className="stack">
      <AutoRefresh seconds={60} />
      {/* A paused real book shows on both views (not a long, deliberate pause), with Resume right here */}
      {kill?.halted && !kill.long && !isOffice(book) && <ResumeBanner kill={kill} admin={admin} />}

      <OfficeHero
        label={name}
        badge={book === "pretend" ? <span className="badge" title={label.title}>Pretend money</span> : null}
        worth={worth} putIn={putIn} stats={stats}
        tabs={<RangeTabs value={range} path="/" />}
        chart={<HeroChart points={points} marks={marks} checked={books?.at ?? live.updated_at} members={whatIf}
                          bets={pool.map((b) => [b.t, b.strategy, Math.round(b.pnl * 100) / 100] as WhatIfBet)}
                          putIn={putIn} betPct={policy.pool.bet_pct} period={RANGE_WORDS[range]} />}
        facts={<HeroFacts period={RANGE_WORDS[range]} change={rangeChange} inRange={pool.filter((b) => b.t >= chartStart)}
                          all={pool} employees={employees} tz={tz} since={season.since} />}
        under={isOffice(book) ? <OfficePause halted={!!kill?.halted} mine={officeOf(user) === book} /> : null}
      />

      <RaceTrack positions={live.positions.filter((p) => members.has(p.strategy))} employees={employees} held={held}
                 started={started} now={Date.now()} />

      <LatestBets fills={fills.filter((f) => members.has(f.strategy) && f.yes_value != null)} employees={employees} day={lastDay} />

      <Card title="Your Team" aside={(
        <Link href="/team">
          {attention > 0 ? <strong>{attention} {attention === 1 ? "needs" : "need"} you · </strong> : null}Records &amp; news →
        </Link>
      )}>
        <Spotlight award={award} employees={employees} policy={policy} pot={pot} startsAt={isLive(book) ? 500 : 0} pool={live.pool?.equity ?? 0} />
        <TeamList rows={rows} profits={profits} rates={rates} notes={notes} star={award?.strategy ?? undefined} starTitle={award?.detail.title} />
      </Card>

      <div className="row-btns" style={{ justifyContent: "center" }}>
        <StatusPill updatedAt={live.updated_at} />
      </div>
    </div>
  );
}

/** A friend's office before its first run: the server opens it within a couple of minutes of joining. */
function OfficeSoon() {
  return (
    <div className="card narrow stack">
      <AutoRefresh seconds={30} />
      <h2>Your Office Is Opening</h2>
      <p>It takes a couple of minutes after you connect Kalshi. This page refreshes itself.</p>
      <p className="sub">
        Haven&apos;t connected your Kalshi key yet? Use the link from your invite again. Put money in on Kalshi whenever
        you like: the office notices within about 10 minutes.
      </p>
    </div>
  );
}
