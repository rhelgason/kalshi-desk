export const money = (x: number | null | undefined, signed = true) => {
  if (x == null || Number.isNaN(x)) return "–";
  const s = Math.abs(x) >= 1000 ? `$${(Math.abs(x) / 1000).toFixed(1)}K` : `$${Math.abs(x).toFixed(2)}`;
  if (!signed) return x < 0 ? `-${s}` : s;
  return x > 0.004 ? `+${s}` : x < -0.004 ? `−${s}` : s;
};

export const pct = (x: number | null | undefined, signed = false, digits = 1) => {
  if (x == null || Number.isNaN(x)) return "–";
  const v = (x * 100).toFixed(digits);
  return signed && x > 0 ? `+${v}%` : x < 0 ? `−${v.replace("-", "")}%` : `${v}%`;
};

export const tone = (x: number | null | undefined) =>
  x == null || Math.abs(x) < 0.005 ? "flat" : x > 0 ? "up" : "down";

export function ago(iso: string | null | undefined): string {
  if (!iso) return "never";
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (s < 90) return `${Math.round(s)}s ago`;
  if (s < 5400) return `${Math.round(s / 60)}m ago`;
  if (s < 172800) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

export const usd = (x: number) =>
  x >= 1000 ? `$${x.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : `$${x.toFixed(2)}`;

/** Per-contract edges are small; show them in cents with one decimal. */
export const cents = (x: number | null | undefined) => {
  if (x == null || Number.isNaN(x)) return "–";
  const c = (x * 100).toFixed(1);
  return x > 0.0005 ? `+${c}¢` : x < -0.0005 ? `−${c.replace("-", "")}¢` : "0.0¢";
};

/** Compact axis labels: $0, $500, $1K, −$2.5K. */
export const axisMoney = (x: number, step?: number) => {
  const a = Math.abs(x);
  // Thousands get a K, unless the ticks are close together ($7,996 / $7,998, not $8K / $8K)
  const close = step != null && step < 100;
  const body = a >= 1000 && !close ? `$${+(a / 1000).toFixed(1)}K`
    : `$${a.toLocaleString("en-US", { maximumFractionDigits: step != null && step < 1 ? 2 : a < 10 ? 2 : 0 })}`;
  return x < 0 ? `−${body}` : body;
};

/** Full dollars and cents for headline numbers: $13,982.40, or signed +$206.03 / −$198.11. */
export const dollars = (x: number | null | undefined, signed = false) => {
  if (x == null || Number.isNaN(x)) return "–";
  const body = `$${Math.abs(x).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (!signed) return x < 0 ? `−${body}` : body;
  return x > 0.004 ? `+${body}` : x < -0.004 ? `−${body}` : body;
};
