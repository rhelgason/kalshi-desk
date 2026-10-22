import type { Metadata, Viewport } from "next";
import { Press_Start_2P } from "next/font/google";
import Link from "next/link";
import Avatar from "@/components/Avatar";
import NavButtons from "@/components/NavButtons";
import PullToRefresh from "@/components/PullToRefresh";
import CoinSwitch from "@/components/CoinSwitch";
import { getRealBook, viewedBook, viewedCoin } from "@/lib/book";
import { isAdmin } from "@/lib/admin";
import { logoutAction } from "./actions";
import "./globals.css";

const pixel = Press_Start_2P({ weight: "400", subsets: ["latin"], variable: "--font-pixel", display: "swap" });

export const metadata: Metadata = {
  title: "Kalshi Desk",
  description: "Paper-trading employees competing on live Kalshi markets.",
  // On the iPhone home screen: full-screen, dark status bar over the page
  appleWebApp: { capable: true, title: "Kalshi Desk", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = { themeColor: "#0f0d1f", viewportFit: "cover" };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const [admin, real, book, coin] = await Promise.all([isAdmin(), getRealBook(), viewedBook(), viewedCoin()]);
  return (
    <html lang="en" className={pixel.variable}>
      <body>
        <PullToRefresh />
        <div className="shell">
          <header className="topbar">
            <Link href="/" className="brand">
              <Avatar k="dart_monkey" size={36} />
              <span className="brand-name">KALSHI DESK</span>
            </Link>
            <nav className="nav">
              <NavButtons book={book} hasLive={!!real} />
              <CoinSwitch value={coin} />
              <details className="menu">
                <summary aria-label="More">☰</summary>
                <div className="menu-list">
                  <Link href="/settings">📜 Desk rules</Link>
                  <Link href="/backtests">🕹️ Practice runs</Link>
                  {admin ? (
                    <form action={logoutAction}><button>👔 Manager · log out</button></form>
                  ) : (
                    <Link href="/admin">🔑 Manager log in</Link>
                  )}
                </div>
              </details>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
