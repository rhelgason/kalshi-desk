import type { MoneyMove } from "@/lib/types";
import { money } from "@/lib/format";

/** Labels closer than this (px) share one tag, so "+$250 added" and "+$25 added" an hour apart can't overprint */
const MERGE_PX = 84;

/**
 * Money put in or taken out mid-season, marked on a chart (2026-11-09): a dotted line at each moment and a small tag
 * at the top ("+$100 added"), so a jump in the pool's value reads as a deposit, not a win. 11-22: moves close together
 * on screen share one tag with their total ("+$275 added"), and a tag near the right edge hangs to the left of its
 * line instead of running off the chart. Draw inside the chart's <svg>.
 */
export default function MoneyMarks({ marks, x, x0, x1, top, bottom }: {
  marks?: MoneyMove[]; x: (t: number) => number; x0: number; x1: number; top: number; bottom: number;
}) {
  const shown = (marks ?? []).filter((m) => m.t >= x0 && m.t <= x1).sort((a, b) => a.t - b.t);
  const groups: MoneyMove[][] = [];
  for (const m of shown) {
    const g = groups[groups.length - 1];
    if (g && x(m.t) - x(g[0].t) < MERGE_PX) g.push(m);
    else groups.push([m]);
  }
  const right = x(x1);
  return (
    <g aria-hidden className="money-marks">
      {shown.map((m) => (
        <line key={m.t} x1={x(m.t)} x2={x(m.t)} y1={top} y2={bottom} stroke="var(--text-muted)" strokeWidth={1} strokeDasharray="2 3" />
      ))}
      {groups.map((g) => {
        const sum = g.reduce((s, m) => s + m.amount, 0);
        const label = `${money(sum)} ${sum >= 0 ? "added" : "taken out"}`;
        const at = x(g[0].t);
        const flip = at + 8 + label.length * 6.2 > right; // would run past the chart's right edge
        return (
          <text key={g[0].t} x={flip ? at - 4 : at + 4} y={top + 10} fontSize={11} textAnchor={flip ? "end" : "start"}
                fill={sum >= 0 ? "var(--up)" : "var(--down)"} stroke="var(--surface-1)" strokeWidth={3} paintOrder="stroke"
                style={{ fontWeight: 600 }}>
            {label}
          </text>
        );
      })}
    </g>
  );
}
