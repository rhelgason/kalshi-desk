import AutoRefresh from "@/components/AutoRefresh";
import Office from "@/components/Office";
import Setup from "@/components/Setup";
import { getActivity, getHistory, getLive, getPolicy, getRoster, withRoster } from "@/lib/db";
import { profitSeries } from "@/lib/portfolio";

export const dynamic = "force-dynamic";

export default async function OfficePage() {
  let data;
  try {
    const policy = await getPolicy();
    const [live, roster, activity, history] = await Promise.all([
      getLive(), getRoster(), getActivity(policy.season), getHistory(policy.season, "season"),
    ]);
    data = { policy, live, roster, activity, history };
  } catch (e) {
    return <Setup error={String(e)} />;
  }
  if (!data.live) return <Setup error="The bot hasn't published a status yet. Is it running?" />;
  const employees = withRoster(data.live.employees, data.roster);
  const total = employees.reduce((s, e) => s + (e.pnl ?? 0), 0);
  return (
    <>
      <AutoRefresh seconds={30} />
      <Office employees={employees} activity={data.activity} trends={profitSeries(data.history)} total={total}
        season={data.policy.season} btc={data.live.underlyings?.BTC?.spot ?? null} />
    </>
  );
}
