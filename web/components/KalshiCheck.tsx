import { ago, dollars } from "@/lib/format";
import type { TradingStatus } from "@/lib/types";

/** Where the Live number comes from: Kalshi's own account, checked against our books. */
export default function KalshiCheck({ books, env, equity, halted = false }: {
  books: NonNullable<TradingStatus["books"]>; env: string; equity: number | null; halted?: boolean;
}) {
  const where = env === "prod" ? "Kalshi" : "Kalshi demo";
  const drift = Math.abs(books.drift);
  return (
    <p className="muted small">
      Straight from {where}: {dollars(books.balance)} cash + {dollars(books.held ?? 0)} in open bets, checked {ago(books.at)}.{" "}
      {drift < 0.01
        ? <span className="up">Our books match to the cent.</span>
        : books.ok
          ? <span className="down">Our books are off by {dollars(drift)} (within the limit).</span>
          // A difference is usually a fill or payout reaching Kalshi a moment before our books: trading carries on
          // unless it lasts 30 minutes (desk/runner.py MISMATCH_CHECKS), and then the banner above says so
          : <span className="muted">Our books differ from Kalshi by {dollars(drift)} for a moment{halted ? "; trading is paused" : ", usually a bet or payout landing; trading carries on"}.</span>}
      {equity != null && <> Office pool: {dollars(equity)}.</>}
    </p>
  );
}
