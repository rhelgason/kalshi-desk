/**
 * Tiny 12x16 full-body sprites for the office floor, built from the same looks
 * as the portraits (lib/sprites.ts). Three views (facing down, up, and side;
 * left is the side view mirrored) and a two-step walk cycle.
 *
 * One letter per pixel, "." is transparent, like the portraits.
 */

import { LOOKS, type Look } from "@/lib/sprites";

export type Dir = "down" | "up" | "side";
export type Step = 0 | 1 | 2; // standing, left foot, right foot

type Head = Record<Dir, string[]>;

const HEADS: Record<Look["hairStyle"], Head> = {
  short: {
    down: ["....HHHH....", "..HHHHHHHH..", "..HHHHHHHH..", "..HSSSSSSH.."],
    up: ["....HHHH....", "..HHHHHHHH..", "..HHHHHHHH..", "..HHHHHHHH..", "..HHHHHHHH..", "..SHHHHHHS.."],
    side: ["...HHHHH....", "..HHHHHHH...", "..HHHHHHHH..", "..HHSSSSS..."],
  },
  slick: {
    down: ["...HHHHHH...", "..HHHHHHHHH.", "..HHHHHHHHH.", "..HSSSSSSH.."],
    up: ["...HHHHHH...", "..HHHHHHHH..", "..HHHHHHHH..", "..HHHHHHHH..", "..HHHHHHHH..", "..SHHHHHHS.."],
    side: ["..HHHHHHH...", "..HHHHHHHH..", "..HHHHHHHHH.", "..HHSSSSS..."],
  },
  long: {
    down: ["....HHHH....", "..HHHHHHHH..", ".HHHHHHHHHH.", ".HHSSSSSSHH."],
    up: ["....HHHH....", "..HHHHHHHH..", ".HHHHHHHHHH.", ".HHHHHHHHHH.", ".HHHHHHHHHH.", ".HHHHHHHHHH."],
    side: ["...HHHHH....", "..HHHHHHH...", ".HHHHHHHHH..", ".HHHSSSSS..."],
  },
  ponytail: {
    down: ["....HHHH....", "..HHHHHHHH.H", "..HHHHHHHHHH", "..HSSSSSSH.."],
    up: ["....HHHH....", "..HHHHHHHH..", "..HHHHHHHH..", "..HHHHHHHH..", "..HHHHHHHH..", "..SHHHHHHS.."],
    side: ["...HHHHH....", "..HHHHHHH...", "HHHHHHHHHH..", "HH.HSSSSS..."],
  },
  bald: {
    down: ["............", "...SSSSSS...", "..SSSSSSSS..", "..HSSSSSSH.."],
    up: ["............", "...SSSSSS...", "..SSSSSSSS..", "..SSSSSSSS..", "..HSSSSSSH..", "..SHHHHHHS.."],
    side: ["............", "...SSSSS....", "..SSSSSSS...", "..HSSSSSS..."],
  },
  afro: {
    down: ["..HHHHHHHH..", ".HHHHHHHHHH.", ".HHHHHHHHHH.", ".HHSSSSSSHH."],
    up: ["..HHHHHHHH..", ".HHHHHHHHHH.", ".HHHHHHHHHH.", ".HHHHHHHHHH.", ".HHHHHHHHHH.", "..SHHHHHHS.."],
    side: ["..HHHHHHH...", ".HHHHHHHHH..", ".HHHHHHHHH..", ".HHHSSSSS..."],
  },
  cap: {
    down: ["...AAAAAA...", "..AAAAAAAA..", ".AAAAAAAAAA.", "..HSSSSSSH.."],
    up: ["...AAAAAA...", "..AAAAAAAA..", "..AAAAAAAA..", "..HHHHHHHH..", "..HHHHHHHH..", "..SHHHHHHS.."],
    side: ["..AAAAAA....", "..AAAAAAA...", "..AAAAAAAAAA", "..HHSSSSS..."],
  },
  captain: {
    down: ["..AAAAAAAA..", "..AAAWWAAA..", ".KKKKKKKKKK.", "..HSSSSSSH.."],
    up: ["..AAAAAAAA..", "..AAAAAAAA..", "..KKKKKKKK..", "..HHHHHHHH..", "..HHHHHHHH..", "..SHHHHHHS.."],
    side: ["..AAAAAAA...", "..AAAAAWA...", "..KKKKKKKKK.", "..HHSSSSS..."],
  },
  visor: {
    down: ["....HHHH....", "..HHHHHHHH..", ".AAAAAAAAAA.", "..HSSSSSSH.."],
    up: ["....HHHH....", "..HHHHHHHH..", "..AAAAAAAA..", "..HHHHHHHH..", "..HHHHHHHH..", "..SHHHHHHS.."],
    side: ["...HHHHH....", "..HHHHHHH...", "..HAAAAAAAAA", "..HHSSSSS..."],
  },
};

