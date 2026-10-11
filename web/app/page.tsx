import AutoRefresh from "@/components/AutoRefresh";
import Board from "@/components/Board";
import NewsFeed from "@/components/NewsFeed";
import Spotlight from "@/components/Spotlight";
import Setup from "@/components/Setup";
import StatusPill from "@/components/StatusPill";
import TradeFeed from "@/components/TradeFeed";
import { getAnalysis, getEquity, getLive, getNews, getPolicy, getRecentFills, getRoster, getSettledCount, toSeries, withRoster } from "@/lib/db";
import { money, pct, tone, usd } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function Home() {
  let data;
  try {
    const policy = await getPolicy();
    const [live, equity, fills, settled, roster, news, analysis] = await Promise.all([
      getLive(), getEquity(7, policy.season), getRecentFills(policy.season, 25), getSettledCount(policy.season),
      getRoster(), getNews(40), getAnalysis(),
    ]);
    data = { live, equity, fills, settled, roster, news, policy, analysis };
  } catch (e) {
    return <Setup error={String(e)} />;
  }
  const { live, equity, fills, settled, roster, news, policy, analysis } = data;
  if (!live) return <Setup error="The bot hasn't published a status yet. Is it running?" />;

  const employees = withRoster(live.employees, roster);
  const award = news.find((n) => n.kind === "award") ?? null;
  const totalPnl = employees.reduce((s, e) => s + (e.pnl ?? 0), 0);
  const totalFees = employees.reduce((s, e) => s + (e.fees ?? 0), 0);
  const best = [...employees].sort((a, b) => (b.pnl ?? 0) - (a.pnl ?? 0))[0];
  const dan = employees.find((e) => e.key === "dart_monkey");
  const beatingDan = dan ? employees.filter((e) => e.key !== dan.key && (e.pnl ?? 0) > (dan.pnl ?? 0)).length : null;

  return (
    <div className="stack">
      <AutoRefresh seconds={60} />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <StatusPill updatedAt={live.updated_at} />
        {Object.entries(live.underlyings).map(([sym, q]) => (
          <span key={sym} className="pill"><strong style={{ color: "var(--text-primary)" }}>{sym}</strong> {usd(q.spot)}</span>
        ))}
      </div>

      <Spotlight award={award} employees={employees} policy={policy} />

      <div className="grid tiles">
        <div className="card tile">
          <div className="label">Whole desk, paper P&amp;L</div>
          <div className={`value ${tone(totalPnl)}`}>{money(totalPnl)}</div>
          <div className="note">across {employees.length} employees</div>
        </div>
        <div className="card tile">
          <div className="label">Top earner</div>
          <div className="value">{best?.emoji} {money(best?.pnl)}</div>
          <div className="note">{best?.name} · {pct(best?.roi, true)}</div>
        </div>
        <div className="card tile">
          <div className="label">Beating the dart monkey</div>
          <div className="value">{beatingDan ?? "–"} <span className="muted" style={{ fontSize: 15 }}>/ {employees.filter((e) => e.status !== "fired").length - 1}</span></div>
          <div className="note">🐒 Dan is at {money(dan?.pnl)}</div>
        </div>
        <div className="card tile">
          <div className="label">Bets settled</div>
          <div className="value">{settled.toLocaleString()}</div>
          <div className="note">{money(totalFees, false)} paid in fees</div>
        </div>
      </div>

      <Board employees={employees} series={toSeries(equity, employees)} evidence={analysis.evidence} />

      <div className="grid two">
        <section className="card">
          <h2>Latest trades</h2>
          <p className="sub">Paper fills against the live Kalshi orderbook, newest first.</p>
          <TradeFeed fills={fills} employees={employees} />
        </section>
        <section className="card">
          <h2>Office news</h2>
          <p className="sub">Hires, promotions, awards, suspensions, and retunes.</p>
          <NewsFeed items={news.filter((n) => n.kind !== "review").slice(0, 25)} employees={employees} />
        </section>
      </div>
    </div>
  );
}
