import Link from "next/link";
import { home } from "@/lib/db";
import { currentUser } from "@/lib/session";
import { readInvite } from "../../account";
import JoinFlow from "./JoinFlow";

export const dynamic = "force-dynamic";

/** An invite link from the owner (made on /offices): joining, or (for someone already in) a new device. */
export default async function JoinPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const [invite, user] = await Promise.all([readInvite(token), currentUser()]);
  const signedIn = !!user && !!invite?.userId && user.id === invite.userId;
  if (!invite || invite.expired || (invite.used && !signedIn)) {
    return (
      <div className="card narrow stack">
        <h2>This invite link doesn&apos;t work</h2>
        <p className="sub">{!invite ? "It isn't one we know." : invite.expired ? "It has expired (they last a week)." : "It has been used already."} Ask for a new one.</p>
        <Link href="/login">Already joined? Sign in</Link>
      </div>
    );
  }
  const owner = (await home()`SELECT name FROM public.users WHERE role = 'owner' ORDER BY id LIMIT 1`.catch(() => []))[0]?.name;
  return <JoinFlow token={token} name={invite.name} owner={owner ?? "The desk's owner"} hasKey={invite.hasKey} signedIn={signedIn} />;
}
