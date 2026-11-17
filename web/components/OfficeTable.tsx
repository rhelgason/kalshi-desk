"use client";

import { useState } from "react";
import { dollars, pct } from "@/lib/format";

/** One office's row: everything is from finished bets except Riding (open bets, at cost). */
export type OfficeRow = {
  key: string; name: string; color: string; paused: boolean; since: number;
  /** week: profit over the chart's range */
  putIn: number; worth: number; week: number; bets: number; won: number; perDollar: number | null;
  open: number; openCost: number;
  /** the manager's "Open" button: a bound server action */
  visit?: () => Promise<void>;
};

type Col = { key: string; label: string; money?: boolean; value: (r: OfficeRow) => number; show: (r: OfficeRow) => React.ReactNode };

const tone = (v: number) => (v > 0.0049 ? "up" : v < -0.0049 ? "down" : "");
const ret = (r: OfficeRow) => (r.worth - r.putIn) / (r.putIn || 1);

/**
 * Every office in one table under the cockpit chart (11-16): its colour is the chart's legend, any column sorts
 * (tap again to flip), biggest office first. The manager sees dollars; a friend sees only % and rates, the same
 * offices, the same staff.
 */
export default function OfficeTable({ rows, money, now, period }: { rows: OfficeRow[]; money: boolean; now: number; period: string }) {
  const cols: Col[] = [
    ...(money ? [
      { key: "putIn", label: "Put in", money: true, value: (r: OfficeRow) => r.putIn, show: (r: OfficeRow) => dollars(r.putIn) },
      { key: "worth", label: "Worth now", money: true, value: (r: OfficeRow) => r.worth, show: (r: OfficeRow) => <strong>{dollars(r.worth)}</strong> },
      { key: "profit", label: "Profit", money: true, value: (r: OfficeRow) => r.worth - r.putIn,
        show: (r: OfficeRow) => <span className={tone(r.worth - r.putIn)}>{dollars(r.worth - r.putIn, true)}</span> },
    ] : []),
    { key: "return", label: "Return", value: ret, show: (r) => <span className={tone(ret(r))}>{pct(ret(r), true, 1)}</span> },
    { key: "week", label: period, value: (r) => r.week / (r.putIn || 1),
      show: (r) => <span className={tone(r.week)}>{money ? dollars(r.week, true) : pct(r.week / (r.putIn || 1), true, 1)}</span> },
    { key: "per", label: "Per $1 bet", value: (r) => r.perDollar ?? -1,
      show: (r) => r.perDollar == null ? "–" : <span className={tone(r.perDollar)}>{`${r.perDollar >= 0 ? "+" : ""}${(r.perDollar * 100).toFixed(1)}¢`}</span> },
    { key: "won", label: "Won", value: (r) => (r.bets ? r.won / r.bets : 0),
      show: (r) => r.bets ? <>{pct(r.won / r.bets, false, 1)} <span className="muted small">of {r.bets.toLocaleString()}</span></> : "–" },
    { key: "days", label: "Days in", value: (r) => now - r.since, show: (r) => Math.max(1, Math.ceil((now - r.since) / 86_400_000)) },
    ...(money ? [{ key: "riding", label: "Riding", value: (r: OfficeRow) => r.openCost,
      show: (r: OfficeRow) => r.open ? <>{dollars(r.openCost)} <span className="muted small">· {r.open}</span></> : "–" }] : []),
  ];
  const [sort, setSort] = useState<{ key: string; desc: boolean }>({ key: money ? "worth" : "return", desc: true });
  const col = cols.find((c) => c.key === sort.key) ?? cols[0];
  const sorted = [...rows].sort((a, b) => (col.value(a) - col.value(b)) * (sort.desc ? -1 : 1));
  const by = (key: string) => setSort((s) => ({ key, desc: s.key === key ? !s.desc : true }));

  return (
    <div className="table-wrap">
      <table className="cockpit-table">
        <thead>
          <tr>
            <th>Office</th>
            {cols.map((c) => (
              <th key={c.key} className="num" aria-sort={sort.key === c.key ? (sort.desc ? "descending" : "ascending") : undefined}>
                <button type="button" className="sort-btn" onClick={() => by(c.key)}>
                  {c.label}<span className="sort-mark" aria-hidden>{sort.key === c.key ? (sort.desc ? "▾" : "▴") : ""}</span>
                </button>
              </th>
            ))}
            {money && <th />}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.key}>
              <td>
                <span className="office-name"><span className="legend-swatch" style={{ background: r.color }} /><strong>{r.name}</strong></span>
                {r.paused && <span className="badge paused-badge">Paused</span>}
              </td>
              {cols.map((c) => <td key={c.key} className="num">{c.show(r)}</td>)}
              {money && (
                <td>{r.visit && <form action={r.visit}><button className="btn small">Open</button></form>}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
