import { ago, dollars } from "@/lib/format";
import type { TradingStatus } from "@/lib/types";

/** Where the Live number comes from: Kalshi's own account, checked against our books. */
export default function KalshiCheck({ books, env, equity }: {
  books: NonNullable<TradingStatus["books"]>; env: string; equity: number | null;
}) {
  const where = env === "prod" ? "Kalshi" : "Kalshi demo";
  const drift = Math.abs(books.drift);
  return (
    <p className="muted small">
      Straight from {where}: {dollars(books.balance)} cash + {dollars(books.held ?? 0)} in open bets, checked {ago(books.at)}.{" "}
      {drift < 0.01
        ? <span className="up">Our books match to the cent.</span>
        : <span className="down">Our books are off by {dollars(drift)}{books.ok ? " (within the limit)" : ", trading paused"}.</span>}
      {equity != null && <> Office pool: {dollars(equity)}.</>}
    </p>
  );
}
