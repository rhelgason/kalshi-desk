import AutoRefresh from "@/components/AutoRefresh";
import Card from "@/components/ui/Card";
import StatRow, { toneOf } from "@/components/ui/StatRow";
import ReturnsChart, { type ReturnLine } from "@/components/ReturnsChart";
import { isAdmin } from "@/lib/admin";
import { requireViewer } from "@/lib/book";
import { getAnalysis, getBets, getKillSwitch, getLive, getPolicy, getRoster, getSeasonStart, home, withRoster, type Book } from "@/lib/db";
import NeedsAttention from "@/components/NeedsAttention";
import { advise, betsPerDay, type Advice } from "@/lib/advice";
import type { Employee } from "@/lib/types";
import { dollars, pct } from "@/lib/format";
import { headline, parseRange, poolKeys, RANGES, RANGE_WORDS } from "@/lib/portfolio";
import RangeTabs from "@/components/RangeTabs";
import { perDollar, skillOdds, type Bet } from "@/lib/records";
import OfficeTable, { type OfficeRow } from "@/components/OfficeTable";
import SkillGauge from "@/components/SkillGauge";
import DayStrip from "@/components/DayStrip";
import { viewOffice } from "../account";

export const dynamic = "force-dynamic";

type Office = {
  book: Book; name: string; since: number; worth: number; putIn: number; bets: Bet[]; paused: boolean;
  updated: string;
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
      const [live, start, bets, kill] = await Promise.all([getLive(book), getSeasonStart(book, policy.season), getBets(book, policy.season),
        getKillSwitch(book)]);
      if (!live) return null;
      const since = start ?? Date.now();
      const top = headline(live, true, since);
      const members = new Set(live.pool?.members ?? []);
      return {
        book, name, since, worth: top.worth, putIn: top.putIn,
        bets: bets.filter((b) => members.has(b.strategy)).sort((a, b) => a.t - b.t),
        paused: !!kill.halted, updated: live.updated_at,
      } satisfies Office;
    } catch {
      return null;
    }
  }));
  return out.filter((o): o is Office => o !== null);
}

const won = (bs: Bet[]) => bs.filter((b) => b.pnl > 0).length;

/** An office's running profit after each finished bet, for the chart. */
function returnLine(o: Office, color: string): ReturnLine {
  let sum = 0;
  return { key: o.book, label: o.name, color, putIn: o.putIn, since: o.since, pnl: o.bets.map((b) => [b.t, (sum += b.pnl)]) };
}

/**
 * The cockpit (11-16). One card on top: every office's return on one chart, with the office table under it as its
 * legend (the manager sees dollars and can open each; a friend sees % only). Then, side by side, the manager's to-do
 * list and "Is it working?": every office's bets together, which is the honest answer to "can I trust this?" (one
 * office can be lucky over a few days; all of them together over weeks can't).
 */
export default async function CockpitPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  await requireViewer();
  const range = parseRange((await searchParams).range, "week");
  const admin = await isAdmin();
  const offices = await loadOffices();
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
  const lines = offices.map((o, i) => returnLine(o, COLORS[i % COLORS.length]));
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
  const stripDays = Math.min(Math.min(30, Math.max(7, rangeDays ?? 30)), Math.ceil((now - start) / 86_400_000));

  // What a newcomer asks: what did a dollar turn into, does it win most days, is it skill?
  const working = (
    <Card title="Is It Working?">
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
    </Card>
  );

  return (
    <div className="stack">
      <AutoRefresh seconds={120} />
      <Card title="Cockpit" className="cockpit-main">
        <div className="hero-chart-head"><RangeTabs value={range} path="/cockpit" /></div>
        <ReturnsChart lines={lines} from={from} now={now} checked={offices[0]?.updated} />
        <OfficeTable rows={rows} money={admin} now={now} period={RANGE_WORDS[range]} />
      </Card>
      {admin ? <div className="grid two cockpit-under">{working}<NeedsAttention todo={todo} /></div> : working}
    </div>
  );
}
