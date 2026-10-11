import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kalshi Desk",
  description: "A dozen paper-trading employees competing on live Kalshi markets.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <header className="topbar">
            <Link href="/" className="brand">
              <span aria-hidden>🏢</span> Kalshi Desk <small>paper trading</small>
            </Link>
            <nav className="nav">
              <Link href="/">Floor</Link>
              <Link href="/backtests">Backtests</Link>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
