import AutoRefresh from "@/components/AutoRefresh";
import Card from "@/components/ui/Card";
import StatRow, { toneOf } from "@/components/ui/StatRow";
import OfficeCards, { type OfficeCard, type OfficePoint } from "@/components/OfficeCards";
import { isAdmin } from "@/lib/admin";
import { requireViewer } from "@/lib/book";
import { getAnalysis, getBets, getForecast, getKillSwitch, getLive, getMoneyMoves, getPolicy, getRoster, getSeasonStart, home, withRoster, type Book } from "@/lib/db";
import NeedsAttention from "@/components/NeedsAttention";
import InviteCard from "@/components/InviteCard";
import ForecastCard from "@/components/ForecastCard";
import SystemAlert from "@/components/SystemAlert";
import { advise, betsPerDay, type Advice } from "@/lib/advice";
import type { Employee, MoneyMove } from "@/lib/types";
import { dollars, pct } from "@/lib/format";
import { headline, parseRange, poolKeys, RANGES, RANGE_WORDS } from "@/lib/portfolio";
import RangeTabs from "@/components/RangeTabs";
import { calendarDays, perDollar, skillOdds, type Bet } from "@/lib/records";
import OfficeTable, { type OfficeRow } from "@/components/OfficeTable";
import SkillGauge from "@/components/SkillGauge";
import DayStrip from "@/components/DayStrip";
import { viewOffice } from "../account";
import { currentUser, officeOf } from "@/lib/session";
import { previewFresh } from "@/lib/fresh";
import { sixMonths } from "@/lib/forecast";

export const dynamic = "force-dynamic";

type Office = {
  book: Book; name: string; since: number; worth: number; putIn: number; bets: Bet[]; paused: boolean;
  updated: string; moves: MoneyMove[];
};

// One colour per office, the same on the chart and in the table
const COLORS = ["var(--series-1)", "var(--series-2)", "#8b5cf6", "#14b8a6", "#ec4899"];

/** Every office that's trading: the owner's real book, then each friend's. */
async function loadOffices(): Promise<Office[]> {
  const friends = (await home()`
    SELECT u.office AS slug, u.name FROM public.users u JOIN public.offices o ON o.slug = u.office
    WHERE u.role = 'friend' AND o.status = 'active' ORDER BY u.created_at`.catch(() => [])) as unknown as { slug: string; name: string }[];
  const owner = (await home()`SELECT name FROM public.users WHERE role = 'owner' LIMIT 1`.catch(() => []))[0]?.name ?? "Manager";
  const books: { book: Book; name: string }[] = [{ book: "real", name: owner },
    ...friends.map((f) => ({ book: `office_${f.slug}` as Book, name: f.name }))];
  const out = await Promise.all(books.map(async ({ book, name }) => {
    try {
      const policy = await getPolicy(book);
      const [live, start, bets, kill, moves] = await Promise.all([getLive(book), getSeasonStart(book, policy.season), getBets(book, policy.season),
        getKillSwitch(book), getMoneyMoves(book, policy.season).catch(() => [] as MoneyMove[])]);
      if (!live) return null;
      const since = start ?? Date.now();
      const top = headline(live, true, since);
      const members = new Set(live.pool?.members ?? []);
      return {
        book, name, since, worth: top.worth, putIn: top.putIn,
        bets: bets.filter((b) => members.has(b.strategy)).sort((a, b) => a.t - b.t),
        paused: !!kill.halted, updated: live.updated_at, moves,
      } satisfies Office;
    } catch {
      return null;
    }
  }));
  return out.filter((o): o is Office => o !== null);
}

const won = (bs: Bet[]) => bs.filter((b) => b.pnl > 0).length;

/**
 * An office's worth and money put in over the range, for its card's chart (11-22): put in steps up at each deposit,
 * worth is put in plus finished bets' profit, thinned to ~150 points, and the last point is today's worth (with open bets).
 */
