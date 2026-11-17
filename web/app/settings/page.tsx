import SubmitButton from "@/components/SubmitButton";
import ThemePicker from "@/components/ThemePicker";
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
 * Your own settings (11-17), the same page for everyone: who you're signed in as, your passkeys (or, for the manager
 * by password, remembering this device), signing out, and how the site looks. The office's rules are on /rules.
 */
export default async function SettingsPage() {
  await requireViewer();
  const [user, admin, look] = await Promise.all([currentUser(), isAdmin(), readLook()]);
  const keys = user
    ? await home()`SELECT device, created_at FROM public.passkeys WHERE user_id = ${user.id} ORDER BY created_at`.catch(() => [])
    : [];
  const manager = user?.role === "owner" || (!user && admin);
  return (
    <div className="stack">
      <section className="card">
        <h2>Account</h2>
        <dl className="kv">
          <dt>Signed in as</dt><dd><strong>{user?.name ?? "The manager"}</strong></dd>
          <dt>You see</dt><dd>{manager ? "Every office, as the manager: you can hire, fire and change the rules" : "Your own office, and every office side by side on the cockpit"}</dd>
          <dt>On this device</dt><dd>{user ? "Signed in with a passkey; you stay signed in" : "Signed in with the manager password"}</dd>
        </dl>
        {user ? (
          <>
            <div className="section-title">Your passkeys</div>
            <ul className="plain-list">
              {keys.map((k, i) => <li key={i}>{k.device ?? "A device"} <span className="muted">· added {day(k.created_at)}</span></li>)}
            </ul>
            <p className="muted small">
              A passkey saved on an iPhone works on your other Apple devices too (and Android ones across your Google
              account). On a computer without one, choose &quot;use a phone&quot; when you sign in and scan the code.
            </p>
            <AddPasskey label="📱 Add a passkey on this device" />
          </>
        ) : (
          <>
            <p className="muted small">Save a passkey and this device never asks for the password again.</p>
            <AddPasskey askName />
          </>
        )}
        <form action={signOut} className="account-out"><SubmitButton className="btn">Sign out</SubmitButton></form>
      </section>
      <section className="card">
        <h2>Look</h2>
        <ThemePicker current={look.theme} mode={look.mode} />
      </section>
    </div>
  );
}
