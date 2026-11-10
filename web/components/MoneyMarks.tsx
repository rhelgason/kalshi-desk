import type { MoneyMove } from "@/lib/types";
import { money } from "@/lib/format";

/**
 * Money put in or taken out mid-season, marked on a chart (2026-11-09): a dotted line at the moment with "+$100"
 * or "−$50" at the top, so a jump in the pool's value reads as a deposit, not a win. Draw inside the chart's <svg>.
 */
export default function MoneyMarks({ marks, x, x0, x1, top, bottom }: {
  marks?: MoneyMove[]; x: (t: number) => number; x0: number; x1: number; top: number; bottom: number;
}) {
  const shown = (marks ?? []).filter((m) => m.t >= x0 && m.t <= x1);
  return (
    <g aria-hidden>
      {shown.map((m) => (
        <g key={m.t}>
          <line x1={x(m.t)} x2={x(m.t)} y1={top} y2={bottom} stroke="var(--text-muted)" strokeWidth={1} strokeDasharray="2 3" />
          <text x={x(m.t) + 4} y={top + 10} fontSize={11} fill={m.amount >= 0 ? "var(--up)" : "var(--down)"}>
            {money(m.amount)} {m.amount >= 0 ? "added" : "taken out"}
          </text>
        </g>
      ))}
    </g>
  );
}
