/**
 * The value of a line chart at any time t, matching how it's drawn: straight
 * lines between points (or flat steps, for money put in). Before the first
 * point there's no value; after the last, the last value holds.
 */
export function lerpAt<P>(points: P[], t: number, time: (p: P) => number, value: (p: P) => number, step = false): number | null {
  if (!points.length || t < time(points[0])) return null;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1], b = points[i];
    const ta = time(a), tb = time(b);
    if (t <= tb) {
      if (step || tb === ta) return t < tb ? value(a) : value(b);
      return value(a) + ((t - ta) / (tb - ta)) * (value(b) - value(a));
    }
  }
  return value(points[points.length - 1]);
}
