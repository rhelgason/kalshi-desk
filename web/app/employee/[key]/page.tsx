import { Fragment } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import AdminPanel from "@/components/AdminPanel";
import Avatar from "@/components/Avatar";
import AutoRefresh from "@/components/AutoRefresh";
import { LevelBadge, StatusBadge, Trophies } from "@/components/Badges";
import NewsFeed from "@/components/NewsFeed";
import { RealityCheck, SkillCheck } from "@/components/Evidence";
import CalibrationChart from "@/components/CalibrationChart";
import AdviceCard from "@/components/AdviceCard";
import CompareChart from "@/components/CompareChart";
import RangeTabs from "@/components/RangeTabs";
import Setup from "@/components/Setup";
import ManagerBar from "@/components/ManagerBar";
import { DailyBars, MoneySplit, WinDonut } from "@/components/MiniCharts";
import TradeFeed from "@/components/TradeFeed";
import { isAdmin } from "@/lib/admin";
import { advise, betsPerDay, light } from "@/lib/advice";
import { HOW_THEY_BET, quip } from "@/lib/voice";
import { getAnalysis, getHistory, getLive, getNews, getPolicy, getRecentFills, getRoster, getSeasonStart, getSettlementStats, getTuningRuns, withRoster } from "@/lib/db";
import { cents, dollars, money, pct, tone } from "@/lib/format";
import { parseRange, profitSeries } from "@/lib/portfolio";

export const dynamic = "force-dynamic";

