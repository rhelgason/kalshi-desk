import AutoRefresh from "@/components/AutoRefresh";
import Board from "@/components/Board";
import Setup from "@/components/Setup";
import StatusPill from "@/components/StatusPill";
import TradeFeed from "@/components/TradeFeed";
import { getEquity, getLive, getRecentFills, getSettledCount, toSeries } from "@/lib/db";
import { money, pct, tone, usd } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function Home() {
  let data;
  try {
    const [live, equity, fills, settled] = await Promise.all([getLive(), getEquity(7), getRecentFills(25), getSettledCount()]);
    data = { live, equity, fills, settled };
  } catch (e) {
    return <Setup error={String(e)} />;
  }
  const { live, equity, fills, settled } = data;
  if (!live) return <Setup error="The bot hasn't published a status yet. Is it running?" />;

  const employees = live.employees;
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
          <div className="value">{beatingDan ?? "–"} <span className="muted" style={{ fontSize: 15 }}>/ {employees.length - 1}</span></div>
          <div className="note">🐒 Dan is at {money(dan?.pnl)}</div>
        </div>
        <div className="card tile">
          <div className="label">Bets settled</div>
          <div className="value">{settled.toLocaleString()}</div>
          <div className="note">{money(totalFees, false)} paid in fees</div>
        </div>
      </div>

      <Board employees={employees} series={toSeries(equity, employees)} />

      <section className="card">
        <h2>Latest trades</h2>
        <p className="sub">Paper fills against the live Kalshi orderbook, newest first.</p>
        <TradeFeed fills={fills} employees={employees} />
      </section>
    </div>
  );
}
