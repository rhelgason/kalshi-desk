import { isAdmin } from "@/lib/admin";
import { logoutAction } from "../actions";
import LoginForm from "./LoginForm";

export const dynamic = "force-dynamic";

export default async function AdminPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  if (await isAdmin()) {
    return (
      <div className="card narrow stack auth">
        <h2>You&apos;re the Manager</h2>
        <p className="sub">Manager controls appear on employee pages and in Settings.</p>
        <form action={logoutAction}><button className="btn">Log out</button></form>
      </div>
    );
  }
  return (
    <div className="card narrow stack auth">
      <h2>Manager Login</h2>
      <p className="sub">The manager can hire, fire and change the desk&apos;s settings.</p>
      {process.env.ADMIN_PASSWORD ? <LoginForm next={next ?? "/"} /> : <p className="notice">Set ADMIN_PASSWORD in Vercel to enable admin controls.</p>}
    </div>
  );
}
