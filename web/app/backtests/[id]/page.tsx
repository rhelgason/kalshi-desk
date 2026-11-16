import Link from "next/link";
import { notFound } from "next/navigation";
import CalibrationChart from "@/components/CalibrationChart";
import EquityChart from "@/components/EquityChart";
import Setup from "@/components/Setup";
import { getBacktest } from "@/lib/db";
import { cents, money, pct, tone } from "@/lib/format";
import type { Series } from "@/lib/types";
import { requireViewer } from "@/lib/book";

export const dynamic = "force-dynamic";

export default async function BacktestPage({ params }: { params: Promise<{ id: string }> }) {
  await requireViewer();
  const { id } = await params;
  let s;
  try {
    s = await getBacktest(id);
  } catch (e) {
    return <Setup error={String(e)} />;
  }
  if (!s) notFound();
  const meta = Object.fromEntries((s.employees ?? []).map((e) => [e.key, e]));
  const label = (k: string) => `${meta[k]?.emoji ?? ""} ${meta[k]?.name ?? k}`;
  const rows = [...s.scoreboard].sort((a, b) => b.pnl - a.pnl);
  const series: Series[] = Object.entries(s.equity ?? {})
    .filter(([, pts]) => pts.length)
    .map(([k, pts]) => {
      const start = s!.scoreboard.find((r) => r.strategy === k)?.starting_cash ?? 1000;
      return { key: k, label: meta[k]?.name ?? k, emoji: meta[k]?.emoji ?? "", points: pts.map(([t, v]) => ({ t: Date.parse(t), v: v - start })) };
    });
  const traded = s.accuracy.filter((a) => a.n > 0);

  return (
    <div className="stack">
      <Link href="/backtests" className="muted">← all backtests</Link>
      <section className="card">
        <h2>Backtest {s.id}</h2>
        <p className="sub">
          {s.days} days · {s.settled_markets.toLocaleString()} settled markets in {s.series.join(", ")} · fill delay {s.fill_delay} min
          · assumes {s.depth} contracts available at each quote · {s.stats.fills.toLocaleString()} fills
        </p>
        {series.length ? <EquityChart series={series} /> : <div className="empty">This run was saved before equity curves were recorded.</div>}
      </section>

      <section className="card">
        <h2>Results</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Employee</th><th className="num">P&amp;L</th><th className="num">ROI</th><th className="num">Bets</th><th className="num">Win rate</th><th className="num">Fees</th><th className="num">Skill</th><th className="num">Real edge</th></tr></thead>
            <tbody>
              {rows.map((r) => {
                const a = s!.accuracy.find((x) => x.strategy === r.strategy);
                return (
                  <tr key={r.strategy}>
                    <td>{label(r.strategy)}</td>
                    <td className={`num ${tone(r.pnl)}`}>{money(r.pnl)}</td>
                    <td className={`num ${tone(r.roi)}`}>{pct(r.roi, true)}</td>
                    <td className="num">{r.fills}</td>
                    <td className="num">{r.win_rate == null ? "–" : pct(r.win_rate, false, 0)}</td>
                    <td className="num muted">{money(r.fees, false)}</td>
                    <td className={`num ${tone(a?.skill)}`}>{pct(a?.skill, true)}</td>
                    <td className={`num ${tone(a?.realized_edge)}`}>{a ? cents(a.realized_edge) : "–"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}>
        {traded.map((a) => (
          <section key={a.strategy} className="card">
            <h2>{label(a.strategy)}</h2>
            <p className="sub">{a.n} settled bets · won {pct(a.hit_rate, false, 0)}</p>
            <CalibrationChart model={a.model_bins} market={a.market_bins} />
          </section>
        ))}
      </div>
    </div>
  );
}
