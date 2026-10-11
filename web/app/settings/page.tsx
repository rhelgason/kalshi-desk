import PolicyForm from "@/components/PolicyForm";
import Setup from "@/components/Setup";
import { isAdmin } from "@/lib/admin";
import { getCoverage, getJobs, getPolicy } from "@/lib/db";
import { ago } from "@/lib/format";
import { LEVELS, awardName } from "@/lib/hr";

export const dynamic = "force-dynamic";

export default async function Handbook() {
  let data;
  try {
    const [policy, jobs, coverage, admin] = await Promise.all([getPolicy(), getJobs(), getCoverage(), isAdmin()]);
    data = { policy, jobs, coverage, admin };
  } catch (e) {
    return <Setup error={String(e)} />;
  }
  const { policy, jobs, coverage, admin } = data;
  const at = policy.autotune;
  return (
    <div className="stack">
      <section className="card">
        <h2>📘 Employee handbook</h2>
        <p className="sub">
          How the desk runs itself. Every {policy.review_days} days a performance review crowns the{" "}
          {awardName(policy.review_days)}, promotes strong performers to bigger bets, and benches the ones who keep
          losing. {admin ? "You can change any rule below." : "Only the manager can change these rules."}
        </p>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Level</th><th className="num">Bet size</th><th>How to get there</th></tr></thead>
            <tbody>
              {LEVELS.map((l, i) => (
                <tr key={l.title}>
                  <td>{l.title}</td>
                  <td className="num">{l.multiplier}x</td>
                  <td className="muted">{i === 0 ? "New hires and demoted employees" : `One promotion above ${LEVELS[i - 1].title}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2>Desk rules</h2>
        <PolicyForm policy={policy} admin={admin} />
      </section>

      <section className="card">
        <h2>Background jobs</h2>
        <p className="sub">
          Every 3 hours GitHub Actions syncs new market history, backfills Kalshi&apos;s archive, and retunes employees
          when due (every {at.every_hours}h{at.enabled ? "" : ", currently paused"}).
        </p>
        <dl className="kv">
          <dt>Backtests assume</dt>
          <dd>
            {policy.realism.depth} contracts available at the best price
            {policy.realism.samples
              ? ` (measured from ${policy.realism.samples} live trades)`
              : " (default until enough live trades are measured)"}
          </dd>
          <dt>Last job</dt><dd>{jobs ? `${ago(jobs.finished_at)} (${jobs.seconds}s)` : "hasn't run yet"}</dd>
          <dt>Last retune</dt><dd>{at.last_run ? ago(at.last_run) : "never"}</dd>
          <dt>Retune requested</dt><dd>{at.requested_at ? `yes, ${ago(at.requested_at)}` : "no"}</dd>
        </dl>
        <div className="section-title">History stored for backtests</div>
        {coverage.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Series</th><th className="num">Settled markets</th><th>From</th><th>To</th></tr></thead>
              <tbody>
                {coverage.map((c) => (
                  <tr key={c.series}>
                    <td>{c.series}</td>
                    <td className="num">{c.markets.toLocaleString()}</td>
                    <td>{new Date(c.oldest * 1000).toLocaleDateString()}</td>
                    <td>{new Date(c.newest * 1000).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div className="empty">Nothing stored yet; the first background job fills this in.</div>}
      </section>
    </div>
  );
}
