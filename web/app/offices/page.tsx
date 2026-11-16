import { redirect } from "next/navigation";
import { InviteForm, OpenOffice } from "@/components/OfficeAdmin";
import { isAdmin } from "@/lib/admin";
import { getKillSwitch, getLive, getPolicy, getSeasonStart, home, type Book } from "@/lib/db";
import { ago, dollars } from "@/lib/format";
import { headline } from "@/lib/portfolio";

export const dynamic = "force-dynamic";

type Row = { slug: string; name: string; status: string; note: string | null; share: boolean; user_id: number | null; has_key: boolean };

/** Friends' offices at a glance, for the owner (only offices whose friend agreed to share, see app/join). */
export default async function OfficesPage() {
  if (!(await isAdmin())) redirect("/admin?next=/offices");
  const rows = (await home()`
    SELECT u.office AS slug, u.name, coalesce(o.status, 'setup') AS status, o.note, u.share_overview AS share, u.id AS user_id,
           o.key_box IS NOT NULL AS has_key
    FROM public.users u LEFT JOIN public.offices o ON o.slug = u.office
    WHERE u.role = 'friend' ORDER BY u.created_at`.catch(() => [])) as unknown as Row[];
  const offices = await Promise.all(rows.map(async (r) => {
    const book = `office_${r.slug}` as Book;
    if (r.status !== "active") return { r, book, live: null };
    try {
      const [live, policy, kill] = await Promise.all([getLive(book), getPolicy(book), getKillSwitch(book)]);
      const since = (await getSeasonStart(book, policy.season)) ?? 0;
      return { r, book, live, kill, top: live ? headline(live, true, since) : null };
    } catch {
      return { r, book, live: null };
    }
  }));
  const status = (o: (typeof offices)[number]) => {
    if (o.r.status === "setup") return o.r.has_key ? "opening" : "joining (no Kalshi key yet)";
    if (o.r.status === "ready") return "opening (within 2 minutes)";
    if ("kill" in o && o.kill?.halted) return `⏸ ${o.kill.reason ?? "paused"}`;
    return o.live ? `running · ${ago(o.live.updated_at)}` : "running";
  };
  return (
    <div className="stack">
      <section className="card">
        <h2>Friends&apos; Offices</h2>
        <p className="sub">
          Each friend&apos;s own Kalshi account, run by your real-money staff and playbook (who&apos;s hired, bet size,
          review rules), with its own pool, levels and awards. They run on the server half a minute after yours, and
          never bid on a market before you or a tick over your bid.
        </p>
        {offices.length ? (
          <table className="office-table">
            <thead><tr><th>Friend</th><th>Kalshi</th><th>Profit</th><th>Status</th><th /></tr></thead>
            <tbody>
              {offices.map((o) => (
                <tr key={o.r.slug}>
                  <td><strong>{o.r.name}</strong></td>
                  <td>{"top" in o && o.top ? dollars(o.top.worth) : "—"}</td>
                  <td className={"top" in o && o.top ? (o.top.profit >= 0 ? "up" : "down") : ""}>
                    {"top" in o && o.top ? dollars(o.top.profit, true) : "—"}
                  </td>
                  <td className="small">
                    {status(o)}
                    {o.r.note && <div className="down">{o.r.note}</div>}
                  </td>
                  <td>{o.live && <OpenOffice book={o.book} />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="muted">No friends yet.</p>}
      </section>
      <section className="card narrow">
        <h2>Invite a Friend</h2>
        <p className="sub">They open the link on their phone or computer, save a passkey and connect their Kalshi key. About five minutes.</p>
        <InviteForm />
      </section>
      {rows.length > 0 && (
        <section className="card narrow">
          <h2>New Sign-In Link</h2>
          <p className="sub">For a friend on a new phone without their passkey: they add one and carry on.</p>
          {rows.filter((r) => r.user_id).map((r) => (
            <div key={r.slug} className="stack-tight"><strong>{r.name}</strong><InviteForm forUser={r.user_id!} name={r.name} /></div>
          ))}
        </section>
      )}
    </div>
  );
}
