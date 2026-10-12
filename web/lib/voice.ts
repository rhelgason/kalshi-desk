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
