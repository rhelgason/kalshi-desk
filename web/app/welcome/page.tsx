import { redirect } from "next/navigation";
import { isAdmin } from "@/lib/admin";
import { home } from "@/lib/db";
import { currentUser } from "@/lib/session";
import JoinFlow from "../join/[token]/JoinFlow";

export const dynamic = "force-dynamic";

/**
 * Setting up Kalshi after joining (the new-user experience, 11-17): someone who joined but hasn't connected Kalshi
 * lands here from the home page until they do, wherever they left off. `?preview=1`: the manager walks through the
 * whole thing as a new friend would, with nothing checked or saved.
 */
export default async function WelcomePage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const preview = (await searchParams).preview === "1";
  const [user, admin] = await Promise.all([currentUser(), isAdmin()]);
  if (preview && admin) {
    return <JoinFlow token="" name="Friend" owner={user?.name ?? "The desk's owner"} hasKey={false} signedIn={false} preview />;
  }
  if (!user) redirect("/login");
  if (!user.office) redirect("/");
  const [office, owner] = await Promise.all([
    home()`SELECT key_box IS NOT NULL AS has FROM public.offices WHERE slug = ${user.office}`.catch(() => []),
    home()`SELECT name FROM public.users WHERE role = 'owner' ORDER BY id LIMIT 1`.catch(() => []),
  ]);
  return <JoinFlow token="" name={user.name} owner={owner[0]?.name ?? "The desk's owner"} hasKey={!!office[0]?.has} signedIn />;
}
