import type { Metadata, Viewport } from "next";
import { Inter, Oswald, Press_Start_2P } from "next/font/google";
import { cookies } from "next/headers";
import Link from "next/link";
import Avatar from "@/components/Avatar";
import NavButtons from "@/components/NavButtons";
import PullToRefresh from "@/components/PullToRefresh";
import ThemePicker from "@/components/ThemePicker";
import Ticker from "@/components/Ticker";
import Taskbar from "@/components/Taskbar";
import { THEMES, THEME_COOKIE, parseTheme } from "@/lib/theme";
import { getRealBook, viewedBook } from "@/lib/book";
import { isAdmin } from "@/lib/admin";
import { logoutAction } from "./actions";
import "./globals.css";
import "./themes/clean.css";
import "./themes/broadcast.css";
import "./themes/desktop.css";

const pixel = Press_Start_2P({ weight: "400", subsets: ["latin"], variable: "--font-pixel", display: "swap" });
// The other looks' type: only downloaded by a browser when its theme uses it
const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const condensed = Oswald({ subsets: ["latin"], variable: "--font-condensed", display: "swap" });

const theme = async () => parseTheme((await cookies()).get(THEME_COOKIE)?.value);

export const metadata: Metadata = {
  title: "Kalshi Desk",
  description: "Paper-trading employees competing on live Kalshi markets.",
  // On the iPhone home screen: full-screen, dark status bar over the page
  appleWebApp: { capable: true, title: "Kalshi Desk", statusBarStyle: "black-translucent" },
};

export async function generateViewport(): Promise<Viewport> {
  return { themeColor: THEMES[await theme()].color, viewportFit: "cover" };
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const [admin, real, book, look] = await Promise.all([isAdmin(), getRealBook(), viewedBook(), theme()]);
  return (
    <html lang="en" data-theme={look} className={`${pixel.variable} ${sans.variable} ${condensed.variable}`}>
      <body>
        <PullToRefresh />
        {/* Theme decorations: each shows only in its own look (CSS), and costs nothing elsewhere */}
        {look === "broadcast" && <Ticker book={book} />}
        <div className="shell">
          <header className="topbar">
            <Link href="/" className="brand">
              <Avatar k="dart_monkey" size={36} />
              <span className="brand-name">KALSHI DESK</span>
            </Link>
            <nav className="nav">
              <NavButtons book={book} hasLive={!!real} />
              <details className="menu">
                <summary aria-label="More">☰</summary>
                <div className="menu-list">
                  <ThemePicker current={look} />
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
        {look === "desktop" && <Taskbar />}
      </body>
    </html>
  );
}
