import type { Employee, Evidence, Policy, Realism } from "./types";
import { money, pct } from "./format";

// Mirrors desk/paper/evidence.py: below this many settled bets it's always "too early"
const MIN_BETS = 30;

/** One plain-word status per employee, always an icon plus a label (never color alone). */
export type Light = {
  key: "good" | "wait" | "bad" | "benched" | "fired" | "idle" | "yardstick";
  icon: string;
  label: string;
};

export function light(e: Employee, ev?: Evidence): Light {
  if (e.status === "fired") return { key: "fired", icon: "✖️", label: "Fired" };
  if (e.status === "suspended") return { key: "benched", icon: "⏸️", label: "Benched" };
  if (!ev || ev.bets === 0) return { key: "idle", icon: "💤", label: "No bets yet" };
  if (e.control) return { key: "yardstick", icon: "📏", label: "Yardstick" };
  const pnl = e.pnl ?? 0;
  if ((ev.verdict_key === "losing" || ev.verdict_key === "probably_not") && pnl < 0)
    return { key: "bad", icon: "🔴", label: "Losing" };
  if (["strong", "fragile", "promising"].includes(ev.verdict_key) && pnl > 0)
    return { key: "good", icon: "🟢", label: "Doing well" };
  if (ev.verdict_key === "too_early") return { key: "wait", icon: "🟡", label: "Too early to tell" };
  return { key: "wait", icon: "🟡", label: "Could be luck" };
}

export type Advice = {
  /** act = you should do something; watch = worth knowing; relax = nothing to do */
  tone: "act" | "watch" | "relax";
  headline: string;
  why: string;
  action?: { kind: "suspend"; days: number } | { kind: "reinstate" };
};

const sure = (x: number) => `${Math.round(x * 100)}%`;
const shortDate = (iso: string) => new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });

function paceText(more: number, betsPerDay: number | null): string {
  if (!betsPerDay || betsPerDay <= 0) return "";
  const days = more / betsPerDay;
  return days < 1 ? " (less than a day at their pace)" : days < 60 ? ` (about ${Math.ceil(days)} days at their pace)` : " (months at their pace)";
}

function fillWarning(r?: Realism): string | null {
  if (!r) return null;
  if (r.verdict_key === "too_big") return "Their trades take a big share of what's for sale, so real trades would be smaller.";
  if (r.verdict_key === "slippy") return "Prices often move before their trades go through, so real results would likely be worse.";
  if (r.verdict_key === "maker") return "Their trades depend on guesses about waiting in line for a fill, so treat the results with caution.";
  return null;
}

/** What, if anything, the manager should do about an employee, in plain words. */
export function advise(e: Employee, ev: Evidence | undefined, r: Realism | undefined, policy: Policy,
                       betsPerDay: number | null = null): Advice {
  const pnl = e.pnl ?? 0;
  const given = e.starting_cash ?? 0;
  const lostOrMade = `${pnl >= 0 ? "made" : "lost"} ${money(Math.abs(pnl), false)} (${pct(Math.abs(e.roi ?? 0))} of their money)`;

  if (e.status === "fired") {
    return { tone: "relax", headline: "Fired. Nothing to do.", why: "They no longer trade. You can rehire them from their page." };
  }
  if (e.status === "suspended") {
    const until = e.suspended_until && !e.suspended_until.startsWith("9999") ? shortDate(e.suspended_until) : null;
    return {
      tone: "relax",
      headline: until ? `Benched until ${until}. Nothing to do.` : "Benched until you bring them back.",
      why: until ? "They come back automatically. You can bring them back early." : "They won't trade until you reinstate them.",
      action: { kind: "reinstate" },
    };
  }
  if (!ev || ev.bets === 0) {
    return {
      tone: "relax", headline: "Nothing to do yet.",
      why: "No finished bets this season. Some employees wait a long time for the right opportunity.",
    };
  }
  if (e.control) {
    return {
      tone: "relax", headline: "Nothing to do: this is a yardstick.",
      why: `Yardsticks follow a simple fixed rule so we can tell whether the others are actually clever. They're never promoted or benched. So far this rule has ${lostOrMade}; the real employees should beat it.`,
    };
  }

  const warn = fillWarning(r);
  const more = ev.bets_needed && ev.bets_needed > ev.bets ? ev.bets_needed - ev.bets : null;
  const moreText = more ? ` About ${more.toLocaleString()} more bets will tell${paceText(more, betsPerDay)}.` : "";

  switch (ev.verdict_key) {
    case "losing":
      if (pnl < 0) {
        return {
          tone: "act", headline: `Bench ${e.name}.`,
          why: `They've ${lostOrMade} over ${ev.bets} bets, and we're ${sure(1 - ev.confidence)} sure it isn't just bad luck.`,
          action: { kind: "suspend", days: policy.suspend_days },
        };
      }
      break;
    case "probably_not":
      if (pnl < 0 && (e.roi ?? 0) <= -0.1) {
        return {
          tone: "act", headline: `Consider benching ${e.name}.`,
          why: `They've ${lostOrMade}, and there's only a ${sure(ev.confidence)} chance they have real skill.`,
          action: { kind: "suspend", days: policy.suspend_days },
        };
      }
      return {
        tone: "watch", headline: "Keep an eye on them.",
        why: `They've ${lostOrMade}, and there's only a ${sure(ev.confidence)} chance they have real skill. The weekly review demotes them automatically if this continues.`,
      };
    case "too_early": {
      const left = MIN_BETS - ev.bets;
      return {
        tone: "relax", headline: "Nothing to do yet: too early to tell.",
        why: `${ev.bets} finished bets so far; we need at least ${MIN_BETS} before judging. ${left} to go${paceText(left, betsPerDay)}.`,
      };
    }
    case "luck":
      return {
        tone: "relax", headline: "Wait and see.",
        why: `They've ${lostOrMade}, but that could easily be luck (${sure(ev.confidence)} sure it's skill).${moreText}`,
      };
    case "promising":
      return {
        tone: warn ? "watch" : "relax", headline: "Keep going: looking good.",
        why: `They've ${lostOrMade}, and we're ${sure(ev.confidence)} sure it's skill.${moreText}${warn ? ` One worry: ${warn}` : ""}`,
      };
    case "fragile":
      return {
        tone: "watch", headline: "Doing well, but the margin is thin.",
        why: `Real skill (${sure(ev.confidence)} sure), but if every trade cost just 1¢ more, their ${money(ev.pnl)} would be ${money(ev.pnl_1c)}.${warn ? ` Also: ${warn}` : ""}`,
      };
    case "strong":
      if (warn) {
        return { tone: "watch", headline: "Looks great on paper, but double-check.", why: `${sure(ev.confidence)} sure it's skill. However: ${warn}` };
      }
      return {
        tone: "relax", headline: "Doing great. Nothing to do.",
        why: `They've ${lostOrMade} over ${ev.bets} bets, and we're ${sure(ev.confidence)} sure it's real skill. The weekly review will reward them.`,
      };
  }
  return {
    tone: "relax", headline: "Nothing to do.",
    why: `They've ${lostOrMade} on ${money(given, false)}.`,
  };
}

/** Bets per day so far this season, for "about N days" estimates. */
export const betsPerDay = (bets: number, seasonStart: number | null) =>
  seasonStart ? bets / Math.max(0.25, (Date.now() - seasonStart) / 86_400_000) : null;
