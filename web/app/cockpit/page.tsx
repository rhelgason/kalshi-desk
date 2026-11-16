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
import { ago, dollars, pct } from "@/lib/format";
import { headline, poolKeys } from "@/lib/portfolio";
import { perDollar, type Bet } from "@/lib/records";
import { currentUser, officeOf } from "@/lib/session";
import { viewOffice } from "../account";

export const dynamic = "force-dynamic";

type Office = {
  book: Book; name: string; mine: boolean; since: number; worth: number; putIn: number;
  bets: Bet[]; open: number; openCost: number; status: string;
};

/** Every office that's trading: the owner's real book, then each friend's. */
async function loadOffices(viewer: Book | null): Promise<Office[]> {
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
      const positions = live.positions.filter((p) => members.has(p.strategy));
      return {
        book, name, mine: book === viewer, since, worth: top.worth, putIn: top.putIn,
        bets: bets.filter((b) => members.has(b.strategy)), open: positions.length,
        openCost: positions.reduce((s, p) => s + p.cost, 0),
        status: kill.halted ? "Paused" : `Running · ${ago(live.updated_at)}`,
      } satisfies Office;
    } catch {
      return null;
    }
  }));
  return out.filter((o): o is Office => o !== null);
}

/** Return since the start, step by step: each finished bet's profit over what was put in. */
function returnLine(o: Office): ReturnLine {
  let sum = 0;
  const pts = [{ t: o.since, v: 0 }];
  for (const b of [...o.bets].sort((a, b) => a.t - b.t)) {
    sum += b.pnl;
    pts.push({ t: b.t, v: sum / (o.putIn || 1) });
  }
  return { key: o.book, label: o.name, points: pts, mine: o.mine };
}

const won = (bs: Bet[]) => bs.filter((b) => b.pnl > 0).length;

/**
 * The cockpit (11-16). The manager: every office side by side, in dollars and %, one tap from each. A friend: the
 * light version, in % only, the same offices and the same staff, which is the honest answer to "can I trust this?"
 * (one office can be lucky; all of them together over weeks can't).
 */
export default async function CockpitPage() {
  await requireViewer();
  const [admin, user] = await Promise.all([isAdmin(), currentUser()]);
  const offices = await loadOffices(admin ? "real" : officeOf(user));
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
  const weekAgo = Date.now() - 7 * 86_400_000;
  const lines = offices.map(returnLine);
  const all = offices.flatMap((o) => o.bets);
  const allPer = perDollar(all);
  const days = Math.max(1, Math.round((Date.now() - Math.min(...offices.map((o) => o.since))) / 86_400_000));

  return (
    <div className="stack">
      <AutoRefresh seconds={120} />
      {admin && <NeedsAttention todo={todo} />}
      <Card title="Cockpit" aside={`${offices.length} offices · same staff, same rules`}>
        <ReturnsChart lines={lines} />
      </Card>

      <section className="card">
        <h2>Every Office</h2>
        <div className="table-wrap">
          <table className="cockpit-table">
            <thead>
              <tr>
                <th>Office</th>
                {admin && <th className="num">Value</th>}
                {admin && <th className="num">Profit</th>}
                <th className="num">Return</th>
                <th className="num">Last 7 days</th>
                <th className="num">Bets</th>
                <th className="num">Won</th>
                <th className="num">Per $1 bet</th>
                {admin && <th className="num">Riding</th>}
                {admin && <th>Status</th>}
                {admin && <th />}
              </tr>
            </thead>
            <tbody>
              {offices.map((o) => {
                const profit = o.worth - o.putIn;
                const week = o.bets.filter((b) => b.t >= weekAgo).reduce((s, b) => s + b.pnl, 0);
                const per = perDollar(o.bets);
                return (
                  <tr key={o.book} className={o.mine ? "is-mine" : undefined}>
                    <td><strong>{o.name}</strong>{o.mine && <span className="muted"> · you</span>}</td>
                    {admin && <td className="num">{dollars(o.worth)}</td>}
                    {admin && <td className={`num ${profit >= 0 ? "up" : "down"}`}>{dollars(profit, true)}</td>}
                    <td className={`num ${profit >= 0 ? "up" : "down"}`}>{pct(profit / (o.putIn || 1), true, 1)}</td>
                    <td className={`num ${week >= 0 ? "up" : "down"}`}>{pct(week / (o.putIn || 1), true, 1)}</td>
                    <td className="num">{o.bets.length}</td>
                    <td className="num">{o.bets.length ? pct(won(o.bets) / o.bets.length, false, 1) : "–"}</td>
                    <td className={`num ${(per ?? 0) >= 0 ? "up" : "down"}`}>{per == null ? "–" : `${(per * 100).toFixed(2)}¢`}</td>
                    {admin && <td className="num">{o.open ? `${o.open} · ${dollars(o.openCost)}` : "–"}</td>}
                    {admin && <td className="muted small">{o.status}</td>}
                    {admin && (
                      <td>
                        <form action={viewOffice.bind(null, o.book === "real" ? null : o.book)}>
                          <button className="btn small">Open</button>
                        </form>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2>All Offices Together</h2>
        <StatRow stats={[
          { label: "Bets Finished", value: all.length.toLocaleString(), note: `over ${days} days` },
          { label: "Won", value: all.length ? pct(won(all) / all.length, false, 1) : "–", note: `${all.length - won(all)} lost` },
          { label: "Per $1 Bet", value: allPer == null ? "–" : `${(allPer * 100).toFixed(2)}¢`, tone: toneOf(allPer), note: "profit, after fees" },
        ]} />
        <p className="muted small">
          Most bets are strong favorites: each win earns a few cents per dollar, and a loss costs nearly the whole bet. So
          one office can look great or poor over a few days by luck alone. What matters is profit per $1 across all
          offices over weeks: if it stays above zero, the method is working.
        </p>
      </section>
    </div>
  );
}