function officePoints(o: Office, from: number, now: number): OfficePoint[] {
  const start = Math.max(from, o.since);
  const base = o.putIn - o.moves.reduce((s, m) => s + m.amount, 0);
  const putInAt = (t: number) => base + o.moves.filter((m) => m.t <= t).reduce((s, m) => s + m.amount, 0);
  let profit = 0, i = 0;
  const bets = o.bets;
  for (; i < bets.length && bets[i].t <= start; i++) profit += bets[i].pnl;
  const out: OfficePoint[] = [{ t: start, v: putInAt(start) + profit, p: putInAt(start) }];
  const bin = Math.max(60_000, (now - start) / 150);
  const events = [...bets.slice(i).map((b) => ({ t: b.t, pnl: b.pnl, move: false })),
    ...o.moves.filter((m) => m.t > start && m.t <= now).map((m) => ({ t: m.t, pnl: 0, move: true }))].sort((a, b) => a.t - b.t);
  for (const e of events) {
    if (e.move) out.push({ t: e.t - 1, v: putInAt(e.t - 1) + profit, p: putInAt(e.t - 1) }); // the step's foot
    profit += e.pnl;
    const p = { t: e.t, v: putInAt(e.t) + profit, p: putInAt(e.t) };
    const last = out[out.length - 1];
    if (!e.move && out.length > 1 && Math.floor((last.t - start) / bin) === Math.floor((e.t - start) / bin) && last.p === p.p) out[out.length - 1] = p;
    else out.push(p);
  }
  out.push({ t: Math.max(now, out[out.length - 1].t + 1), v: o.worth, p: o.putIn });
  return out;
}

/**
 * The cockpit (11-16; 11-22 the owner: one player card per office instead of one shared % chart, the table folded
 * under them). The manager sees dollars and can open each office; a friend sees % only. Then, side by side, the manager's to-do
 * list and "Is it working?": every office's bets together, which is the honest answer to "can I trust this?" (one
 * office can be lucky over a few days; all of them together over weeks can't).
 */
