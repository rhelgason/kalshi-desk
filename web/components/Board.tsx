"use client";

import Link from "next/link";
import { useState } from "react";
import type { Employee, Series } from "@/lib/types";
import { money, pct, tone } from "@/lib/format";
import EquityChart from "./EquityChart";
import Sparkline from "./Sparkline";

/** The equity chart and the leaderboard, wired so hovering one highlights the other. */
export default function Board({ employees, series }: { employees: Employee[]; series: Series[] }) {
  const [hot, setHot] = useState<string | null>(null);
  const ranked = [...employees].sort((a, b) => (b.pnl ?? 0) - (a.pnl ?? 0));
  const byKey = Object.fromEntries(series.map((s) => [s.key, s.points]));

  return (
    <>
      <section className="card">
        <h2>Paper P&amp;L over time</h2>
        <p className="sub">Each employee started with the same paper bankroll. Open bets are valued at current prices.</p>
        <EquityChart series={series} highlight={hot} onHighlight={setHot} />
      </section>

      <section className="card">
        <h2>Leaderboard</h2>
        <p className="sub">Ranked by paper profit. Win rate counts settled bets only.</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Employee</th>
                <th className="num">P&amp;L</th>
                <th className="num">ROI</th>
                <th>Trend</th>
                <th className="num">Win rate</th>
                <th className="num">Bets</th>
                <th className="num">Open</th>
                <th className="num">Fees</th>
                <th className="num">Max drop</th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((e, i) => (
                <tr key={e.key} className={hot === e.key ? "hot" : ""} onMouseEnter={() => setHot(e.key)} onMouseLeave={() => setHot(null)}>
                  <td className="muted">{i + 1}</td>
                  <td>
                    <Link href={`/employee/${e.key}`} className="who">
                      <span className="emoji" aria-hidden>{e.emoji}</span>
                      <span>
                        <div className="name">{e.name}</div>
                        <div className="title">{e.title}</div>
                      </span>
                    </Link>
                  </td>
                  <td className={`num ${tone(e.pnl)}`}>{money(e.pnl)}</td>
                  <td className={`num ${tone(e.roi)}`}>{pct(e.roi, true)}</td>
                  <td><Sparkline points={byKey[e.key] ?? []} /></td>
                  <td className="num">{e.win_rate == null ? "–" : pct(e.win_rate, false, 0)}</td>
                  <td className="num">{e.fills ?? 0}</td>
                  <td className="num">{e.open_positions ?? 0}</td>
                  <td className="num muted">{money(e.fees, false)}</td>
                  <td className="num muted">{pct(e.max_drawdown, false, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