const FACE_DOWN = ["..SESSSSES..", "..SSSSSSSS..", "...SSMMSS...", "....SSSS...."];
const FACE_SIDE = ["..HSSSSES...", "..HSSSSSSS..", "...SSSSMS...", "....SSSS...."];
const NECK_UP = ["...SSSSSS...", "....SSSS...."];

const BODY: Record<Dir, string[]> = {
  down: ["..CCCWWCCC..", ".CCCCTTCCCC.", ".CCCCTTCCCC.", ".SCCCCCCCCS."],
  up: ["..CCCCCCCC..", ".CCCCCCCCCC.", ".CCCCCCCCCC.", ".SCCCCCCCCS."],
  side: ["....CCCC....", "...CCCCCC...", "...CCCCCC...", "...CCSCCC..."],
};
const LEGS: Record<Dir, string[][]> = {
  down: [
    ["...PPPPPP...", "...PP..PP...", "...PP..PP...", "...QQ..QQ..."],
    ["...PPPPPP...", "...PP..PP...", "...PP..QQ...", "...QQ......."],
    ["...PPPPPP...", "...PP..PP...", "...QQ..PP...", ".......QQ..."],
  ],
  side: [
    ["....PPPP....", "....PPP.....", "....PPP.....", "....QQQQ...."],
    ["....PPPP....", "...PP.PP....", "..PP...PP...", "..QQ...QQQ.."],
    ["....PPPP....", "....PPP.....", "...PP.PP....", "...QQ.QQQ..."],
  ],
  up: [],
};
LEGS.up = LEGS.down;

const MONKEY_HEAD: Head = {
  down: ["...BBBBBB..R", "..BBBBBBBBR.", "..BBttttBB..", "BBBtEttEtBBB", "BtBttttttBtB", "..BttKKttB..", "..BBtttttB..", "...BBBBBB..."],
  up: ["...BBBBBB..R", "..BBBBBBBBR.", "..BBBBBBBB..", "BBBBBBBBBBBB", "BtBBBBBBBBtB", "..BBBBBBBB..", "..BBBBBBBB..", "...BBBBBB..."],
  side: ["...BBBBB...R", "..BBBBBBB.R.", "..BBBBtttt..", "..BBBttEtt..", ".BtBBtttttt.", "..BBBttttK..", "...BBtttt...", "....BBBB...."],
};

const pad = (r: string) => r.slice(0, 12).padEnd(12, ".");

export type Grid = { rows: string[]; palette: Record<string, string> };

