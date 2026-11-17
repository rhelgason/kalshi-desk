import Card from "@/components/ui/Card";
import ManagerControls from "@/components/ManagerControls";
import RealMoney from "@/components/RealMoney";
import Setup from "@/components/Setup";
import SystemAlert from "@/components/SystemAlert";
import { isAdmin } from "@/lib/admin";
import { viewedBook, requireViewer } from "@/lib/book";
import { getKillSwitch, getLive, getPolicy, isOffice } from "@/lib/db";
import { LEVELS, awardName, poolShare } from "@/lib/hr";

export const dynamic = "force-dynamic";

const pct = (v: number) => `${+(v * 100).toFixed(2)}%`;

/**
 * The office's rules (11-17): how employees move up and what they bet, the limits that keep the pool safe, real
 * money's stop button, and the manager's two other buttons. Rules themselves are changed by asking Claude.
 */
export default async function RulesPage() {
  await requireViewer();
  let data;
  try {
    const book = await viewedBook();
    // The rules are the viewed book's; the real-money panel is the real book's (a friend's: their office's)
    const money = isOffice(book) ? book : "real";
    const [policy, admin, live, killSwitch] = await Promise.all([
      getPolicy(book), isAdmin(), getLive(money).catch(() => null), getKillSwitch(money).catch(() => ({ halted: false })),
    ]);
    data = { book, policy, admin: admin && !isOffice(book), office: isOffice(book), trading: live?.trading ?? { mode: "paper" as const }, killSwitch };
  } catch (e) {
    return <Setup error={String(e)} />;
  }
  const { book, policy, admin, office, trading, killSwitch } = data;
  const p = policy.pool;
  return (
    <div className="stack">
      {admin && <SystemAlert />}
      <Card title="Employee Handbook">
        <p className="sub">
          Every {policy.review_days} days a review names the {awardName(policy.review_days)} (the most profit per $1 bet),
          promotes strong performers to bigger bets and benches the ones who keep losing.
          {office ? " Your office follows the manager's rules." : ""}
        </p>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Level</th><th className="num">Each bet</th><th>How to get there</th></tr></thead>
            <tbody>
              {LEVELS.map((l, i) => (
                <tr key={l.title}>
                  <td>{l.title}</td>
                  <td className="num">{poolShare(l.multiplier, p.bet_pct)} of the pool</td>
                  <td className="muted">{i === 0 ? "New hires and demoted employees" : `A promotion from ${LEVELS[i - 1].title}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="section-title">Safety limits</div>
        <dl className="kv">
          <dt>At once</dt><dd>At most {pct(p.window_cap)} of the pool in any 15 minutes</dd>
          <dt>Bad day</dt><dd>Betting stops for the day after losing {pct(p.daily_stop)}</dd>
          {p.brake_drawdown > 0 && <><dt>Slump</dt><dd>Bets shrink to {pct(p.brake_factor)} of size after a {pct(p.brake_drawdown)} drop</dd></>}
        </dl>
      </Card>

      <RealMoney trading={trading} killSwitch={killSwitch} admin={admin} />

      {admin && <ManagerControls training={book === "pretend"} />}
    </div>
  );
}
