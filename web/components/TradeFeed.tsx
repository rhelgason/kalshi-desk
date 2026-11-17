import type { Employee, Fill } from "@/lib/types";
import { ago, money, shortName } from "@/lib/format";

/** "bitcoin goes up" for the 15-minute bitcoin markets; plain YES/NO otherwise. */
const what = (f: Fill) =>
  f.ticker.startsWith("KXBTC15M") ? `bitcoin goes ${f.side === "yes" ? "up" : "down"}` : `on ${f.side.toUpperCase()}`;
import Avatar from "./Avatar";

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
            <Avatar k={f.strategy} emoji={e?.emoji ?? "•"} size={36} />
            <div className="what">
              <div>
                <strong>{e ? shortName(e.name) : f.strategy}</strong> bet {money(f.count * f.price, false)} {what(f)}{" "}
                <span className="muted">· {ago(f.ts)}</span>
              </div>
              <div className="reason" title={f.reason ?? ""}>
                {Math.round(f.price * 100)}¢ odds, so a win pays {money(f.count, false)}
              </div>
            </div>
            <span className={`badge ${settled ? (won ? "up" : "down") : "muted"}`}>
              {settled ? `${won ? "won" : "lost"} ${money(f.pnl)}` : "riding"}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
