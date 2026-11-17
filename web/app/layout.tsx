import type { Metadata, Viewport } from "next";
import { Inter, Oswald, Press_Start_2P } from "next/font/google";
import Link from "next/link";
import NavButtons from "@/components/NavButtons";
import PullToRefresh from "@/components/PullToRefresh";
import NavProgress from "@/components/NavProgress";
import HeaderLink from "@/components/HeaderLink";
import SubmitButton from "@/components/SubmitButton";
import Ticker from "@/components/Ticker";
import Taskbar from "@/components/Taskbar";
import { barColor } from "@/lib/theme";
import { readLook } from "@/lib/look";
import Avatar from "@/components/Avatar";
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


export const metadata: Metadata = {
  title: "Kalshi Desk",
  description: "Paper-trading employees competing on live Kalshi markets.",
  // On the iPhone home screen: full-screen, dark status bar over the page
  appleWebApp: { capable: true, title: "Kalshi Desk", statusBarStyle: "black-translucent" },
};

export async function generateViewport(): Promise<Viewport> {
  const { theme, mode } = await readLook();
  return { themeColor: barColor(theme, mode), viewportFit: "cover" };
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const [admin, real, book, { theme: look, mode }, user] = await Promise.all([isAdmin(), getRealBook(), viewedBook(), readLook(), currentUser()]);
  const office = await getOffice(book);
  // The manager looking at a friend's office: the header takes them back to their own view
  const inOffice = admin && isOffice(book);
  return (
    <html lang="en" data-theme={look} data-mode={mode} className={`${pixel.variable} ${sans.variable} ${condensed.variable}`}>
      <body>
        <NavProgress stamp={Date.now()} />
        <PullToRefresh />
        {/* Theme decorations: each shows only in its own look (CSS), and costs nothing elsewhere */}
        {look === "broadcast" && <Ticker book={book} />}
        <div className="shell">
          <header className="topbar">
            <HeaderLink href="/" leave={inOffice} className="brand">
              <span className="brand-mark"><Avatar k="dart_monkey" size={34} /></span>
              <span className="brand-name">Kalshi <em>Desk</em></span>
            </HeaderLink>
            <nav className="nav">
              {(user || admin) && <NavButtons book={book} hasLive={!!real} manager={admin} inOffice={inOffice} />}
              <details className="menu">
                <summary aria-label="Menu">{user ? user.name : "Menu"}</summary>
                <div className="menu-list">
                  <HeaderLink href="/settings" leave={inOffice}>Settings</HeaderLink>
                  {admin && <HeaderLink href="/offices" leave={inOffice}>Invites</HeaderLink>}
                  {admin && <HeaderLink href="/backtests" leave={inOffice}>Practice runs</HeaderLink>}
                  {user ? (
                    <>
                      <HeaderLink href="/login" leave={inOffice}>Passkeys{user.role === "owner" ? " · manager" : ""}</HeaderLink>
                      <form action={signOut}><SubmitButton>Sign out</SubmitButton></form>
                    </>
                  ) : admin ? (
                    <>
                      <HeaderLink href="/login" leave={inOffice}>Remember this device</HeaderLink>
                      <form action={logoutAction}><SubmitButton>Manager · log out</SubmitButton></form>
                    </>
                  ) : (
                    <Link href="/login">Sign in</Link>
                  )}
                </div>
              </details>
            </nav>
          </header>
          {/* The manager looking at a friend's office: always say whose, with the way back */}
          {inOffice && (
            <div className="viewing-bar">
              <span>Viewing <strong>{office?.name ?? "a friend"}&apos;s office</strong></span>
              <form action={viewOffice.bind(null, null)}><SubmitButton className="btn small primary">← Back to my office</SubmitButton></form>
            </div>
          )}
          {children}
        </div>
        {look === "desktop" && <Taskbar />}
      </body>
    </html>
  );
}
