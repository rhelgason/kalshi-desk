import Card from "./ui/Card";
import { InviteForm, SignInLink } from "./OfficeAdmin";
import { home } from "@/lib/db";

type Friend = { slug: string; name: string; status: string; note: string | null; user_id: number | null; has_key: boolean };

/** Where a friend's office is before it trades (the cockpit's table shows it once it does). */
const stage = (f: Friend) =>
  f.status === "setup" ? (f.has_key ? "Opening" : "Joined, no Kalshi key yet")
    : f.status === "ready" ? "Opening within 2 minutes"
    : f.status;

/**
 * Bringing friends in (11-17, was its own Invites page; the cockpit's table already shows every trading office):
 * a new invite link, a fresh sign-in link for a friend on a new phone, and anyone still joining. Manager only.
 */
export default async function InviteCard() {
  const friends = (await home()`
    SELECT u.office AS slug, u.name, coalesce(o.status, 'setup') AS status, o.note, u.id AS user_id, o.key_box IS NOT NULL AS has_key
    FROM public.users u LEFT JOIN public.offices o ON o.slug = u.office
    WHERE u.role = 'friend' ORDER BY u.created_at`.catch(() => [])) as unknown as Friend[];
  const joining = friends.filter((f) => f.status !== "active");
  const signedUp = friends.filter((f) => f.user_id).map((f) => ({ id: f.user_id!, name: f.name }));
  return (
    <Card title="Invite a Friend" className="invite-card">
      <div className="invite-grid">
        <div className="invite-part">
          <h3>New friend</h3>
          <p className="muted small">They open the link on their phone or computer, save a passkey and connect their Kalshi key. About five minutes. Their office runs your real-money staff and rules, half a minute after yours.</p>
          <InviteForm />
        </div>
        {signedUp.length > 0 && (
          <div className="invite-part">
            <h3>Lost their phone?</h3>
            <p className="muted small">A fresh sign-in link for a friend on a new device without their passkey: they add one and carry on.</p>
            <SignInLink friends={signedUp} />
          </div>
        )}
      </div>
      {joining.length > 0 && (
        <ul className="plain-list joining">
          {joining.map((f) => (
            <li key={f.slug}><strong>{f.name}</strong> <span className="muted">· {stage(f)}</span>{f.note && <div className="down small">{f.note}</div>}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}
