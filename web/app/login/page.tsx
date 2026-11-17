import { redirect } from "next/navigation";
import Link from "next/link";
import { AddPasskey, PasskeyLogin } from "@/components/PasskeyButtons";
import { isAdmin } from "@/lib/admin";
import { currentUser } from "@/lib/session";

export const dynamic = "force-dynamic";

/** Sign in with a passkey (signed in already: Settings). */
export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  const [user, admin] = await Promise.all([currentUser(), isAdmin()]);
  // Signed in already: your account lives in Settings
  if (user) redirect("/settings");
  return (
    <div className="card narrow stack auth">
      <h2>Sign In</h2>
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
