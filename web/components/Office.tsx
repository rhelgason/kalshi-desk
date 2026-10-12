import Link from "next/link";
import type { Activity } from "@/lib/db";
import type { Employee, Point } from "@/lib/types";
import { dollars } from "@/lib/format";
import Avatar from "./Avatar";

export type Mood = "celebrating" | "stressed" | "trading" | "watching" | "coffee" | "sleeping" | "benched" | "fired";

const minutes = (iso: string) => (Date.now() - Date.parse(iso)) / 60_000;
const ago = (iso: string) => {
  const m = minutes(iso);
  return m < 60 ? `${Math.max(1, Math.round(m))}m ago` : m < 2880 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`;
};

/** What an employee is doing right now, from their real activity, and what their speech bubble says. */
export function mood(e: Employee, a: Activity | undefined): { mood: Mood; line: string } {
  if (e.status === "fired") return { mood: "fired", line: "Packed up their desk." };
  if (e.status === "suspended") {
    const until = e.suspended_until && !e.suspended_until.startsWith("9999")
      ? new Date(e.suspended_until).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : null;
    return { mood: "benched", line: until ? `On the bench until ${until}.` : "On the bench." };
  }
  const pnl = a?.pnlLastHour ?? 0;
  if (pnl >= 5) return { mood: "celebrating", line: `${dollars(pnl, true)} this hour!` };
  if (pnl <= -5) return { mood: "stressed", line: `${dollars(pnl, true)} this hour…` };
  const last = a?.lastFill;
  if (last && minutes(last.ts) < 10) {
    return { mood: "trading", line: `Bet ${dollars(last.count * last.price)} on ${last.side.toUpperCase()}!` };
  }
  if (last && minutes(last.ts) < 60) return { mood: "watching", line: "Watching the markets…" };
  if (last && minutes(last.ts) < 360) return { mood: "coffee", line: `Coffee break. Last bet ${ago(last.ts)}.` };
  return { mood: "sleeping", line: last ? `Zzz… no good bets since ${ago(last.ts)}.` : "Zzz… hasn't found a bet yet." };
}

// Busiest desks first, so the action is at the top on a phone
const ORDER: Mood[] = ["celebrating", "stressed", "trading", "watching", "coffee", "sleeping", "benched", "fired"];

const MOOD_WORD: Record<Mood, string> = {
  celebrating: "🎉 winning", stressed: "😰 losing", trading: "⌨️ betting", watching: "👀 watching",
  coffee: "☕ break", sleeping: "💤 asleep", benched: "⏸️ benched", fired: "📦 fired",
};

/** A tiny pixel chart for the desk monitor. */
function Screen({ points, up }: { points: Point[]; up: boolean }) {
  if (points.length < 2) return <div className="screen idle" />;
  const xs = points.map((p) => p.t), vs = points.map((p) => p.v);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), lo = Math.min(...vs), hi = Math.max(...vs);
  const pts = points.map((p) => `${(((p.t - x0) / (x1 - x0 || 1)) * 30 + 1).toFixed(1)},${(17 - ((p.v - lo) / (hi - lo || 1)) * 14).toFixed(1)}`).join(" ");
  return (
    <div className={`screen ${up ? "up" : "down"}`}>
      <svg viewBox="0 0 32 20" preserveAspectRatio="none" shapeRendering="crispEdges">
        <polyline points={pts} fill="none" stroke="currentColor" strokeWidth={1.5} />
      </svg>
    </div>
  );
}

function Desk({ e, a, trend }: { e: Employee; a?: Activity; trend: Point[] }) {
  const { mood: m, line } = mood(e, a);
  const pnl = e.pnl ?? 0;
  const away = m === "benched" || m === "fired";
  return (
    <Link href={`/employee/${e.key}`} className={`desk-cell ${m}`} aria-label={`${e.name}: ${MOOD_WORD[m]}. ${line}`}>
      <div className="bubble">{line}</div>
      <div className="station">
        <div className="chair" />
        {!away && (
          <div className="sitter">
            <Avatar k={e.key} emoji={e.emoji} size={64} />
            {m === "sleeping" && <div className="zzz"><span>Z</span><span>Z</span><span>Z</span></div>}
            {m === "celebrating" && <div className="coins"><span>$</span><span>$</span><span>$</span></div>}
            {m === "stressed" && <div className="sweat" />}
            {m === "watching" && <div className="phone" />}
          </div>
        )}
        <Screen points={trend} up={pnl >= 0} />
        {m === "coffee" && <div className="mug" />}
        {m === "trading" && <div className="keyboard" />}
        {m === "benched" && <div className="sign">BENCHED</div>}
        {m === "fired" && <div className="box" />}
        <div className="desk-top" />
      </div>
      <div className="plate">
        <span className="plate-name">{e.name}</span>
        <span className={pnl > 0.004 ? "up" : pnl < -0.004 ? "down" : "muted"}>{dollars(pnl, true)}</span>
        <span className="plate-mood">{MOOD_WORD[m]}</span>
      </div>
    </Link>
  );
}

/** The trading floor: every employee at their desk, acting out what they're really doing. */
export default function Office({ employees, activity, trends, total, season, btc }: {
  employees: Employee[];
  activity: Record<string, Activity>;
  trends: Record<string, Point[]>;
  total: number;
  season: number;
  btc: number | null;
}) {
  const moods = employees.map((e) => mood(e, activity[e.key]).mood);
  const count = (...ms: Mood[]) => moods.filter((m) => ms.includes(m)).length;
  const tape = [...employees].sort((a, b) => (b.pnl ?? 0) - (a.pnl ?? 0))
    .map((e) => `${e.name.toUpperCase()} ${dollars(e.pnl ?? 0, true)}`);
  const tapeText = [`DESK ${dollars(total, true)}`, ...(btc ? [`BTC ${dollars(btc).replace(/\.\d+$/, "")}`] : []), ...tape].join("   ★   ");
  return (
    <div className="office">
      <div className="wall">
        <div className="windows" aria-hidden />
        <div className="office-sign">
          <span className="pixel">Season {season} trading floor</span>
          <span className="small muted">
            {count("trading", "celebrating", "stressed")} betting · {count("watching")} watching · {count("coffee")} on break · {count("sleeping")} asleep{count("benched") ? ` · ${count("benched")} benched` : ""}
          </span>
        </div>
      </div>
      <div className="tape" aria-hidden><div className="tape-inner"><span>{tapeText}</span><span>{tapeText}</span></div></div>
      <div className="desks">
        {[...employees]
          .sort((a, b) => ORDER.indexOf(mood(a, activity[a.key]).mood) - ORDER.indexOf(mood(b, activity[b.key]).mood) || (b.pnl ?? 0) - (a.pnl ?? 0))
          .map((e) => <Desk key={e.key} e={e} a={activity[e.key]} trend={trends[e.key] ?? []} />)}
      </div>
      <p className="muted small office-legend">
        Everyone acts out what they&apos;re really doing: ⌨️ just placed a bet · 👀 bet within the hour · ☕ quiet for a while · 💤 no bets for 6+ hours ·
        🎉/😰 won or lost $5+ in the last hour. The little screen is their profit this season. Tap a desk for details.
      </p>
    </div>
  );
}
