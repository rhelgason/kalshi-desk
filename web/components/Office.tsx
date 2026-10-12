import Link from "next/link";
import type { Activity } from "@/lib/db";
import type { Employee, Point } from "@/lib/types";
import OfficeFloor, { type FloorPerson, type Mood } from "./OfficeFloor";
import { dollars } from "@/lib/format";
import Avatar from "./Avatar";


const minutes = (iso: string) => (Date.now() - Date.parse(iso)) / 60_000;
const ago = (iso: string) => {
  const m = minutes(iso);
  return m < 60 ? `${Math.max(1, Math.round(m))}m ago` : m < 2880 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`;
};

export type { Mood };

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

// Busiest first, so the action is at the top of the list
const ORDER: Mood[] = ["celebrating", "stressed", "trading", "watching", "coffee", "sleeping", "benched", "fired"];

const MOOD_WORD: Record<Mood, string> = {
  celebrating: "🎉 winning", stressed: "😰 losing", trading: "⌨️ betting", watching: "👀 watching",
  coffee: "☕ on a break", sleeping: "💤 napping", benched: "⏸️ benched", fired: "📦 fired",
};

/** The trading floor: a live top-down office where everyone acts out what they're really doing. */
export default function Office({ employees, activity, total, btc, series }: {
  employees: Employee[];
  activity: Record<string, Activity>;
  total: number;
  btc: number | null;
  series: Point[];
}) {
  const people: FloorPerson[] = employees.map((e) => {
    const a = activity[e.key];
    const m = mood(e, a);
    const f = a?.lastFill;
    return {
      key: e.key, name: e.name, pnl: e.pnl ?? 0, mood: m.mood, line: m.line, pnlLastHour: a?.pnlLastHour ?? 0,
      lastFillTs: f?.ts ?? null,
      lastBet: f ? `bet ${dollars(f.count * f.price)} on ${f.side.toUpperCase()} at ${Math.round(f.price * 100)}¢` : null,
    };
  });
  const tape = [...employees].sort((a, b) => (b.pnl ?? 0) - (a.pnl ?? 0))
    .map((e) => `${e.name.toUpperCase()} ${dollars(e.pnl ?? 0, true)}`);
  const tapeText = [`DESK ${dollars(total, true)}`, ...(btc ? [`BTC ${dollars(btc).replace(/\.\d+$/, "")}`] : []), ...tape].join("   ★   ");
  const sorted = [...people].sort((a, b) => ORDER.indexOf(a.mood) - ORDER.indexOf(b.mood) || b.pnl - a.pnl);
  return (
    <div className="office">
      <div className="tape" aria-hidden><div className="tape-inner"><span>{tapeText}</span><span>{tapeText}</span></div></div>
      <OfficeFloor people={people} total={total} btc={btc} series={series} />
      <ul className="whos-here">
        {sorted.map((p) => (
          <li key={p.key}>
            <Link href={`/employee/${p.key}`}>
              <Avatar k={p.key} size={28} />
              <span className="who">{p.name}<span className="muted small">{MOOD_WORD[p.mood]} · {p.line}</span></span>
              <span className={p.pnl > 0.004 ? "up" : p.pnl < -0.004 ? "down" : "muted"}>{dollars(p.pnl, true)}</span>
            </Link>
          </li>
        ))}
      </ul>
      <p className="muted small office-legend">
        Everyone acts out what they&apos;re really doing on Kalshi: at their desk when they just bet, wandering when it&apos;s quiet,
        napping after hours without a good bet, ringing the bell when they win. Monitors glow green when someone&apos;s up, red when down.
        The big board shows the whole desk&apos;s profit. The parties are just for fun.
      </p>
    </div>
  );
}
