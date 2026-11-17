import { getJobs, getLive } from "@/lib/db";
import { ago } from "@/lib/format";

/** The background jobs run every 6 hours; two missed in a row means they've stopped. */
const JOBS_LATE_MS = 14 * 3600_000;
/** The bot runs every 2 minutes. */
const BOT_LATE_MS = 10 * 60_000;

/**
 * Says something only when something has stopped (11-17): the bot hasn't reported for 10 minutes, or the background
 * jobs (history sync, retuning) haven't run for 14 hours. Everything fine: nothing at all. Manager pages only.
 */
export default async function SystemAlert() {
  const [live, jobs] = await Promise.all([getLive("real").catch(() => null), getJobs().catch(() => null)]);
  const now = Date.now();
  const problems: string[] = [];
  if (live && now - Date.parse(live.updated_at) > BOT_LATE_MS)
    problems.push(`The bot hasn't run since ${ago(live.updated_at)}. Nothing new is being bet or checked against Kalshi.`);
  if (jobs && now - Date.parse(jobs.finished_at) > JOBS_LATE_MS)
    problems.push(`The background jobs last ran ${ago(jobs.finished_at)} (they run every 6 hours), so retuning and history syncing have stopped.`);
  if (!problems.length) return null;
  return (
    <div className="notice notice-bad" role="alert">
      <strong>⚠️ Something has stopped</strong>
      {problems.map((p) => <div key={p}>{p}</div>)}
      <div className="muted small">Ask Claude to look into it.</div>
    </div>
  );
}
