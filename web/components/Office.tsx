import type { Activity } from "@/lib/db";
import type { Employee, Point } from "@/lib/types";
import OfficeFloor, { type FloorPerson, type Mood } from "./OfficeFloor";
import { dollars } from "@/lib/format";


const minutes = (iso: string) => (Date.now() - Date.parse(iso)) / 60_000;
const ago = (iso: string) => {
  const m = minutes(iso);
  return m < 60 ? `${Math.max(1, Math.round(m))}m ago` : m < 2880 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`;
};

export type { Mood };

/** What an employee is doing right now, from their real activity, and what their speech bubble says. */
export function mood(e: Employee, a: Activity | undefined): { mood: Mood; line: string } {
  if (e.status === "fired") return { mood: "fired", line: "Packed up their desk." };
  if (e.practicing) return { mood: "benched", line: "Practicing on pretend money." };
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

/** The office: a live top-down floor where everyone acts out what they're really doing. */
export default function Office({ employees, activity, total, btc, series, btcSeries }: {
  employees: Employee[];
  activity: Record<string, Activity>;
  total: number;
  btc: number | null;
  series: Point[];
  btcSeries: Point[];
}) {
  const people: FloorPerson[] = employees.map((e) => {
    const a = activity[e.key];
    const m = mood(e, a);
    const f = a?.lastFill;
    return {
      key: e.key, name: e.name, pnl: e.pnl ?? 0, mood: m.mood, line: m.line, pnlLastHour: a?.pnlLastHour ?? 0,
      lastFillTs: f?.ts ?? null,
      lastBet: f ? `bet ${dollars(f.count * f.price)} bitcoin goes ${f.side === "yes" ? "up" : "down"}` : null,
    };
  });
  return (
    <div className="office">
      <OfficeFloor people={people} total={total} btc={btc} series={series} btcSeries={btcSeries} />
    </div>
  );
}