export default async function EmployeePage({ params, searchParams }: {
  params: Promise<{ key: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const { key } = await params;
  const range = parseRange((await searchParams).range);
  let data;
  try {
    const policy = await getPolicy();
    const [live, history, seasonStart, fills, analysis, roster, news, tuning, admin, stats] = await Promise.all([
      getLive(), getHistory(policy.season, range), getSeasonStart(policy.season), getRecentFills(policy.season, 8, key),
      getAnalysis(), getRoster(), getNews(20, key), getTuningRuns(key), isAdmin(),
      getSettlementStats(policy.season, key),
    ]);
    data = { live, history, seasonStart, fills, accuracy: analysis.accuracy, evidence: analysis.evidence, realism: analysis.realism,
             roster, news, tuning, policy, admin, stats };
  } catch (e) {
    return <Setup error={String(e)} />;
  }
  const base = data.live?.employees.find((x) => x.key === key);
  if (!base || !data.live) notFound();
  const e = withRoster([base], data.roster)[0];
  const lastTune = data.tuning[0];
  const acc = data.accuracy.find((a) => a.strategy === key);
  const positions = data.live.positions.filter((p) => p.strategy === key);

  const ev = data.evidence[key];
  const status = light(e, ev);
  const advice = advise(e, ev, data.realism[key], data.policy, betsPerDay(ev?.bets ?? 0, data.seasonStart));
  const everyone = withRoster(data.live.employees, data.roster);
  const profits = profitSeries(data.history);
  const liveT = Date.parse(data.live.updated_at);
  const series = everyone
    .filter((x) => profits[x.key]?.length)
    // End each line at the live profit so the chart's "now" matches the numbers above
    .map((x) => ({
      key: x.key, label: x.name, emoji: x.emoji,
      points: [...profits[x.key], { t: Math.max(liveT, profits[x.key].at(-1)!.t), v: x.pnl ?? 0 }],
    }));
  const pnl = e.pnl ?? 0;
  const settled = (e.wins ?? 0) + (e.losses ?? 0);

  return (
    <div className="stack">
      <AutoRefresh seconds={60} />
      <Link href="/" className="muted">← Home</Link>
      <div className="hero">
        <Avatar k={e.key} emoji={e.emoji} size={80} />
        <div>
          <h1>{e.name} <Trophies n={e.awards} /></h1>
          <div className="row-btns" style={{ marginTop: 4 }}>
            <span className={`light ${status.key}`}>{status.icon} {status.label}</span>
            <LevelBadge level={e.level} title={e.level_title} />
            <StatusBadge e={e} />
          </div>
          <div className="hero-quote">“{quip(e)}”</div>
          <p className="how-they-bet">{HOW_THEY_BET[e.key] ?? e.blurb}</p>
          {e.note && <div className="notice" style={{ marginTop: 8 }}>📝 {e.note}</div>}
        </div>
      </div>

      <div className="money-row">
        <div className="card tile">
          <div className="label">Money given</div>
          <div className="value">{dollars(e.starting_cash)}</div>
        </div>
        <div className="card tile">
          <div className="label">Worth now</div>
          <div className="value">{dollars(e.equity)}</div>
        </div>
        <div className="card tile">
          <div className="label">{pnl >= 0 ? "Gained" : "Lost"}</div>
          <div className={`value ${tone(pnl)}`}>{dollars(pnl, true)}</div>
          <div className={`note ${tone(pnl)}`}>{pct(e.roi, true)}</div>
        </div>
      </div>

      <AdviceCard k={key} name={e.name} advice={advice} admin={data.admin} />
      {data.admin && <ManagerBar e={e} />}

      <section className="card">
        <h2>Profit over time</h2>
        <RangeTabs value={range} path={`/employee/${key}`} />
        <CompareChart series={series} focus={key} given={Object.fromEntries(everyone.map((x) => [x.key, x.starting_cash ?? 1000]))} />
      </section>

      <div className="grid three">
        <section className="card">
          <h2>Bets won</h2>
          <WinDonut wins={data.stats.wins} losses={data.stats.losses} open={positions.length} />
        </section>
        <section className="card">
          <h2>Where the money went</h2>
          <MoneySplit won={data.stats.won} lost={data.stats.lost} fees={e.fees ?? 0} />
        </section>
        <section className="card">
          <h2>Profit by day</h2>
          <DailyBars days={data.stats.days} />
        </section>
      </div>

      <section className="card">
        <h2>Skill or luck?</h2>
        <SkillCheck e={ev} />
      </section>

      <div className="grid two">
        <section className="card">
          <h2>Bets still open ({positions.length})</h2>
          {positions.length ? (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Market</th><th className="num">Bet on</th><th className="num">Paid</th><th className="num">Now</th></tr></thead>
                <tbody>
                  {positions.slice(0, 5).map((p) => {
                    const yes = p.yes >= p.no;
                    const now = p.mark == null ? null : (yes ? p.yes * p.mark : p.no * (1 - p.mark));
                    return (
                      <tr key={p.ticker}>
                        <td className="market"><div>{p.title || p.ticker}</div><div className="muted" style={{ fontSize: 12 }}>{p.subtitle}</div></td>
                        <td className="num">{(yes ? p.yes : p.no).toFixed(0)} {yes ? "YES" : "NO"}</td>
                        <td className="num">{money(p.cost, false)}</td>
                        <td className={`num ${now == null ? "" : tone(now - p.cost)}`}>{now == null ? "–" : money(now, false)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
          {positions.length > 5 && <p className="muted small" style={{ margin: "8px 0 0" }}>…and {positions.length - 5} more.</p>}
          {positions.length ? null : (
            <div className="empty">Nothing open right now.</div>
          )}
        </section>
        <section className="card">
        <h2>Recent bets</h2>
        <TradeFeed fills={data.fills} employees={data.live.employees} />
      </section>
      </div>

      <details className="card fold">
        <summary><h2>Behind the scenes</h2><span className="muted small">fill check, accuracy, settings, HR file</span></summary>
        <section className="card" style={{ marginTop: 12 }}>
          <h2>Would this work with real money?</h2>
          <p className="sub">Compares each pretend trade with what was really for sale at that moment.</p>
          <RealityCheck r={data.realism[key]} />
        </section>
        <div className="grid two" style={{ marginTop: 12 }}>
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
        <div style={{ marginTop: 16 }}>
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
        </div>
      </details>

      {data.admin && (
        <div id="manager">
          <AdminPanel e={e} roster={data.roster[key] ?? null} reserve={data.policy.reserve} />
        </div>
      )}
    </div>
  );
}
