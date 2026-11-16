import type { ReactNode } from "react";
import type { PortfolioPoint } from "@/lib/portfolio";
import type { MoneyMove } from "@/lib/types";
import { dollars, pct } from "@/lib/format";
import PortfolioChart from "./PortfolioChart";

export type HeroStat = { label: string; value: number; note?: string; percent?: boolean };

/**
 * The top of an office (11-16): what it's worth, what it's made since it started, three numbers people ask about
 * (today, this week, since the start) and the chart. Every figure here moves only when a bet wins or loses
 * (lib/portfolio headline); what open bets are worth now is in the riding card instead.
 */
export default function OfficeHero({ label, badge, worth, putIn, since, stats, tabs, points, marks, period, under }: {
  label: string; badge?: ReactNode; worth: number; putIn: number; since: string; stats: HeroStat[];
  tabs: ReactNode; points: PortfolioPoint[]; marks?: MoneyMove[]; period: string; under?: ReactNode;
}) {
  const profit = worth - putIn;
  const first = points[0], last = points[points.length - 1];
  const change = first && last ? Math.round((last.worth - last.putIn - (first.worth - first.putIn)) * 100) / 100 || 0 : 0;
  return (
    <section className="card money-hero office-hero">
      <div className="hero-head">
        <span className="label">{label}</span>
        {badge}
      </div>
      <div className="big-number">{dollars(worth)}</div>
      <div className={`change ${profit >= 0 ? "up" : "down"}`}>
        {dollars(profit, true)} ({pct(profit / (putIn || 1), true, 1)}) since {since}
      </div>
      <div className="hero-stats">
        {stats.map((s) => (
          <div key={s.label} className="hero-stat">
            <div className="hero-stat-label">{s.label}</div>
            <div className={`hero-stat-value ${s.value > 0 ? "up" : s.value < 0 ? "down" : ""}`}>
              {s.percent ? pct(s.value, true, 1) : dollars(s.value, true)}
            </div>
            {s.note && <div className="hero-stat-note">{s.note}</div>}
          </div>
        ))}
      </div>
      <div className="hero-chart-head">
        {tabs}
      </div>
      <PortfolioChart points={points} marks={marks} />
      <p className="range-change">
        {period}: <strong className={change >= 0 ? "up" : "down"}>{dollars(change, true)}</strong>
      </p>
      {under && <div className="hero-under">{under}</div>}
    </section>
  );
}
