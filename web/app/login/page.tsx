import Link from "next/link";
import { AddPasskey, PasskeyLogin } from "@/components/PasskeyButtons";
import { isAdmin } from "@/lib/admin";
import { home } from "@/lib/db";
import { currentUser } from "@/lib/session";
import { signOut } from "../account";

export const dynamic = "force-dynamic";

/** Sign in (a passkey), or for someone signed in: their devices and a way out. */
export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  const [user, admin] = await Promise.all([currentUser(), isAdmin()]);
  if (user) {
    const keys = await home()`SELECT device, created_at, last_used FROM public.passkeys WHERE user_id = ${user.id} ORDER BY created_at`;
    return (
      <div className="card narrow stack auth">
        <h2>Hi {user.name}</h2>
        <p className="sub">
          You stay signed in on this device{user.role === "friend" ? " and see only your own office" : ""}. Your passkeys:
        </p>
        <ul>
          {keys.map((k, i) => (
            <li key={i}>{k.device ?? "A device"} · added {new Date(k.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</li>
          ))}
        </ul>
        <p className="muted small">
          A passkey saved on an iPhone works on your other Apple devices too (and Android ones across your Google
          account). On a computer without one, choose &quot;use a phone&quot; when you sign in and scan the code.
        </p>
        <AddPasskey label="Add a passkey on this device" />
        <form action={signOut}><button className="btn">Sign out</button></form>
      </div>
    );
  }
  return (
    <div className="card narrow stack auth">
      <h2>Sign in</h2>
      <p className="sub">With the passkey you made when you joined: your face, fingerprint or device PIN. You stay signed in.</p>
      <PasskeyLogin next={next ?? "/"} />
      {admin ? (
        <>
          <p className="muted small">You&apos;re the manager (by password). Save a passkey so this device never asks again:</p>
          <AddPasskey askName />
        </>
      ) : (
        <p className="muted small">Running the desk? <Link href="/admin">Enter your manager password here</Link></p>
      )}
    </div>
  );
}
