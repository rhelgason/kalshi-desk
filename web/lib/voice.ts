import type { Employee } from "./types";

type Lines = { up: string; down: string; idle: string };

/** How each employee would describe their day, in their own words. */
const LINES: Record<string, Lines> = {
  sniper: { up: "Patience pays.", down: "Missed one. It happens.", idle: "Waiting for the shot." },
  nickel_picker: { up: "Another nickel.", down: "The steamroller got me.", idle: "No sure things yet." },
  longshot_fade: { up: "Long shots never hit. Told you.", down: "One actually hit. Ugh.", idle: "Nothing silly to bet against." },
  breakout: { up: "Ride the wave!", down: "Wiped out. Paddling back.", idle: "Waiting for bitcoin to make a move." },
  early_favorite: { up: "Early bird gets the worm.", down: "Picked the wrong horse.", idle: "Waiting for the next window to open." },
  longshot_buy: { up: "It only has to hit once!", down: "The next one's the one.", idle: "Looking for lottery tickets." },
  dart_monkey: { up: "Ook! 🍌", down: "Ook…", idle: "Ook?" },
};
const DEFAULT: Lines = { up: "Up and to the right.", down: "Rough patch.", idle: "Waiting." };

/** One line, in character, about how it's going. */
export function quip(e: Employee): string {
  if (e.status === "fired") return "Packing up my desk.";
  if (e.status === "suspended") return "Riding the bench.";
  const l = LINES[e.key] ?? DEFAULT;
  const pnl = e.pnl ?? 0;
  if (!(e.fills ?? 0) && Math.abs(pnl) < 0.005) return l.idle;
  return pnl >= 0 ? l.up : l.down;
}

/** What each employee actually does, in plain words, for their page. */
export const HOW_THEY_BET: Record<string, string> = {
  sniper: "Waits until the last few minutes of each 15-minute window and only bets when bitcoin is so far from the line that the answer is nearly certain. Rare bets, mostly small wins.",
  nickel_picker: "Buys whichever side is already a heavy favorite (88–95¢) with at least 10 minutes to go. Wins most bets for a few cents each, but one upset can wipe out a dozen wins.",
  longshot_fade: "Bets against long shots: when one side costs only 5–15¢, Bill buys the other side. Like Nick, he wins small and often, and loses big on the occasional surprise.",
  breakout: "When bitcoin has jumped or dropped sharply in the last 15 minutes, Betty bets it keeps going, but only if Kalshi's price hasn't caught up yet (still under 60¢).",
  early_favorite: "Right after a new 15-minute window opens, Edie buys the side that's a clear but not certain favorite (75–85¢), betting the early price is a little too cautious.",
  longshot_buy: "Buys the cheap long shots Bill bets against. He's a yardstick: if Bill can't beat Lenny, Bill's idea doesn't work.",
  dart_monkey: "Bets at random. He's the yardstick everyone has to beat: if a strategy can't do better than a monkey with darts, it isn't really a strategy.",
};
