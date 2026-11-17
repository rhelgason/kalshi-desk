import type { ReactNode } from "react";
import Avatar from "../Avatar";

export type Stat = {
  label: ReactNode;
  value: ReactNode;
  /** colours the value: green up, red down */
  tone?: "up" | "down" | null;
  note?: ReactNode;
  /** an employee: their portrait on the left, the value and note to its right */
  face?: { k: string; emoji?: string };
  /** a record that's being set right now: the value lights up */
  hot?: boolean;
};

/** "up" for a gain, "down" for a loss, nothing for zero. */
export const toneOf = (v: number | null | undefined) => (v == null || Math.abs(v) < 0.005 ? null : v > 0 ? "up" : "down");

/** One stat: header label, then the value and note, beside the employee's portrait when there is one. */
export function StatCell({ s }: { s: Stat }) {
  return (
    <div className={`stat-cell ${s.face ? "has-face" : ""} ${s.hot ? "hot" : ""}`}>
      <div className="stat-label">{s.label}</div>
      <div className="stat-body">
        {s.face && <Avatar k={s.face.k} emoji={s.face.emoji} size={36} className="stat-face" />}
        <div className="stat-text">
          <div className={`stat-value ${s.tone ?? ""}`}>{s.value}</div>
          {s.note != null && <div className="stat-note">{s.note}</div>}
        </div>
      </div>
    </div>
  );
}

/**
 * A row of stat cells (11-16): the office's three numbers, the chart's highlights, the riding totals, the cockpit
 * and the records all use it, so they read the same. Connected cells with dividers by default (four fold to two by
 * two on a phone); `flat` when the stats are the whole card: a plain grid, no boxes inside the box; `attached` as
 * the last thing in a card: flush with its edges and bottom corners, a footer rather than a box.
 */
export default function StatRow({ stats, className, flat, attached }: {
  stats: Stat[]; className?: string; flat?: boolean; attached?: boolean;
}) {
  return (
    <div className={`stat-cells n${stats.length} ${flat ? "flat" : ""} ${attached ? "attached" : ""} ${className ?? ""}`}>
      {stats.map((s, i) => <StatCell key={i} s={s} />)}
    </div>
  );
}
