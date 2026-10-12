import type { Metadata } from "next";
import Link from "next/link";
import { isAdmin } from "@/lib/admin";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kalshi Desk",
  description: "Paper-trading employees competing on live Kalshi markets.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const admin = await isAdmin();
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <header className="topbar">
            <Link href="/" className="brand">
              <span aria-hidden>🏢</span> Kalshi Desk <small>paper trading</small>
            </Link>
            <nav className="nav">
              <Link href="/">Home</Link>
              <Link href="/settings">Rules</Link>
              <Link href="/backtests">Practice runs</Link>
              <Link href="/admin">{admin ? "👔 Manager" : "Log in"}</Link>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
