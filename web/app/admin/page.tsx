import { isAdmin } from "@/lib/admin";
import { logoutAction } from "../actions";
import LoginForm from "./LoginForm";

export const dynamic = "force-dynamic";

export default async function AdminPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  if (await isAdmin()) {
    return (
      <div className="card" style={{ maxWidth: 420 }}>
        <h2>You&apos;re the manager</h2>
        <p className="sub">Admin controls appear on employee pages and in the Handbook.</p>
        <form action={logoutAction}><button className="btn">Log out</button></form>
      </div>
    );
  }
  return (
    <div className="card" style={{ maxWidth: 420 }}>
      <h2>Manager login</h2>
      <p className="sub">Anyone can watch the desk. Only the manager can hire, fire, and change settings.</p>
      {process.env.ADMIN_PASSWORD ? <LoginForm next={next ?? "/"} /> : <p className="notice">Set ADMIN_PASSWORD in Vercel to enable admin controls.</p>}
    </div>
  );
}
