import type { Metadata, Viewport } from "next";
import { Inter, Oswald, Press_Start_2P } from "next/font/google";
import { cookies } from "next/headers";
import Link from "next/link";
import NavButtons from "@/components/NavButtons";
import PullToRefresh from "@/components/PullToRefresh";
import Ticker from "@/components/Ticker";
import Taskbar from "@/components/Taskbar";
import { THEMES, THEME_COOKIE, THEME_PREF, parseTheme } from "@/lib/theme";
import { getOffice, getRealBook, viewedBook } from "@/lib/book";
import { isOffice } from "@/lib/db";
import { isAdmin } from "@/lib/admin";
import { currentUser } from "@/lib/session";
import { logoutAction } from "./actions";
import { signOut, viewOffice } from "./account";
import "./globals.css";
import "./themes/clean.css";
import "./themes/studio.css";
import "./themes/broadcast.css";
import "./themes/desktop.css";

const pixel = Press_Start_2P({ weight: "400", subsets: ["latin"], variable: "--font-pixel", display: "swap" });
// The other looks' type: only downloaded by a browser when its theme uses it
const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const condensed = Oswald({ subsets: ["latin"], variable: "--font-condensed", display: "swap" });

// This device's pick, else the one saved with their login (app/account.ts savePrefs)
const theme = async () => parseTheme((await cookies()).get(THEME_COOKIE)?.value ?? ((await currentUser())?.prefs[THEME_PREF] as string));

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
  const [admin, real, book, look, user] = await Promise.all([isAdmin(), getRealBook(), viewedBook(), theme(), currentUser()]);
  const office = await getOffice(book);
  return (
    <html lang="en" data-theme={look} className={`${pixel.variable} ${sans.variable} ${condensed.variable}`}>
      <body>
        <PullToRefresh />
        {/* Theme decorations: each shows only in its own look (CSS), and costs nothing elsewhere */}
        {look === "broadcast" && <Ticker book={book} />}
        <div className="shell">
          <header className="topbar">
            <Link href="/" className="brand">
              <span className="brand-name">Kalshi Desk</span>
            </Link>
            <nav className="nav">
              {(user || admin) && <NavButtons book={book} hasLive={!!real} manager={admin} />}
              <details className="menu">
                <summary aria-label="Menu">{user ? user.name : "Menu"}</summary>
                <div className="menu-list">
                  <Link href="/settings">Settings</Link>
                  {admin && <Link href="/offices">Invites</Link>}
                  {admin && <Link href="/backtests">Practice runs</Link>}
                  {user ? (
                    <>
                      <Link href="/login">Passkeys{user.role === "owner" ? " · manager" : ""}</Link>
                      <form action={signOut}><button>Sign out</button></form>
                    </>
                  ) : admin ? (
                    <>
                      <Link href="/login">Remember this device</Link>
                      <form action={logoutAction}><button>Manager · log out</button></form>
                    </>
                  ) : (
                    <Link href="/login">Sign in</Link>
                  )}
                </div>
              </details>
            </nav>
          </header>
          {/* The manager looking at a friend's office: always say whose, with the way back */}
          {admin && isOffice(book) && (
            <div className="viewing-bar">
              <span>Viewing <strong>{office?.name ?? "a friend"}&apos;s office</strong></span>
              <form action={viewOffice.bind(null, null)}><button className="btn small">Back to my office</button></form>
            </div>
          )}
          {children}
        </div>
        {look === "desktop" && <Taskbar />}
      </body>
    </html>
  );
}
