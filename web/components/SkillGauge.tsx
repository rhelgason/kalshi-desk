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
      <svg viewBox="0 0 180 104" role="img" aria-label={`${Math.round(c * 100)}% sure it's skill, not luck`}>
        <defs>
          <linearGradient id="skill-arc" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0" stopColor="#9ca3af" />
            <stop offset="0.5" stopColor="#f59e0b" />
            <stop offset="1" style={{ stopColor: "var(--up)" }} />
          </linearGradient>
        </defs>
        <path d={arc(0, 1)} stroke="url(#skill-arc)" strokeWidth={14} fill="none" strokeLinecap="round" />
        <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="var(--text-primary)" strokeWidth={3} strokeLinecap="round" />
        <circle cx={cx} cy={cy} r={6} fill="var(--text-primary)" />
        <text x={cx - r} y={cy + 16} textAnchor="middle" fontSize={10} fill="var(--text-muted)">luck</text>
        <text x={cx + r} y={cy + 16} textAnchor="middle" fontSize={10} fill="var(--text-muted)">skill</text>
      </svg>
      <div className="skill-sure"><strong>{Math.round(c * 100)}%</strong> sure it&apos;s skill</div>
      <div className={`skill-verdict ${good ? "up" : bad ? "down" : ""}`}>{SHORT[e.verdict_key]}</div>
      <div className="muted small">{e.bets} bets{more ? ` · ~${more.toLocaleString()} more to be sure` : ""}</div>
    </div>
  );
}
