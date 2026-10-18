import AutoRefresh from "@/components/AutoRefresh";
import Office from "@/components/Office";
import Setup from "@/components/Setup";
import { getRealBook } from "@/lib/book";
import { getActivity, getBtcSeries, getHistory, getLive, getPolicy, getRoster, withRoster } from "@/lib/db";
import { only, poolKeys, portfolioSeries } from "@/lib/portfolio";

export const dynamic = "force-dynamic";

export default async function OfficePage() {
  let data;
  try {
    // The office always shows the Live book once there is one (training until then)
    const book = (await getRealBook()) ? "real" : "pretend";
    const policy = await getPolicy(book);
    const [live, roster, activity, history, btcSeries] = await Promise.all([
      getLive(book), getRoster(book), getActivity(book, policy.season), getHistory(book, policy.season, "season"),
      getBtcSeries(book),
    ]);
    data = { policy, live, roster, activity, history, btcSeries };
  } catch (e) {
    return <Setup error={String(e)} />;
  }
  if (!data.live) return <Setup error="The bot hasn't published a status yet. Is it running?" />;
  const employees = withRoster(data.live.employees, data.roster);
  const pool = new Set(poolKeys(data.live));
  const total = data.live.pool?.pnl ?? employees.filter((e) => pool.has(e.key)).reduce((s, e) => s + (e.pnl ?? 0), 0);
  return (
    <>
      <AutoRefresh seconds={30} />
      <Office employees={employees} activity={data.activity} total={total}
        series={portfolioSeries(only(data.history, pool)).map((p) => ({ t: p.t, v: p.worth - p.putIn }))}
        btc={data.live.underlyings?.BTC?.spot ?? null} btcSeries={data.btcSeries} />
    </>
  );
}
