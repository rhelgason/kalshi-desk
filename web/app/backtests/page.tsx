import { redirect } from "next/navigation";
import { isAdmin } from "@/lib/admin";
import Link from "next/link";
import Setup from "@/components/Setup";
import { listBacktests } from "@/lib/db";
import { money } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function Backtests() {
  // The owner's research: friends don't see how the desk is tested (11-16)
  if (!(await isAdmin())) redirect("/");
  let runs;
  try {
    runs = await listBacktests();
  } catch (e) {
    return <Setup error={String(e)} />;
  }
  return (
    <div className="stack">
      <section className="card">
        <h2>Backtests</h2>
        <p className="sub">
          Replays of settled Kalshi markets, minute by minute. Run one with <code>python -m desk backtest --days 30</code>.
        </p>
        {runs.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Run</th><th>Markets</th><th className="num">Days</th><th className="num">Fill delay</th><th className="num">Settled</th><th>Best employee</th></tr></thead>
              <tbody>
                {runs.map(({ id, summary: s }) => {
                  const best = [...s.scoreboard].sort((a, b) => b.pnl - a.pnl)[0];
                  const emp = s.employees?.find((e) => e.key === best?.strategy);
                  return (
                    <tr key={id}>
                      <td><Link href={`/backtests/${id}`}>{id}</Link></td>
                      <td className="muted">{s.series.join(", ")}</td>
                      <td className="num">{s.days}</td>
                      <td className="num">{s.fill_delay} min</td>
                      <td className="num">{s.settled_markets.toLocaleString()}</td>
                      <td>{emp?.emoji} {emp?.name ?? best?.strategy} <span className="up">{money(best?.pnl)}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty">No backtests uploaded yet.</div>
        )}
      </section>
    </div>
  );
}
