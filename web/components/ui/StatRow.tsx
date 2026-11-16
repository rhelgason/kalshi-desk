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
};

/** "up" for a gain, "down" for a loss, nothing for zero. */
export const toneOf = (v: number | null | undefined) => (v == null || Math.abs(v) < 0.005 ? null : v > 0 ? "up" : "down");

/**
 * A row of connected stat cells (11-16): a header label, the number, a subline. Used for the office's three numbers,
 * the chart's highlights, the riding totals and the cockpit, so they all read the same. Four cells fold to two by
 * two on a phone.
 */
export default function StatRow({ stats, className }: { stats: Stat[]; className?: string }) {
  return (
    <div className={`stat-cells n${stats.length} ${className ?? ""}`}>
      {stats.map((s, i) => (
        <div key={i} className={`stat-cell ${s.face ? "has-face" : ""}`}>
          <div className="stat-label">{s.label}</div>
          <div className="stat-body">
            {s.face && <Avatar k={s.face.k} emoji={s.face.emoji} size={36} className="stat-face" />}
            <div className="stat-text">
              <div className={`stat-value ${s.tone ?? ""}`}>{s.value}</div>
              {s.note != null && <div className="stat-note">{s.note}</div>}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
