import Tour from "@/components/Tour";
import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, Inter, Press_Start_2P } from "next/font/google";
import Link from "next/link";
import NavButtons from "@/components/NavButtons";
import PullToRefresh from "@/components/PullToRefresh";
import NavProgress from "@/components/NavProgress";
import HeaderLink from "@/components/HeaderLink";
import SubmitButton from "@/components/SubmitButton";
import Taskbar from "@/components/Taskbar";
import { barColor } from "@/lib/theme";
import { readLook } from "@/lib/look";
import Avatar from "@/components/Avatar";
import { getOffice, getRealBook, viewedBook } from "@/lib/book";
import { isOffice } from "@/lib/db";
import { isAdmin } from "@/lib/admin";
import { currentUser } from "@/lib/session";
import { viewOffice } from "./account";
import Menu from "@/components/Menu";
import "./globals.css";
import "./themes/base.css";
import "./themes/studio.css";
import "./themes/office.css";
import "./themes/desktop.css";
import "./themes/terminal.css";

const pixel = Press_Start_2P({ weight: "400", subsets: ["latin"], variable: "--font-pixel", display: "swap" });
// The other looks' type: only downloaded by a browser when its theme uses it
const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const mono = IBM_Plex_Mono({ weight: ["400", "500", "600", "700"], subsets: ["latin"], variable: "--font-mono", display: "swap" });


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
    <html lang="en" data-theme={look} data-mode={mode} className={`${pixel.variable} ${sans.variable} ${mono.variable}`}>
      <body>
        <NavProgress stamp={Date.now()} />
        <PullToRefresh />
        {/* Theme decorations: each shows only in its own look (CSS), and costs nothing elsewhere */}
        <div className="shell">
          <header className="topbar">
            <HeaderLink href="/" leave={inOffice} className="brand">
              <span className="brand-mark"><Avatar k="dart_monkey" size={34} /></span>
              <span className="brand-name">Kalshi <em>Desk</em></span>
            </HeaderLink>
            <nav className="nav">
              {(user || admin) && <NavButtons book={book} hasLive={!!real} manager={admin} inOffice={inOffice} />}
              {/* The same two places for everyone signed in (11-17): their own settings (account, sign-out, look) and the
                  office's rules. Invites live on the cockpit now */}
              <Menu label={user ? user.name : admin ? "Manager" : "Menu"}>
                {user || admin ? (
                  <>
                    <HeaderLink href="/settings" leave={inOffice}>⚙️ Settings</HeaderLink>
                    <HeaderLink href="/rules" leave={inOffice}>📜 Office Rules</HeaderLink>
                  </>
                ) : (
                  <Link href="/login">🔑 Sign in</Link>
                )}
              </Menu>
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
        {/* The new-user experience's guided tour: its step is kept with the login until they finish (or the manager's preview) */}
        {(user || admin) && <Tour start={typeof user?.prefs?.nux === "string" && /^\d+$/.test(user.prefs.nux) ? Number(user.prefs.nux) : null} />}
      </body>
    </html>
  );
}
