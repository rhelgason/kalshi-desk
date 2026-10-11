import Link from "next/link";
import { notFound } from "next/navigation";
import AutoRefresh from "@/components/AutoRefresh";
import CalibrationChart from "@/components/CalibrationChart";
import EquityChart from "@/components/EquityChart";
import Setup from "@/components/Setup";
import TradeFeed from "@/components/TradeFeed";
import { getAccuracy, getEquity, getLive, getRecentFills, toSeries } from "@/lib/db";
import { cents, money, pct, tone } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function EmployeePage({ params }: { params: Promise<{ key: string }> }) {
  const { key } = await params;
  let data;
  try {
    const [live, equity, fills, accuracy] = await Promise.all([getLive(), getEquity(14, key), getRecentFills(50, key), getAccuracy()]);
    data = { live, equity, fills, accuracy };
  } catch (e) {
    return <Setup error={String(e)} />;
  }
  const e = data.live?.employees.find((x) => x.key === key);
  if (!e || !data.live) notFound();
  const acc = data.accuracy.find((a) => a.strategy === key);
  const positions = data.live.positions.filter((p) => p.strategy === key);

  const tiles: [string, string, string?][] = [
    ["Paper P&L", money(e.pnl), tone(e.pnl)],
    ["ROI", pct(e.roi, true), tone(e.roi)],
    ["Win rate", e.win_rate == null ? "–" : pct(e.win_rate, false, 0)],
    ["Bets", String(e.fills ?? 0)],
    ["Fees paid", money(e.fees, false)],
    ["Max drop", pct(e.max_drawdown)],
  ];

  return (
    <div className="stack">
      <AutoRefresh seconds={60} />
      <Link href="/" className="muted">← back to the floor</Link>
      <div className="hero">
        <span className="emoji" aria-hidden>{e.emoji}</span>
        <div>
          <h1>{e.name}</h1>
          <div className="muted">{e.title} · <code>{e.key}</code></div>
          <div style={{ marginTop: 4 }}>{e.blurb}</div>
        </div>
      </div>

      <div className="grid tiles">
        {tiles.map(([label, value, cls]) => (
          <div key={label} className="card tile">
            <div className="label">{label}</div>
            <div className={`value ${cls ?? ""}`}>{value}</div>
          </div>
        ))}
      </div>

      <section className="card">
        <h2>P&amp;L, last 14 days</h2>
        <EquityChart series={toSeries(data.equity, [e])} height={240} />
      </section>

      <div className="grid two">
        <section className="card">
          <h2>Accuracy</h2>
          <p className="sub">
            Are this employee&apos;s odds right? Dots below the diagonal mean overconfident. Orange dots show how
            accurate the market&apos;s own prices were on the same bets.
          </p>
          {acc ? (
            <>
              <CalibrationChart model={acc.model_bins} market={acc.market_bins} />
              <div className="table-wrap" style={{ marginTop: 12 }}>
                <table>
                  <tbody>
                    <tr><td>Settled bets</td><td className="num">{acc.n}</td></tr>
                    <tr><td>Expected edge / contract</td><td className="num">{cents(acc.expected_edge)}</td></tr>
                    <tr><td>Realized edge / contract</td><td className={`num ${tone(acc.realized_edge)}`}>{cents(acc.realized_edge)}</td></tr>
                    <tr><td>Skill vs. market (above 0 = better than the price)</td><td className={`num ${tone(acc.skill)}`}>{pct(acc.skill, true)}</td></tr>
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="empty">No settled bets yet.</div>
          )}
        </section>

        <section className="card">
          <h2>Open bets ({positions.length})</h2>
          {positions.length ? (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Market</th><th className="num">Holding</th><th className="num">Paid</th><th className="num">Now</th></tr></thead>
                <tbody>
                  {positions.map((p) => {
                    const yes = p.yes >= p.no;
                    const now = p.mark == null ? null : (yes ? p.yes * p.mark : p.no * (1 - p.mark));
                    return (
                      <tr key={p.ticker}>
                        <td><div>{p.title || p.ticker}</div><div className="muted" style={{ fontSize: 12 }}>{p.subtitle}</div></td>
                        <td className="num">{(yes ? p.yes : p.no).toFixed(0)} {yes ? "YES" : "NO"}</td>
                        <td className="num">{money(p.cost, false)}</td>
                        <td className={`num ${now == null ? "" : tone(now - p.cost)}`}>{now == null ? "–" : money(now, false)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty">Nothing open right now.</div>
          )}
        </section>
      </div>

      <section className="card">
        <h2>Trades</h2>
        <TradeFeed fills={data.fills} employees={data.live.employees} />
      </section>
    </div>
  );
}
