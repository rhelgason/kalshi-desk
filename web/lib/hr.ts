import type { Policy } from "./types";

// Mirrors desk/hr.py so the website can show and edit the same rules.
export const LEVELS = [
  { title: "Intern", multiplier: 0.5 },
  { title: "Associate", multiplier: 1 },
  { title: "Senior", multiplier: 1.5 },
  { title: "VP", multiplier: 2 },
  { title: "Partner", multiplier: 3 },
];

export const DEFAULT_POLICY: Policy = {
  season: 1,
  review_days: 7,
  min_settled: 20,
  promote_roi: 0.02,
  demote_roi: -0.03,
  strikes_to_suspend: 2,
  suspend_days: 7,
  max_drawdown_suspend: 0.3,
  auto_fire: false,
  strikes_to_fire: 4,
  award_bonus: 250,
  reserve: 5000,
  last_review: null,
  promote_min_confidence: 0.8,
  realism: { depth: 100, samples: 0, measured_at: null },
  autotune: {
    enabled: true,
    every_hours: 24,
    lookback_days: 45,
    min_test_bets: 30,
    min_improvement: 10,
    min_confidence: 0.6,
    requested_at: null,
    last_run: null,
  },
};

export function mergePolicy(saved: Partial<Policy> | null): Policy {
  const p = structuredClone(DEFAULT_POLICY);
  if (!saved) return p;
  const { autotune, realism, ...rest } = saved;
  Object.assign(p, rest);
  if (autotune) Object.assign(p.autotune, autotune);
  if (realism) Object.assign(p.realism, realism);
  return p;
}

export const levelTitle = (level: number) => LEVELS[Math.max(0, Math.min(level, LEVELS.length - 1))].title;

export const awardName = (days: number) =>
  days >= 28 ? "Employee of the Month" : days >= 6 ? "Employee of the Week" : "Employee of the Day";
