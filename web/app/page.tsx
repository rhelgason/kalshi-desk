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
import NewsFeed from "@/components/NewsFeed";
import Card from "@/components/ui/Card";
import { isAdmin } from "@/lib/admin";
import { light } from "@/lib/advice";
import { bookLabel, getOffice, getRealBook, viewedBook, requireViewer } from "@/lib/book";
import {
  getAnalysis, getBetsSince, getBonusPot, getDays, getMoneyIn, getNews, getKillSwitch, getLive, getMoneyMoves, getPolicy, getRecentFills,
  getRoster, isLive, isOffice, withRoster,
} from "@/lib/db";
import { betWindow, dayOf, daysBefore, forReplay, rateOf, totalsOf, trendsOf } from "@/lib/season";
import { currentUser, officeOf } from "@/lib/session";
import { dollars, pct } from "@/lib/format";
import { teamNotes, type Bet } from "@/lib/records";
import type { DayRow, Totals } from "@/lib/season";
import type { Employee, NewsItem, Policy } from "@/lib/types";
import type { BonusPot } from "@/lib/db";
import { Suspense } from "react";
import { headline, only, parseRange, poolKeys, RANGES, RANGE_WORDS, settledSeries } from "@/lib/portfolio";

export const dynamic = "force-dynamic";



/**
 * An office (11-16): the owner's own on opening the app, a friend's only one. Top to bottom: what it's worth and the
 * chart, the bets riding now, the team, the latest bets, streaks and records, and office news (folded). The
 * manager's to-do list is on the cockpit.
 */
