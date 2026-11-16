import type { ReactNode } from "react";
import { dollars, pct } from "@/lib/format";

export type HeroStat = { label: string; value: number; note?: string; percent?: boolean };

/**
 * The top of an office (11-16): what it's worth, what it's made of what was put in, three numbers people ask about
 * (today, the last 7 days, all time), the chart and the range's highlights. Every figure here moves only when a bet
 * wins or loses (lib/portfolio headline); what open bets are worth now is in the riding card instead.
 */
export default function OfficeHero({ label, badge, worth, putIn, stats, tabs, chart, facts, under }: {
  label: string; badge?: ReactNode; worth: number; putIn: number; stats: HeroStat[];
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
      <div className="hero-chart-head">{tabs}</div>
      {chart}
      {facts}
      {under && <div className="hero-under">{under}</div>}
    </section>
  );
}
