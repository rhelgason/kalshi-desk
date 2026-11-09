import type { Employee, NewsItem } from "@/lib/types";
import { ago, money, perDollar } from "@/lib/format";

/** The office news: hires, promotions, awards, suspensions, retunes, and admin changes. */
export default function NewsFeed({ items, employees }: { items: NewsItem[]; employees: Pick<Employee, "key" | "name" | "emoji">[] }) {
  const who = Object.fromEntries(employees.map((e) => [e.key, e]));
  if (!items.length) return <div className="empty">Quiet day at the office.</div>;
  return (
    <ul className="feed">
      {items.map((n) => {
        const e = n.strategy ? who[n.strategy] : null;
        const name = e ? <strong>{e.name}</strong> : <strong>The desk</strong>;
        const { icon, text } = describe(n, name);
        return (
          <li key={n.id}>
            <span className="emoji" aria-hidden>{icon}</span>
            <div className="what">
              <div>{text}</div>
              <div className="reason">{ago(n.ts)}{n.detail.by === "admin" ? " · by the manager" : ""}</div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function describe(n: NewsItem, name: React.ReactNode): { icon: string; text: React.ReactNode } {
  const d = n.detail;
  switch (n.kind) {
    case "award":
      return { icon: "🏆", text: <>{name} is <strong>{d.title}</strong> ({d.roi != null ? <>{perDollar(d.roi)} on {d.settled} bets, </> : null}{money(d.pnl)} this period){d.bonus ? <>, with a {money(d.bonus, false)} bonus</> : null}</> };
    case "review":
      return { icon: "📋", text: <>Performance review finished for {d.standings?.length ?? 0} employees</> };
    case "season":
      return { icon: "🎉", text: <>Fresh start: everyone's money was reset.{d.note ? ` ${d.note}.` : ""}</> };
    case "tune":
      return d.applied
        ? { icon: "🔧", text: <>{name} retuned after testing {d.tried} settings: {Object.entries(d.changes ?? {}).map(([k, v]) => `${k} → ${v}`).join(", ")} ({d.why})</> }
        : { icon: "🔍", text: <>{name} tested {d.tried} settings and kept the current ones: {d.why}</> };
    case "hr": {
      const a = d.action as string;
      const map: Record<string, [string, React.ReactNode]> = {
        hired: ["👋", <>{name} joined the desk as an {d.level}</>],
        promoted: ["⬆️", <>{name} was promoted to <strong>{d.to}</strong>{d.roi != null ? ` (${(d.roi * 100).toFixed(1)}% this period)` : ""}</>],
        demoted: ["⬇️", <>{name} was demoted to {d.to}{d.roi != null ? ` (${(d.roi * 100).toFixed(1)}% this period)` : ""}</>],
        strike: ["⚠️", <>{name} got strike {d.strikes} for a bad period (two in a row means a week on the bench)</>],
        "strikes cleared": ["🧽", <>{name} had a decent period, so their strikes are wiped</>],
        kept: ["🤝", <>{name} had a bad period but keeps their level: {d.why}</>],
        "held back": ["⏳", <>{name} had a good period but was held back from promotion: {d.why}</>],
        suspended: ["⏸", <>{name} was suspended {d.until === "indefinitely" ? "indefinitely" : `until ${fmtDate(d.until)}`}: {d.why}</>],
        reinstated: ["▶️", <>{name} is back at work{d.why ? ` (${d.why})` : ""}</>],
        fired: ["🚪", <>{name} was fired: {d.why}</>],
        rehired: ["🔄", <>{name} was rehired as an {d.to}</>],
        bonus: ["💰", <>{name} received a {money(d.amount, false)} bonus{d.why ? `: ${d.why}` : ""}</>],
        "budget cut": ["✂️", <>{name}&apos;s bankroll was cut by {money(-d.amount, false)}</>],
      };
      const [icon, text] = map[a] ?? ["📌", <>{name}: {a}</>];
      return { icon, text };
    }
    default:
      return { icon: "🛠", text: <>{name}: {d.action ?? n.kind}{d.changes ? ` (${Object.entries(d.changes).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(", ")})` : ""}</> };
  }
}

function fmtDate(iso: string) {
  return iso ? new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric" }) : "";
}
