import type { Evidence } from "@/lib/types";

/** The needle in words: how sure the stats are that it's skill (a reliable loser is its own case). */
const say = (c: number, losing: boolean) =>
  losing ? "Reliably losing" : c >= 0.95 ? "Almost certainly skill" : c >= 0.8 ? "Probably skill" : c >= 0.6 ? "Leaning skill"
    : c >= 0.4 ? "Too close to call" : c >= 0.2 ? "Leaning luck" : "Probably luck";

/**
 * Skill or luck at a glance (11-16): a half-dial from "luck" to "skill" with a needle at how sure the stats are that
 * the employee's edge is real (desk/evidence: their record against what chance alone would do), that in a few words,
 * and how many bets it's judged on.
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
  const losing = e.verdict_key === "losing";
  return (
    <div className="skill-gauge">
      <svg viewBox="0 0 180 112" role="img" aria-label={`${Math.round(c * 100)}% sure it's skill, not luck`}>
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
        <text x={cx - r} y={cy + 24} textAnchor="middle" fontSize={10} fill="var(--text-muted)">luck</text>
        <text x={cx + r} y={cy + 24} textAnchor="middle" fontSize={10} fill="var(--text-muted)">skill</text>
      </svg>
      <div className={`skill-verdict ${losing ? "down" : c >= 0.8 ? "up" : ""}`}>{say(c, losing)} <span className="skill-pct">· {Math.round(c * 100)}% sure</span></div>
      <div className="muted small">assessed across {e.bets.toLocaleString()} bets</div>
    </div>
  );
}
