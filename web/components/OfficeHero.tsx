import type { ReactNode } from "react";
import { dollars } from "@/lib/format";
import StatRow, { type Stat } from "./ui/StatRow";

/**
 * The top of an office (11-16): what it's worth, what it's made of what was put in, three numbers people ask about
 * (today, the last 7 days, all time), the chart and the range's highlights. Every figure here moves only when a bet
 * wins or loses (lib/portfolio headline); what open bets are worth now is in the riding card instead.
 */
export default function OfficeHero({ label, badge, worth, putIn, stats, tabs, chart, facts, under }: {
  label: string; badge?: ReactNode; worth: number; putIn: number; stats: Stat[];
  tabs: ReactNode; chart: ReactNode; facts?: ReactNode; under?: ReactNode;
}) {
  const profit = worth - putIn;
  return (
    <section className="card money-hero office-hero">
      <div className="hero-head">
        <h1 className="office-title">{label}</h1>
        {badge}
      </div>
      <div className={`big-number ${profit >= 0 ? "up" : "down"}`}>{dollars(worth)}</div>
      <div className="change">
        <strong className={profit >= 0 ? "up" : "down"}>{dollars(profit, true)}</strong> of {dollars(putIn)} put in
      </div>
      <StatRow stats={stats} className="hero-stats-row" />
      <div className="hero-chart-head">{tabs}</div>
      {chart}
      {facts}
      {under && <div className="hero-under">{under}</div>}
    </section>
  );
}
