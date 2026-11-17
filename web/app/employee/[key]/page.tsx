import Link from "next/link";
import { notFound } from "next/navigation";
import AdminPanel from "@/components/AdminPanel";
import AutoRefresh from "@/components/AutoRefresh";
import Setup from "@/components/Setup";
import PlayerCard from "@/components/PlayerCard";
import { StatusBadge, Trophies } from "@/components/Badges";
import { DailyBars, WinDonut } from "@/components/MiniCharts";
import LatestBets from "@/components/LatestBets";
import PortfolioChart from "@/components/PortfolioChart";
import RaceTrack from "@/components/RaceTrack";
import SkillGauge from "@/components/SkillGauge";
import Card from "@/components/ui/Card";
import { teamNotes } from "@/lib/records";
import { isAdmin } from "@/lib/admin";
import { HOW_THEY_BET } from "@/lib/voice";
import { getAnalysis, getBets, getLive, getPolicy, getRecentFills, getRoster, getSeasonStart, getSettlementStats, isOffice, withRoster } from "@/lib/db";
import { viewedBook, requireViewer } from "@/lib/book";
import { poolKeys } from "@/lib/portfolio";

export const dynamic = "force-dynamic";

/**
 * One employee (11-16): who they are and how they're doing at the top, their profit line, won / skill or luck / by
 * day, their bets riding now and their latest bets, then (for the manager) the controls. Every number is from
 * finished bets, so the page only moves when a bet is decided; the riding card is the exception.
 */
export default async function EmployeePage({ params }: { params: Promise<{ key: string }> }) {
  await requireViewer();
  const { key } = await params;
  let data;
  try {
    const book = await viewedBook();
    const policy = await getPolicy(book);
    const [live, seasonStart, fills, analysis, roster, admin, stats, bets] = await Promise.all([
      getLive(book), getSeasonStart(book, policy.season), getRecentFills(book, policy.season, 100, key), getAnalysis(book),
      getRoster(book), isAdmin(), getSettlementStats(book, policy.season, key), getBets(book, policy.season),
    ]);
    // On Training, can the manager move this employee to real money? (not when they're already there)
    let movable = false;
    if (admin && book === "pretend") {
      const [real, realPolicy] = await Promise.all([getLive("real"), getPolicy("real")]);
      movable = !!real && !real.employees.some((x) => x.key === key) && !realPolicy.hired?.includes(key);
    }
    data = { live, seasonStart, fills, evidence: analysis.evidence, roster, policy, admin: admin && !isOffice(book), stats, bets, movable };
  } catch (e) {
    return <Setup error={String(e)} />;
  }
  const base = data.live?.employees.find((x) => x.key === key);
  if (!base || !data.live) notFound();
  const e = withRoster([base], data.roster)[0];
  const positions = data.live.positions.filter((p) => p.strategy === key);
  const ev = data.evidence[key];
  const everyone = withRoster(data.live.employees, data.roster);

  const tz = data.live.pool?.settings?.timezone || "America/Vancouver";
  const team = poolKeys(data.live);
  const mine = data.bets.filter((b) => b.strategy === key);
  // Their caption, worded against the whole team so it matches the home page's list
  const caption = teamNotes(team.map((k) => {
    const x = everyone.find((y) => y.key === k);
    return { key: k, benched: x?.status === "suspended" || x?.status === "fired", benchedUntil: x?.suspended_until };
  }), data.bets.filter((b) => team.includes(b.strategy)), tz)[key];
  // Their running profit from finished bets, drawn like the home chart (break-even dashed)
  let run = 0;
  // From their first bet (a mid-season hire's line doesn't sit flat before they joined)
  const profitPoints = [{ t: mine.length ? mine[0].t - 60_000 : data.seasonStart ?? Date.now(), worth: 0, putIn: 0 },
    ...mine.map((b) => ({ t: b.t, worth: (run += b.pnl), putIn: 0 })), { t: Date.now(), worth: run, putIn: 0 }];
  // When each open bet filled, for the race
  const started: Record<string, number> = {};
  for (const f of data.fills) if (f.yes_value == null) {
    const k2 = `${f.strategy}|${f.ticker}`, t = Date.parse(f.ts);
    started[k2] = Math.min(started[k2] ?? t, t);
  }
  const dayAgo = Date.now() - 86_400_000;
  const recent = mine.filter((b) => b.t >= dayAgo);

  return (
    <div className="stack">
      <AutoRefresh seconds={60} />
      <Link href="/" className="muted">← My Office</Link>
      <PlayerCard e={e} bets={mine} tz={tz} caption={caption} blurb={HOW_THEY_BET[e.key] ?? e.blurb}
        team={team.map((k) => ({ key: k, bets: data.bets.filter((b) => b.strategy === k) }))}
        badges={<><StatusBadge e={e} /><Trophies n={e.awards} /></>} />
      {e.note && <div className="notice">{e.note}</div>}

      <Card title="Profit Over Time" aside="this season, from finished bets">
        <PortfolioChart points={profitPoints} profitOnly="profit" checked={data.live.updated_at} />
      </Card>

      <div className="grid three">
        <Card title="Bets Won">
          <WinDonut wins={data.stats.wins} losses={data.stats.losses} open={positions.length} />
        </Card>
        <Card title="Skill or Luck?">
          <SkillGauge e={ev} />
        </Card>
        <Card title="Profit by Day">
          <DailyBars days={data.stats.days} />
        </Card>
      </div>

      {positions.length > 0
        ? <RaceTrack positions={positions} employees={everyone} started={started} now={Date.now()} />
        : <Card title="Riding Now"><div className="empty">Nothing open right now.</div></Card>}

      <LatestBets fills={data.fills.filter((f) => f.yes_value != null)} employees={everyone}
                  day={{ n: recent.length, won: recent.filter((b) => b.pnl > 0).length, pnl: recent.reduce((t, b) => t + b.pnl, 0) }} />

      {data.admin && (
        <div id="manager">
          <AdminPanel e={e} roster={data.roster[key] ?? null} reserve={data.policy.reserve} betPct={data.policy.pool.bet_pct}
                      movable={data.movable} />
        </div>
      )}
    </div>
  );
}
