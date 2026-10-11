import { Fragment } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import AdminPanel from "@/components/AdminPanel";
import AutoRefresh from "@/components/AutoRefresh";
import { LevelBadge, StatusBadge, Trophies } from "@/components/Badges";
import NewsFeed from "@/components/NewsFeed";
import CalibrationChart from "@/components/CalibrationChart";
import EquityChart from "@/components/EquityChart";
import Setup from "@/components/Setup";
import TradeFeed from "@/components/TradeFeed";
import { isAdmin } from "@/lib/admin";
import { getAccuracy, getEquity, getLive, getNews, getPolicy, getRecentFills, getRoster, getTuningRuns, toSeries, withRoster } from "@/lib/db";
import { cents, money, pct, tone } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function EmployeePage({ params }: { params: Promise<{ key: string }> }) {
  const { key } = await params;
  let data;
  try {
    const [live, equity, fills, accuracy, roster, news, tuning, policy, admin] = await Promise.all([
      getLive(), getEquity(14, key), getRecentFills(50, key), getAccuracy(), getRoster(), getNews(20, key),
      getTuningRuns(key), getPolicy(), isAdmin(),
    ]);
    data = { live, equity, fills, accuracy, roster, news, tuning, policy, admin };
  } catch (e) {
    return <Setup error={String(e)} />;
  }
  const base = data.live?.employees.find((x) => x.key === key);
  if (!base || !data.live) notFound();
  const e = withRoster([base], data.roster)[0];
  const lastTune = data.tuning[0];
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
          <h1>{e.name} <Trophies n={e.awards} /></h1>
          <div className="row-btns" style={{ marginTop: 4 }}>
            <span className="muted">{e.title} · <code>{e.key}</code></span>
            <LevelBadge level={e.level} title={e.level_title} />
            <StatusBadge e={e} />
          </div>
          <div style={{ marginTop: 4 }}>{e.blurb}</div>
          {e.note && <div className="notice" style={{ marginTop: 8 }}>📝 {e.note}</div>}
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

      <div className="grid two">
        <section className="card">
          <h2>Settings & tuning</h2>
          <p className="sub">
            {e.backtestable === false
              ? "Can't be replayed from price history; the performance reviews judge this employee."
              : e.autotune
                ? `Autotune is on: the background job retests these every ${data.policy.autotune.every_hours}h and switches only when a tested improvement is found.`
                : "Autotune is off: these settings only change when the manager changes them."}
          </p>
          <dl className="kv">
            {Object.entries(e.params ?? {}).map(([k, v]) => (
              <Fragment key={k}><dt>{k}{e.overrides && k in e.overrides ? " ✎" : ""}</dt><dd>{String(v)}</dd></Fragment>
            ))}
          </dl>
          {lastTune && (
            <>
              <div className="section-title">Last retune · {new Date(lastTune.created_at).toLocaleDateString()}</div>
              <p style={{ margin: 0 }}>
                {lastTune.summary.applied ? "🔧 Switched settings" : "🔍 Kept settings"}: {lastTune.summary.why}. Tried{" "}
                {lastTune.summary.tried} combinations.
              </p>
              <div className="table-wrap" style={{ marginTop: 8 }}>
                <table>
                  <thead><tr><th>Settings</th><th className="num">Train P&amp;L</th><th className="num">Test P&amp;L</th><th className="num">Test bets</th></tr></thead>
                  <tbody>
                    <tr>
                      <td><strong>current</strong></td>
                      <td className={`num ${tone(lastTune.summary.current.train.pnl)}`}>{money(lastTune.summary.current.train.pnl)}</td>
                      <td className={`num ${tone(lastTune.summary.current.test.pnl)}`}>{money(lastTune.summary.current.test.pnl)}</td>
                      <td className="num">{lastTune.summary.current.test.bets}</td>
                    </tr>
                    {lastTune.summary.top.slice(0, 5).map((r, i) => (
                      <tr key={i}>
                        <td className="muted" style={{ fontSize: 12 }}>{Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(", ")}{r.holds_up ? " ✓" : ""}</td>
                        <td className={`num ${tone(r.train.pnl)}`}>{money(r.train.pnl)}</td>
                        <td className={`num ${tone(r.test.pnl)}`}>{money(r.test.pnl)}</td>
                        <td className="num">{r.test.bets}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
        <section className="card">
          <h2>HR file</h2>
          <dl className="kv" style={{ marginBottom: 12 }}>
            <dt>Level</dt><dd>{e.level_title} ({e.multiplier ?? 1}x bet size)</dd>
            <dt>Awards</dt><dd>{e.awards ?? 0}</dd>
            <dt>Strikes</dt><dd>{e.strikes ?? 0}</dd>
            <dt>Bankroll given</dt><dd>{money(e.starting_cash, false)}</dd>
          </dl>
          <NewsFeed items={data.news} employees={[e]} />
        </section>
      </div>

      {data.admin && <AdminPanel e={e} roster={data.roster[key] ?? null} reserve={data.policy.reserve} />}

      <section className="card">
        <h2>Trades</h2>
        <TradeFeed fills={data.fills} employees={data.live.employees} />
      </section>
    </div>
  );
}
