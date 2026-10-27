import AutoRefresh from "@/components/AutoRefresh";
import Office from "@/components/Office";
import Setup from "@/components/Setup";
import { getRealBook } from "@/lib/book";
import { getActivity, getBtcSeries, getHistory, getLive, getPolicy, getRoster, getSettlementsSince, withRoster } from "@/lib/db";
import { only, poolKeys, settledSeries } from "@/lib/portfolio";

export const dynamic = "force-dynamic";

export default async function OfficePage() {
  let data;
  try {
    // The office always shows the Live book once there is one (training until then)
    const book = (await getRealBook()) ? "real" : "pretend";
    const policy = await getPolicy(book);
    // The last week only: the page refreshes every 30 seconds, and a whole seeded season is ~35k bets
    const sinceIso = new Date(Date.now() - 7 * 86_400_000 - 60_000).toISOString();
    const [live, roster, activity, history, btcSeries, settled] = await Promise.all([
      getLive(book), getRoster(book), getActivity(book, policy.season), getHistory(book, policy.season, "week"),
      getBtcSeries(book), getSettlementsSince(book, policy.season, sinceIso),
    ]);
    // Everyone works here, even staff who aren't on the Live book (Dan, Lucky, the twins in training):
    // they sit on the bench, practicing on pretend money
    const [training, trainingRoster] = book === "real"
      ? await Promise.all([getLive("pretend"), getRoster("pretend")]) : [null, {}];
    data = { policy, live, roster, activity, history, btcSeries, settled, training, trainingRoster };
  } catch (e) {
    return <Setup error={String(e)} />;
  }
  if (!data.live) return <Setup error="The bot hasn't published a status yet. Is it running?" />;
  const here = withRoster(data.live.employees, data.roster);
  const onBook = new Set(here.map((e) => e.key));
  const practicing = withRoster(data.training?.employees ?? [], data.trainingRoster)
    .filter((e) => !onBook.has(e.key) && e.status !== "fired")
    .map((e) => ({ ...e, pnl: 0, practicing: true }));
  const employees = [...here, ...practicing];
  const pool = new Set(poolKeys(data.live));
  const total = data.live.pool?.pnl ?? employees.filter((e) => pool.has(e.key)).reduce((s, e) => s + (e.pnl ?? 0), 0);
  return (
    <>
      <AutoRefresh seconds={30} />
      <Office employees={employees} activity={data.activity} total={total}
        series={settledSeries(only(data.history, pool), data.settled, data.history.since, Date.now()).map((p) => ({ t: p.t, v: p.worth - p.putIn }))}
        btc={data.live.underlyings?.BTC?.spot ?? null} btcSeries={data.btcSeries} />
    </>
  );
}
