import type { Forecast } from "@/components/ForecastCard";

/**
 * The prediction model's 6-month middle guess for someone's money (11-17), for the new-user tour's "Is it working?"
 * step. Their own office's forecast once it exists and holds about this much (`own`); otherwise the newcomer table
 * on the owner's forecast (a new office joining the family with `base`), read between its amounts on a log scale.
 * Null when the model hasn't run yet.
 */
export function sixMonths(base: number, own: Forecast | null, owner: Forecast | null): number | null {
  if (own?.fan?.length && Math.abs(own.start - base) <= Math.max(5, base * 0.1)) {
    return own.fan.reduce((a, p) => (p.day > a.day ? p : a)).p50;
  }
  const rows = owner?.newcomer;
  if (!rows?.length) return null;
  if (base <= rows[0].start) return rows[0].d180.p50 * (base / rows[0].start);
  const last = rows[rows.length - 1];
  if (base >= last.start) return last.d180.p50 * (base / last.start);
  const i = rows.findIndex((r) => r.start >= base);
  const a = rows[i - 1], b = rows[i];
  const f = (Math.log(base) - Math.log(a.start)) / (Math.log(b.start) - Math.log(a.start));
  return a.d180.p50 + f * (b.d180.p50 - a.d180.p50);
}
