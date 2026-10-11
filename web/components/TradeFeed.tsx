import type { Employee, Fill } from "@/lib/types";
import { ago, money } from "@/lib/format";

/** Recent paper trades, newest first, with how each one turned out. */
export default function TradeFeed({ fills, employees }: { fills: Fill[]; employees: Employee[] }) {
  const who = Object.fromEntries(employees.map((e) => [e.key, e]));
  if (!fills.length) return <div className="empty">No trades yet.</div>;
  return (
    <ul className="feed">
      {fills.map((f) => {
        const e = who[f.strategy];
        const settled = f.yes_value != null;
        const won = settled && (f.side === "yes" ? f.yes_value! >= 0.5 : f.yes_value! < 0.5);
        return (
          <li key={f.id}>
            <span className="emoji" aria-hidden>{e?.emoji ?? "•"}</span>
            <div className="what">
              <div>
                <strong>{e?.name ?? f.strategy}</strong> bought {f.count.toFixed(f.count % 1 ? 2 : 0)}{" "}
                {f.side.toUpperCase()} @ {f.price.toFixed(2)}{" "}
                <span className="muted">· {ago(f.ts)}</span>
              </div>
              <div className="reason" title={f.reason ?? ""}>{f.reason || f.ticker}</div>
            </div>
            <span className={`badge ${settled ? (won ? "up" : "down") : "muted"}`}>
              {settled ? `${won ? "✓ won" : "✗ lost"} ${money(f.pnl)}` : "open"}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