export default async function CockpitPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  await requireViewer();
  const range = parseRange((await searchParams).range, "week");
  const [manager, user] = await Promise.all([isAdmin(), currentUser()]);
  // The manager previewing the new-user tour sees a friend's cockpit: percentages, no manager cards
  const fresh = await previewFresh(manager);
  const admin = manager && fresh == null;
  const [offices, forecast] = await Promise.all([loadOffices(), getForecast("real").catch(() => null)]);
  // The manager's to-do list for their real-money office (moved here from the old Team page, 11-16)
  let todo: { e: Employee; advice: Advice }[] = [];
  if (admin) {
    try {
      const policy = await getPolicy("real");
      const [live, roster, analysis, start] = await Promise.all([getLive("real"), getRoster("real"), getAnalysis("real"),
        getSeasonStart("real", policy.season)]);
      const members = new Set(live ? poolKeys(live) : []);
      todo = withRoster(live?.employees ?? [], roster).filter((e) => members.has(e.key) && e.status !== "fired")
        .map((e) => ({ e, advice: advise(e, analysis.evidence[e.key], analysis.realism[e.key], policy,
          betsPerDay(analysis.evidence[e.key]?.bets ?? 0, start ?? Date.now())) }))
        .filter((r) => r.advice.tone === "act");
    } catch { /* the list is a nicety: the cockpit still shows without it */ }
  }
  const now = Date.now();
  const rangeDays = RANGES[range].days;
  const from = rangeDays == null ? 0 : now - rangeDays * 86_400_000;
  const cards: OfficeCard[] = offices.map((o, i) => ({
    key: o.book, name: o.name, color: COLORS[i % COLORS.length], paused: o.paused, since: o.since, worth: o.worth, putIn: o.putIn,
    period: o.bets.filter((b) => b.t >= Math.max(from, o.since)).reduce((s, b) => s + b.pnl, 0),
    points: officePoints(o, from, now), moves: o.moves,
    visit: admin ? viewOffice.bind(null, o.book === "real" ? null : o.book) : undefined,
  }));
  const rows: OfficeRow[] = offices.map((o, i) => ({
    key: o.book, name: o.name, color: COLORS[i % COLORS.length], paused: o.paused, since: o.since, putIn: o.putIn, worth: o.worth,
    week: o.bets.filter((b) => b.t >= Math.max(from, o.since)).reduce((s, b) => s + b.pnl, 0), bets: o.bets.length, won: won(o.bets),
    perDollar: perDollar(o.bets),
    visit: admin ? viewOffice.bind(null, o.book === "real" ? null : o.book) : undefined,
  }));
  const all = offices.flatMap((o) => o.bets);
  const allPer = perDollar(all);
  const odds = skillOdds(all);
  const profit = offices.reduce((s, o) => s + o.worth - o.putIn, 0), putIn = offices.reduce((s, o) => s + o.putIn, 0);
  const up = offices.filter((o) => o.worth > o.putIn).length;
  const start = Math.min(...offices.map((o) => o.since));
  const stripDays = Math.min(Math.min(30, Math.max(7, rangeDays ?? 30)), calendarDays(start, "America/Vancouver", now));

  // What it might do for the person looking (the new-user tour's selling point; the tour quotes it,
  // components/Tour.tsx): the prediction model's 6-month middle guess (desk/forecast.py, lib/forecast.ts) for their
  // office's money once it's open; before that, what Kalshi said when they connected (prefs.kalshi_balance), or $100.
  const mineBook = manager ? "real" : officeOf(user);
  const saved = Number(user?.prefs?.kalshi_balance ?? 0) || 0;
  const theirs = fresh != null ? fresh : offices.find((o) => o.book === mineBook)?.worth ?? saved;
  const base = theirs >= 1 ? theirs : 100;
  const own = fresh == null && mineBook ? (mineBook === "real" ? forecast : await getForecast(mineBook as Book).catch(() => null)) : null;
  // Before the model's first run: the pace of every office so far (profit per dollar per day, no compounding)
  const moneyDays = offices.reduce((s, o) => s + ((o.putIn + o.worth) / 2) * Math.max(0, (now - o.since) / 86_400_000), 0);
  const pace = moneyDays > 0 ? profit / moneyDays : 0;
  const later6 = sixMonths(base, own, forecast) ?? base * (1 + Math.max(0, pace) * 182);

  // What a newcomer asks: what did a dollar turn into, does it win most days, is it skill?
  const working = (
    <Card title="Is It Working?" className="is-working">
      <div className="working">
        <SkillGauge e={odds} />
        <div className="working-facts">
          <div className="working-lead">
            Every $1 put in is now <strong className={toneOf(profit) ?? ""}>{dollars(putIn ? (putIn + profit) / putIn : 1)}</strong>
          </div>
          <StatRow flat stats={[
            admin
              ? { label: "Profit", value: dollars(profit, true), tone: toneOf(profit), note: `on ${dollars(putIn)} put in` }
              : { label: "Return", value: pct(putIn ? profit / putIn : 0, true, 1), tone: toneOf(profit), note: "all offices together" },
            { label: "Bets Won", value: all.length ? pct(won(all) / all.length, false, 1) : "–", note: `of ${all.length.toLocaleString()} bets` },
            { label: "Offices Up", value: `${up} of ${offices.length}`, note: allPer == null ? "" : `${allPer >= 0 ? "+" : ""}${(allPer * 100).toFixed(1)}¢ per $1 bet` },
          ]} />
        </div>
      </div>
      {stripDays > 0 && <div className="working-days"><DayStrip bets={all} tz="America/Vancouver" n={stripDays} /></div>}
      {/* The 6-month estimate, for the new-user tour to quote (not shown until the prediction model is built) */}
      <span hidden className="working-estimate" data-base={Math.round(base)} data-later={Math.round(later6)} data-has={theirs >= 1 ? "1" : ""} />
    </Card>
  );

  return (
    <div className="stack">
      <AutoRefresh seconds={120} />
      {admin && <SystemAlert />}
      <Card title="Cockpit" className="cockpit-main">
        <div className="hero-chart-head"><RangeTabs value={range} path="/cockpit" /></div>
        <OfficeCards cards={cards} money={admin} period={RANGE_WORDS[range]} />
        {/* The full numbers, folded: the cards carry the headline (11-22) */}
        <details className="office-details">
          <summary>All the numbers</summary>
          <OfficeTable rows={rows} money={admin} now={now} period={RANGE_WORDS[range]} />
        </details>
      </Card>
      {admin && forecast?.fan?.length ? <ForecastCard f={forecast} /> : null}
      {admin ? <div className="grid two cockpit-under">{working}<NeedsAttention todo={todo} /></div> : working}
      {admin && <InviteCard />}
    </div>
  );
}