export default async function Home({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  await requireViewer();
  const params = await searchParams;
  const range = parseRange(params.range, "week");
  const days = RANGES[range].days;
  const book = await viewedBook();
  let data;
  try {
    const realBook = await getRealBook();
    const policy = await getPolicy(book);
    const tz = policy.pool.timezone || "America/Vancouver";
    // Single bets only for the latest weeks (a month for the month's chart): the season before that comes as one
    // row per employee per day, added up by the bot after each run (lib/season.ts; 11-16: Training's whole season
    // is ~40,000 bets and took ~15 s). Whole days, so the past days' bets stay cached; only today's are fetched anew.
    const { firstDay, since, today } = betWindow(tz, range === "month" ? 31 : 14);
    const [live, fills, roster, money, admin, rows, bets, kill, marks, office, user] = await Promise.all([
      getLive(book), getRecentFills(book, policy.season, 100), getRoster(book), getMoneyIn(book, policy.season), isAdmin(),
      getDays(book, policy.season, tz),
      getBetsSince(book, policy.season, since, today),
      // A friend's office has its own pause; the owner's real book's pause shows on both of the owner's views
      isOffice(book) ? getKillSwitch(book) : realBook ? getKillSwitch("real") : null, getMoneyMoves(book, policy.season),
      getOffice(book), currentUser(),
    ]);
    data = { realBook, live, fills, roster, policy, money, admin: admin && !isOffice(book), rows, bets, firstDay, kill,
             marks, office, user, tz };
  } catch (e) {
    if (isOffice(book)) return <OfficeSoon />;
    return <Setup error={String(e)} />;
  }
  const { realBook, live, fills, roster, policy, money, admin, rows: dayRows, bets, firstDay, kill, marks, office, user, tz } = data;
  // Asked for once the top card's numbers are in, so they don't queue ahead of them (two database connections)
  const later = Promise.all([getAnalysis(book), getNews(book, 40), getBonusPot(book)]);
  later.catch(() => {});
  if (!live) return isOffice(book) ? <OfficeSoon /> : <Setup error="The bot hasn't published a status yet. Is it running?" />;

  const label = bookLabel(book, realBook, office);
  const employees = withRoster(live.employees, roster);
  const members = new Set(poolKeys(live));
  const team = employees.filter((e) => members.has(e.key) && e.status !== "fired");
  const { worth, putIn, books, held } = headline(live, isLive(book), money.since);
  const now = Math.max(Date.parse(live.updated_at), Date.now() - 60_000);
  const totals = totalsOf(dayRows);
  // The latest weeks' single bets (the team's captions and the three numbers), and the whole season as finished
  // bets: a row per day before those weeks, then each bet (the chart, its facts and the what-if)
  const pool = bets.filter((b) => members.has(b.strategy));
  const finished = [...daysBefore(dayRows, firstDay, (k) => members.has(k)), ...pool];
  // Finished bets, ending on the headline's own number: open bets count at cost until they're decided
  const rangeStart = days == null ? money.since : Math.max(money.since, now - days * 86_400_000);
  const points = settledSeries(only(money, members), finished.map((b) => ({ ...b, coin: "" })), rangeStart, now, worth);

  // The three numbers: finished bets today and in the last 7 days, and the return since the start
  const today = dayOf(Date.now(), tz);
  const weekAgo = Date.now() - 7 * 86_400_000;
  const sum = (xs: typeof pool) => xs.reduce((s, b) => s + b.pnl, 0);
  const todays = pool.filter((b) => dayOf(b.t, tz) === today);
  const weeks = pool.filter((b) => b.t >= weekAgo);
  const won = (xs: typeof pool) => xs.filter((b) => b.pnl > 0).length;
  const record = (xs: typeof pool) => xs.length ? `${won(xs)} of ${xs.length} won (${Math.round((won(xs) / xs.length) * 100)}%)` : "nothing finished yet";
  const allTime = (worth - putIn) / (putIn || 1);
  const season_ = Object.entries(totals).filter(([k]) => members.has(k)).map(([, t]) => t);
  const seasonN = season_.reduce((s, t) => s + t.n, 0), seasonWon = season_.reduce((s, t) => s + t.won, 0);
  const stats: Stat[] = [
    { label: "Today", value: dollars(sum(todays), true), tone: toneOf(sum(todays)), note: record(todays) },
    { label: "Last 7 Days", value: dollars(sum(weeks), true), tone: toneOf(sum(weeks)), note: record(weeks) },
    { label: "All Time", value: pct(allTime, true, 1), tone: toneOf(allTime),
      note: seasonN ? `${seasonWon} of ${seasonN} won (${Math.round((seasonWon / seasonN) * 100)}%)` : "nothing finished yet" },
  ];
  const dayAgo = Date.now() - 86_400_000;
  const recent = pool.filter((b) => b.t >= dayAgo);
  const lastDay = { n: recent.length, won: won(recent), pnl: sum(recent) };
  // The chart's range: where it starts, what changed over it, and each member's running profit for the what-if
  const chartStart = points[0]?.t ?? money.since;
  const inRange = finished.filter((b) => b.t >= chartStart);
  const rangeChange = Math.round(inRange.reduce((s, b) => s + b.pnl, 0) * 100) / 100 || 0;
  const whatIf: WhatIfMember[] = team.filter((e) => !e.control && finished.some((b) => b.strategy === e.key)).map((e) => ({
    key: e.key, name: e.name, emoji: e.emoji,
    inRange: Math.round(inRange.filter((b) => b.strategy === e.key).reduce((s, b) => s + b.pnl, 0) * 100) / 100,
  })).sort((a, b) => a.inRange - b.inRange);
  // When each open bet filled (its first fill), so the race knows where each lane started
  const started: Record<string, number> = {};
  for (const f of fills) if (f.yes_value == null) {
    const k = `${f.strategy}|${f.ticker}`, t = Date.parse(f.ts);
    started[k] = Math.min(started[k] ?? t, t);
  }
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
                          bets={forReplay(finished, points, tz) as WhatIfBet[]}
                          putIn={putIn} betPct={policy.pool.bet_pct} period={RANGE_WORDS[range]} />}
        facts={<HeroFacts period={RANGE_WORDS[range]} change={rangeChange} inRange={inRange}
                          all={finished} employees={employees} tz={tz} since={money.since} days={days} />}
      />

      <RaceTrack positions={live.positions.filter((p) => members.has(p.strategy))} employees={employees} held={held}
                 started={started} now={Date.now()} />

      {/* The team and the news stream in just after the top card (their numbers are asked for once it's ready) */}
      <Suspense fallback={<Card title="Your Team"><div className="skel skel-line" /><div className="skel skel-line" /><div className="skel skel-line short" /></Card>}>
        <Team later={later} employees={employees} members={members} totals={totals} dayRows={dayRows} bets={bets} tz={tz}
              policy={policy} startsAt={isLive(book) ? 500 : 0} pool={live.pool?.equity ?? 0} />
      </Suspense>

      <LatestBets fills={fills.filter((f) => members.has(f.strategy) && f.yes_value != null)} employees={employees} day={lastDay} />

      {/* The day strip is already in the top card */}

      <details className="card fold">
        <summary><h2>Office News</h2></summary>
        <Suspense fallback={<div className="skel skel-line" />}><News later={later} employees={employees} /></Suspense>
      </details>

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

type Later = Promise<[Awaited<ReturnType<typeof getAnalysis>>, NewsItem[], BonusPot]>;

/** The team as it always looked: the award, then everyone with their status light, profit line and caption. */
async function Team({ later, employees, members, totals, dayRows, bets, tz, policy, startsAt, pool }: {
  later: Later; employees: Employee[]; members: Set<string>; totals: Record<string, Totals>; dayRows: DayRow[]; bets: Bet[];
  tz: string; policy: Policy; startsAt: number; pool: number;
}) {
  const [analysis, news, pot] = await later.catch(() => [null, [] as NewsItem[], null] as const);
  const profits: Record<string, number> = Object.fromEntries(Object.entries(totals).map(([k, t]) => [k, t.pnl]));
  const trends = trendsOf(dayRows);
  const away = (r: { light: { key: string } }) => (r.light.key === "benched" || r.light.key === "fired" ? 1 : 0);
  const rows = employees
    .filter((e) => members.has(e.key) || e.control)
    .map((e) => ({ e, light: light(e, analysis?.evidence[e.key]), trend: trends[e.key] ?? [] }))
    .sort((a, b) => away(a) - away(b) || (profits[b.e.key] ?? 0) - (profits[a.e.key] ?? 0));
  const rates = Object.fromEntries(rows.map((r) => [r.e.key, rateOf(totals[r.e.key])]));
  const notes = teamNotes(rows.map((r) => ({ key: r.e.key, benched: r.light.key === "benched" || r.light.key === "fired",
    benchedUntil: r.e.suspended_until })), bets, tz, Date.now(), totals);
  const seasonStarted = news.findIndex((n) => n.kind === "season");
  const award = (seasonStarted < 0 ? news : news.slice(0, seasonStarted)).find((n) => n.kind === "award") ?? null;
  return (
    <Card title="Your Team">
      {pot && <Spotlight award={award} employees={employees} policy={policy} pot={pot} startsAt={startsAt} pool={pool} />}
      <TeamList rows={rows} profits={profits} rates={rates} notes={notes} star={award?.strategy ?? undefined} starTitle={award?.detail.title} />
    </Card>
  );
}

/** Office news, folded at the bottom. */
async function News({ later, employees }: { later: Later; employees: Employee[] }) {
  const news = await later.then((x) => x[1]).catch(() => [] as NewsItem[]);
  return <NewsFeed items={news.filter((n) => n.kind !== "review").slice(0, 25)} employees={employees} />;
}
