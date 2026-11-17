import SubmitButton from "@/components/SubmitButton";
import ThemePicker from "@/components/ThemePicker";
import Card from "@/components/ui/Card";
import { AddPasskey } from "@/components/PasskeyButtons";
import { isAdmin } from "@/lib/admin";
import { requireViewer } from "@/lib/book";
import { home } from "@/lib/db";
import { readLook } from "@/lib/look";
import { currentUser } from "@/lib/session";
import { signOut } from "../account";

export const dynamic = "force-dynamic";

const day = (d: string) => new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

/**
 * Your own settings (11-17), the same page for everyone: who you're signed in as and how, your passkeys (or, for
 * the manager by password, remembering this device), signing out, and the theme. The office's rules are on /rules.
 */
export default async function SettingsPage() {
  await requireViewer();
  const [user, admin, look] = await Promise.all([currentUser(), isAdmin(), readLook()]);
  const keys = user
    ? await home()`SELECT device, created_at FROM public.passkeys WHERE user_id = ${user.id} ORDER BY created_at`.catch(() => [])
    : [];
  const manager = user?.role === "owner" || (!user && admin);
  const name = user?.name ?? "Manager";
  return (
    <div className="stack settings">
      <Card title="Account">
        <div className="account-head">
          <span className="account-initial" aria-hidden>{name.slice(0, 1).toUpperCase()}</span>
          <div>
            <div className="account-name">{name}</div>
            <div className="muted small">
              {manager ? "Manager · sees every office" : "Sees their own office and the cockpit"}
              {" · "}{user ? "signed in with a passkey" : "signed in with the password"}
            </div>
          </div>
        </div>

        <div className="settings-rows">
          {user ? (
            <>
              {keys.map((k, i) => (
                <div key={i} className="settings-row">
                  <span aria-hidden>🔑</span>
                  <span className="grow">{k.device ?? "A device"}</span>
                  <span className="muted small">Added {day(k.created_at)}</span>
                </div>
              ))}
              <div className="settings-row settings-action"><AddPasskey label="Add a passkey on this device" /></div>
            </>
          ) : (
            <div className="settings-row settings-block">
              <div>
                <div className="settings-row-title">🔑 Remember this device</div>
                <div className="muted small">Save a passkey and this device never asks for the password again.</div>
              </div>
              <AddPasskey askName label="Save a passkey" />
            </div>
          )}
        </div>

        <form action={signOut} className="account-out"><SubmitButton className="btn quiet-danger">Sign out</SubmitButton></form>
      </Card>

      <Card title="Theme">
        <ThemePicker current={look.theme} mode={look.mode} />
      </Card>
    </div>
  );
}
