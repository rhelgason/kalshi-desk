import type { Employee, Evidence, Policy, Realism } from "./types";
import { money, shortName } from "./format";

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

const shortDate = (iso: string) => new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });

function paceText(more: number, betsPerDay: number | null): string {
  if (!betsPerDay || betsPerDay <= 0) return "";
  const days = more / betsPerDay;
  return days < 1 ? ", probably today" : days < 60 ? `, about ${Math.ceil(days)} day${Math.ceil(days) === 1 ? "" : "s"} at this pace` : ", which could take months";
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
  const who = shortName(e.name);
  const upDown = `${pnl >= 0 ? "Up" : "Down"} ${money(Math.abs(pnl), false)}`;

  if (e.status === "fired") {
    return { tone: "relax", headline: "Fired.", why: `${who} cleaned out the desk. You can rehire them below.` };
  }
  if (e.status === "suspended") {
    const until = e.suspended_until && !e.suspended_until.startsWith("9999") ? shortDate(e.suspended_until) : null;
    return {
      tone: "relax",
      headline: until ? `Benched until ${until}.` : "Benched.",
      why: until ? `${who} comes back on their own.` : `${who} sits until you say so.`,
      action: { kind: "reinstate" },
    };
  }
  if (!ev || ev.bets === 0) {
    return { tone: "relax", headline: "Nothing yet.", why: `${who} hasn't found a bet worth making. That's allowed.` };
  }
  if (e.control) {
    return {
      tone: "relax", headline: `${who} is the yardstick.`,
      why: `${upDown} with a dead-simple rule. Everyone else should beat that.`,
    };
  }

  const warn = fillWarning(r);
  const more = ev.bets_needed && ev.bets_needed > ev.bets ? ev.bets_needed - ev.bets : null;
  const moreText = more ? ` About ${more.toLocaleString()} more bets will tell${paceText(more, betsPerDay)}.` : "";

  switch (ev.verdict_key) {
    case "losing":
      if (pnl < 0) {
        return {
          tone: "act", headline: `Bench ${who}.`,
          why: `${upDown} over ${ev.bets} bets. That's not bad luck anymore.`,
          action: { kind: "suspend", days: policy.suspend_days },
        };
      }
      break;
    case "probably_not":
      if (pnl < 0 && (e.roi ?? 0) <= -0.1) {
        return {
          tone: "act", headline: `Think about benching ${who}.`,
          why: `${upDown}, and it's looking more like a bad idea than bad luck.`,
          action: { kind: "suspend", days: policy.suspend_days },
        };
      }
      return { tone: "watch", headline: `Keep an eye on ${who}.`, why: `${upDown}, and it doesn't look like skill so far.` };
    case "too_early": {
      const left = MIN_BETS - ev.bets;
      return { tone: "relax", headline: "Too early to tell.", why: `${ev.bets} bets in. Ask again in ${left} more${paceText(left, betsPerDay)}.` };
    }
    case "luck":
      return { tone: "relax", headline: "Wait and see.", why: `${upDown}, but a coin flip could do that.${moreText}` };
    case "promising":
      return {
        tone: warn ? "watch" : "relax", headline: "Looking good.",
        why: `${upDown}, and it's starting to look like real skill.${warn ? ` One worry: ${warn}` : ""}`,
      };
    case "fragile":
      return {
        tone: "watch", headline: "Winning, barely.",
        why: `${upDown}, but a penny worse per bet and it'd be ${money(ev.pnl_1c)}.${warn ? ` Also: ${warn}` : ""}`,
      };
    case "strong":
      if (warn) return { tone: "watch", headline: "Great on paper. Double-check.", why: warn };
      return { tone: "relax", headline: "Doing great.", why: `${upDown} over ${ev.bets} bets. That's skill, not luck.` };
  }
  return { tone: "relax", headline: "Nothing to do.", why: `${upDown}.` };
}

/** Bets per day so far this season, for "about N days" estimates. */
export const betsPerDay = (bets: number, seasonStart: number | null) =>
  seasonStart ? bets / Math.max(0.25, (Date.now() - seasonStart) / 86_400_000) : null;
