"use client";

import { useState } from "react";
import type { Employee, Fill } from "@/lib/types";
import { dollars } from "@/lib/format";
import TradeFeed from "./TradeFeed";
import Card from "./ui/Card";

const STEP = 10;

/**
 * Finished and riding bets, newest first (11-16): ten at a time, "Show 10 more" under the last row (so it moves down
 * with the list), and "Show fewer" folds it back to ten. A line on the last 24 hours heads it.
 */
export default function LatestBets({ fills, employees, day }: {
  fills: Fill[]; employees: Employee[];
  day: { n: number; won: number; pnl: number };
}) {
  const [shown, setShown] = useState(STEP);
  return (
    <Card title="Latest Bets" className="latest" aside={<>
      Last 24h: {day.n
        ? <>{day.won} of {day.n} won · <strong className={day.pnl >= 0 ? "up" : "down"}>{dollars(day.pnl, true)}</strong></>
        : "nothing finished"}
    </>}>
      <TradeFeed fills={fills.slice(0, shown)} employees={employees} />
      {(fills.length > shown || shown > STEP) && (
        <div className="more-row">
          {fills.length > shown && (
            <button className="btn small" onClick={() => setShown((n) => n + STEP)}>Show {Math.min(STEP, fills.length - shown)} more</button>
          )}
          {shown > STEP && <button className="btn small ghost" onClick={() => setShown(STEP)}>Show fewer</button>}
        </div>
      )}
    </Card>
  );
}
