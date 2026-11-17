import type { Evidence } from "@/lib/types";

const SHORT: Record<Evidence["verdict_key"], string> = {
  too_early: "Too early to tell", luck: "Could be luck", probably_not: "Probably no edge", losing: "Reliably losing",
  promising: "Promising", fragile: "Real, but thin", strong: "Real skill",
};

/**
 * Skill or luck at a glance (11-16): a half-dial from "luck" to "skill" with a needle at how sure the stats are that
 * the employee's edge is real (desk/evidence: their record against what chance alone would do), the verdict in a
 * few words, and how many more bets it would take to be sure.
 */
export default function SkillGauge({ e }: { e?: Evidence }) {
  if (!e) return <div className="empty">No finished bets yet.</div>;
  const c = Math.max(0, Math.min(1, e.confidence));
  const r = 70, cx = 90, cy = 84;
  const at = (f: number) => [cx - r * Math.cos(Math.PI * f), cy - r * Math.sin(Math.PI * f)];
  const arc = (a: number, b: number) => {
    const [x1, y1] = at(a), [x2, y2] = at(b);
    return `M${x1},${y1} A${r},${r} 0 0 1 ${x2},${y2}`;
  };
  const [nx, ny] = at(c);
  const good = ["strong", "fragile", "promising"].includes(e.verdict_key);
  const bad = ["losing", "probably_not"].includes(e.verdict_key);
  const more = e.bets_needed && e.bets_needed > e.bets && e.edge > 0 ? e.bets_needed - e.bets : null;
  return (
    <div className="skill-gauge">
      <svg viewBox="0 0 180 100" role="img" aria-label={`${Math.round(c * 100)}% sure it's skill, not luck`}>
        <path d={arc(0, 1)} stroke="var(--grid)" strokeWidth={14} fill="none" strokeLinecap="round" />
        <path d={arc(0, 0.5)} stroke="color-mix(in srgb, var(--text-muted) 35%, transparent)" strokeWidth={14} fill="none" strokeLinecap="round" />
        <path d={arc(0.5, 0.95)} stroke="color-mix(in srgb, var(--up) 45%, transparent)" strokeWidth={14} fill="none" />
        <path d={arc(0.95, 1)} stroke="var(--up)" strokeWidth={14} fill="none" strokeLinecap="round" />
        <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="var(--text-primary)" strokeWidth={3} strokeLinecap="round" />
        <circle cx={cx} cy={cy} r={6} fill="var(--text-primary)" />
        <text x={cx - r} y={cy + 14} textAnchor="middle" fontSize={10} fill="var(--text-muted)">luck</text>
        <text x={cx + r} y={cy + 14} textAnchor="middle" fontSize={10} fill="var(--text-muted)">skill</text>
      </svg>
      <div className={`skill-verdict ${good ? "up" : bad ? "down" : ""}`}>{SHORT[e.verdict_key]}</div>
      <div className="muted small">
        {Math.round(c * 100)}% sure it&apos;s skill · {e.bets} bets{more ? ` · ~${more.toLocaleString()} more to be sure` : ""}
      </div>
    </div>
  );
}