/** One frame of an employee walking (or standing) in a direction. */
export function walker(look: Look | "monkey", dir: Dir, step: Step, opts: { sleepy?: boolean } = {}): Grid {
  let head: string[];
  let palette: Record<string, string>;
  if (look === "monkey") {
    head = [...MONKEY_HEAD[dir]];
    palette = { B: "#3b2412", t: "#e8c39e", K: "#1a1a1a", E: "#1a1a1a", R: "#e03c3c", C: "#4a5568", W: "#ffffff", T: "#e03c3c", S: "#3b2412", P: "#2d3142", Q: "#111111" };
  } else {
    const h = HEADS[look.hairStyle];
    head = dir === "down" ? [...h.down, ...FACE_DOWN] : dir === "up" ? [...h.up, ...NECK_UP] : [...h.side, ...FACE_SIDE];
    palette = {
      H: look.hair, S: look.skin, K: "#1a1a1a", E: "#1a1a1a", G: "#cfd8dc", M: "#7a2e2e", W: "#ffffff",
      C: look.shirt, T: look.tie ?? look.shirt, A: look.hat ?? look.hair, D: "#2b2b2b",
      P: look.pants ?? "#2d3142", Q: "#111111",
    };
    const put = (r: number, c: number, v: string) => (head[r] = head[r].slice(0, c) + v + head[r].slice(c + v.length));
    if (dir !== "up") {
      if (look.eyes === "glasses") dir === "down" ? put(4, 2, "GEGSSGEG") : put(4, 6, "GEG");
      if (look.eyes === "shades") dir === "down" ? put(4, 2, "KKKSSKKK") : put(4, 6, "KKK");
      if (look.mouth === "grin" && dir === "down") put(6, 3, "SMMMMS");
      if (look.beard) {
        if (dir === "down") { put(5, 2, "HSSSSSSH"); put(6, 2, "HHHMMHHH"); put(7, 3, "HHHHHH"); }
        else { put(6, 3, "HHHHMH"); put(7, 4, "HHHH"); }
      }
    }
    if (look.headset && dir !== "up") { put(3, 1, "D"); put(4, 1, "D"); put(5, 1, "DD"); }
  }
  if (opts.sleepy) head = head.map((r) => r.replace(/E/g, look === "monkey" ? "t" : "S"));
  let body = [...BODY[dir]];
  if (look !== "monkey" && look.tie === null && dir === "down") body = ["..CCCSSCCC..", ".CCCCCCCCCC.", ".CCCCCCCCCC.", ".SCCCCCCCCS."];
  if (look === "monkey") body = body.map((r) => r.replace(/S/g, "t"));
  const legs = [...LEGS[dir][step]];
  if (look === "monkey" && dir === "up") legs[1] = legs[1].slice(0, 10) + "B" + legs[1].slice(11); // a tail
  return { rows: [...head, ...body, ...legs].slice(0, 16).map(pad), palette };
}

/** Extra characters who wander in during events. */
export const NPCS: Record<string, Look> = {
  pizza: { skin: "#d9a77c", hair: "#222222", hairStyle: "cap", hat: "#e03c3c", shirt: "#e03c3c", tie: null, pants: "#1f2a44" },
  janitor: { skin: "#a86b45", hair: "#555555", hairStyle: "cap", hat: "#3f6fb5", shirt: "#3f6fb5", tie: null, pants: "#3f6fb5" },
  wolf: { skin: "#f2d0b1", hair: "#d8b25a", hairStyle: "slick", shirt: "#1d1d2b", tie: "#c0392b", pants: "#1d1d2b" },
  band: { skin: "#d9a77c", hair: "#222222", hairStyle: "captain", hat: "#c0392b", shirt: "#c0392b", tie: "#f5c542", pants: "#ffffff" },
};

export function lookFor(key: string): Look | "monkey" {
  return LOOKS[key] ?? NPCS[key] ?? { skin: "#f2d0b1", hair: "#5a3a1e", hairStyle: "short", shirt: "#7f8c8d", tie: "#2f5aa8" };
}

/** Render a grid to a little offscreen canvas (browser only). */
export function gridCanvas(g: Grid): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = g.rows[0].length;
  c.height = g.rows.length;
  const ctx = c.getContext("2d")!;
  g.rows.forEach((row, y) => {
    for (let x = 0; x < row.length; x++) {
      const col = g.palette[row[x]];
      if (row[x] !== "." && col) {
        ctx.fillStyle = col;
        ctx.fillRect(x, y, 1, 1);
      }
    }
  });
  return c;
}
