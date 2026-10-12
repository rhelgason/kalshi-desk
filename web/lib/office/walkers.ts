/**
 * Full-body office sprites (14x22 drawn, 16x24 with the outline), built from
 * the same looks as the portraits (lib/sprites.ts). Three views: facing down,
 * up, and side (left is the side view mirrored), and a two-step walk cycle.
 *
 * Templates use one letter per pixel ("." is transparent). Shading and the
 * black outline are added automatically in spriteCanvas(), so every
 * character gets the same light-from-the-top-left look.
 */

import { LOOKS, type Look } from "@/lib/sprites";

export type Dir = "down" | "up" | "side";
export type Step = 0 | 1 | 2; // standing, left foot, right foot

const W = 14;

// Heads: rows 0-9. Faces use E for eyes and M for the mouth.
type HeadSet = Record<Dir, string[]>;

const BASE: HeadSet = {
  down: [
    "....HHHHHH....",
    "...HHHHHHHH...",
    "..HHHHHHHHHH..",
    "..HHHHHHHHHH..",
    "..HSSSSSSSSH..",
    "..SSESSSSESS..",
    "..SSESSSSESS..",
    "..SSSSSSSSSS..",
    "...SSSMMSSS...",
    ".....SSSS.....",
  ],
  up: [
    "....HHHHHH....",
    "...HHHHHHHH...",
    "..HHHHHHHHHH..",
    "..HHHHHHHHHH..",
    "..HHHHHHHHHH..",
    "..HHHHHHHHHH..",
    "..HHHHHHHHHH..",
    "..SHHHHHHHHS..",
    "...SSSSSSSS...",
    ".....SSSS.....",
  ],
  side: [
    "....HHHHH.....",
    "...HHHHHHHH...",
    "..HHHHHHHHHH..",
    "..HHHHHHHHHH..",
    "..HHHSSSSSSS..",
    "..HHSSSSSESS..",
    "..HHSSSSSESSS.",
    "..HHSSSSSSSS..",
    "...SSSSSSMS...",
    ".....SSSS.....",
  ],
};

/** Per-style changes to the top of the head (row index -> row). */
const STYLE: Record<Look["hairStyle"], Partial<Record<Dir, Record<number, string>>>> = {
  short: {},
  slick: {
    down: { 0: "...HHHHHHHH...", 1: "..HHHHHHHHHH..", 2: "..HHHHHHHHHHH." },
    side: { 0: "..HHHHHHHH....", 1: "..HHHHHHHHHH..", 2: "..HHHHHHHHHHH." },
  },
  long: {
    down: { 4: ".HHSSSSSSSSHH.", 5: ".HSSESSSSESSH.", 6: ".HSSESSSSESSH.", 7: ".HSSSSSSSSSSH.", 8: ".HH.SSMMSS.HH.", 9: ".HH..SSSS..HH." },
    up: { 7: ".HHHHHHHHHHHH.", 8: ".HHHHHHHHHHHH.", 9: "..HHHHHHHHHH.." },
    side: { 4: ".HHHHSSSSSSS..", 5: ".HHHSSSSSESS..", 6: ".HHHSSSSSESSS.", 7: ".HHHSSSSSSSS..", 8: ".HH.SSSSSSMS..", 9: ".HH..SSSS....." },
  },
  ponytail: {
    down: { 1: "...HHHHHHHH.HH", 2: "..HHHHHHHHHHHH", 3: "..HHHHHHHHHH.H" },
    up: { 7: "..SHHHHHHHHS..", 8: "...SSSHHSSS...", 9: ".....SHHS....." },
    side: { 2: "HHHHHHHHHHHH..", 3: "HHHHHHHHHHHH..", 4: "HH.HHSSSSSSS.." },
  },
  bald: {
    down: { 0: "..............", 1: "....SSSSSS....", 2: "...SSSSSSSS...", 3: "..SSSSSSSSSS..", 4: "..HSSSSSSSSH.." },
    up: { 0: "..............", 1: "....SSSSSS....", 2: "...SSSSSSSS...", 3: "..SSSSSSSSSS..", 4: "..SSSSSSSSSS..", 5: "..HSSSSSSSSH..", 6: "..HHHHHHHHHH.." },
    side: { 0: "..............", 1: "....SSSSS.....", 2: "...SSSSSSSS...", 3: "..SSSSSSSSSS..", 4: "..HSSSSSSSSS.." },
  },
  afro: {
    down: { 0: "...HHHHHHHH...", 1: "..HHHHHHHHHH..", 2: ".HHHHHHHHHHHH.", 3: ".HHHHHHHHHHHH.", 4: ".HHSSSSSSSSHH." },
    up: { 0: "...HHHHHHHH...", 1: "..HHHHHHHHHH..", 2: ".HHHHHHHHHHHH.", 3: ".HHHHHHHHHHHH.", 4: ".HHHHHHHHHHHH.", 5: ".HHHHHHHHHHHH." },
    side: { 0: "...HHHHHHH....", 1: "..HHHHHHHHHH..", 2: ".HHHHHHHHHHH..", 3: ".HHHHHHHHHHH..", 4: ".HHHHSSSSSSS.." },
  },
  cap: {
    down: { 0: "....AAAAAA....", 1: "...AAAAAAAA...", 2: "..AAAAAAAAAA..", 3: ".KKKKKKKKKKKK." },
    up: { 0: "....AAAAAA....", 1: "...AAAAAAAA...", 2: "..AAAAAAAAAA..", 3: "..AAAAAAAAAA.." },
    side: { 0: "....AAAAA.....", 1: "...AAAAAAAA...", 2: "..AAAAAAAAAA..", 3: "..AAAAAAAAKKKK" },
  },
  captain: {
    down: { 0: "...AAAAAAAA...", 1: "..AAAAWWAAAA..", 2: "..AAAAAAAAAA..", 3: ".KKKKKKKKKKKK." },
    up: { 0: "...AAAAAAAA...", 1: "..AAAAAAAAAA..", 2: "..AAAAAAAAAA..", 3: "..KKKKKKKKKK.." },
    side: { 0: "...AAAAAAA....", 1: "..AAAAAAWAA...", 2: "..AAAAAAAAAA..", 3: "..KKKKKKKKKKK." },
  },
  visor: {
    down: { 3: ".AAAAAAAAAAAA." },
    up: { 3: "..AAAAAAAAAA.." },
    side: { 3: "..HHAAAAAAAAAA" },
  },
};

// Bodies: rows 10-16
const BODY: Record<Dir, string[]> = {
  down: [
    "...CCCWWCCC...",
    "..CCCCWTTCCC..",
    ".CCCCCCTTCCCC.",
    ".CCCCCCTTCCCC.",
    ".CCCCCCTTCCCC.",
    ".S.CCCCCCCC.S.",
    "...BBBBBBBB...",
  ],
  up: [
    "...CCCCCCCC...",
    "..CCCCCCCCCC..",
    ".CCCCCCCCCCCC.",
    ".CCCCCCCCCCCC.",
    ".CCCCCCCCCCCC.",
    ".S.CCCCCCCC.S.",
    "...BBBBBBBB...",
  ],
  side: [
    ".....CCCCC....",
    "....CCCCCCC...",
    "....CCCCCCC...",
    "....CCCSCCC...",
    "....CCCSCCC...",
    "....CCCCCCC...",
    "....BBBBBBB...",
  ],
};
const OPEN_COLLAR = ["...CCCSSCCC...", "..CCCCSSCCCC..", ".CCCCCCCCCCCC.", ".CCCCCCCCCCCC.", ".CCCCCCCCCCCC."];

// Legs: rows 17-21, per step
const LEGS: Record<Dir, string[][]> = {
  down: [
    ["...PPPPPPPP...", "...PPP..PPP...", "...PPP..PPP...", "...PPP..PPP...", "...QQQ..QQQ..."],
    ["...PPPPPPPP...", "...PPP..PPP...", "...PPP..PPP...", "...PPP..QQQ...", "...QQQ........"],
    ["...PPPPPPPP...", "...PPP..PPP...", "...PPP..PPP...", "...QQQ..PPP...", "........QQQ..."],
  ],
  side: [
    ["....PPPPPPP...", ".....PPPPP....", ".....PPPPP....", ".....PP.PP....", ".....QQQQQQ..."],
    ["....PPPPPPP...", "....PPP.PPP...", "...PPP...PPP..", "...PP.....PP..", "..QQQ.....QQQ."],
    ["....PPPPPPP...", ".....PPPPP....", ".....PPPP.....", "......PPP.....", "......QQQQ...."],
  ],
  up: [],
};
LEGS.up = LEGS.down;

// Dart Monkey Dan: fur (B), face (t), a red dart (R) stuck in his head, and a tail
const MONKEY: HeadSet = {
  down: [
    "....BBBBBB..R.",
    "...BBBBBBBBR..",
    "..BBBBBBBBBB..",
    "BBBBttttttBBBB",
    "BtBtttttttttBtB".slice(0, 14),
    "BBtEtttttEttBB",
    "..tEtttttEtt..",
    "..tttKKKKttt..",
    "...ttttttttt..",
    ".....BBBB.....",
  ],
  up: [
    "....BBBBBB..R.",
    "...BBBBBBBBR..",
    "..BBBBBBBBBB..",
    "BBBBBBBBBBBBBB",
    "BtBBBBBBBBBBtB",
    "BBBBBBBBBBBBBB",
    "..BBBBBBBBBB..",
    "..BBBBBBBBBB..",
    "...BBBBBBBB...",
    ".....BBBB.....",
  ],
  side: [
    "....BBBBB...R.",
    "...BBBBBBBBR..",
    "..BBBBBBBBBB..",
    "..BBBBtttttt..",
    ".BtBBttttEtt..",
    "..BBBtttttttt.",
    "..BBBttttttKt.",
    "...BBtttttt...",
    "....BtttttK...",
    ".....BBBB.....",
  ],
};

const fit = (r: string) => r.slice(0, W).padEnd(W, ".");

export type Grid = { rows: string[]; palette: Record<string, string> };

/** One frame of someone standing or walking in a direction. */
export function walker(look: Look | "monkey", dir: Dir, step: Step, opts: { sleepy?: boolean } = {}): Grid {
  let head: string[];
  let palette: Record<string, string>;
  if (look === "monkey") {
    head = [...MONKEY[dir]];
    palette = {
      B: "#5a3a1e", t: "#e8c39e", K: "#1a1a1a", E: "#1a1a1a", R: "#e03c3c", C: "#4a5568", W: "#ffffff",
      T: "#e03c3c", S: "#e8c39e", P: "#2d3142", Q: "#111111",
    };
  } else {
    head = [...BASE[dir]];
    for (const [i, row] of Object.entries(STYLE[look.hairStyle][dir] ?? {})) head[Number(i)] = row;
    palette = {
      H: look.hair, S: look.skin, K: "#1a1a1a", E: "#1a1a1a", G: "#d7e3ea", M: "#8a3b3b", W: "#ffffff",
      C: look.shirt, T: look.tie ?? look.shirt, A: look.hat ?? look.hair, D: "#2b2b2b",
      P: look.pants ?? "#2d3142", Q: "#151515", B: "#1d1d26",
    };
    const put = (r: number, c: number, v: string) => (head[r] = head[r].slice(0, c) + v + head[r].slice(c + v.length));
    if (dir === "down") {
      if (look.eyes === "glasses") { put(5, 3, "GEGG"); put(5, 8, "GEGG"); put(6, 3, "GEGG"); put(6, 8, "GEGG"); put(5, 7, "G"); }
      if (look.eyes === "shades") { put(5, 3, "KKKKKKKKK"); put(6, 3, "KKK"); put(6, 8, "KKKK"); }
      if (look.mouth === "grin") put(8, 4, "SMMMMS");
      if (look.mouth === "frown") put(8, 4, "SMSSMS");
      if (look.beard) { put(7, 2, "HSSSSSSSSH"); put(8, 2, "HHHMMMMHHH"); put(9, 3, "HHHHHHHH"); }
      if (look.headset) { put(4, 1, "D"); put(5, 1, "D"); put(6, 1, "D"); put(7, 2, "DD"); put(8, 3, "D"); }
    }
    if (dir === "side") {
      if (look.eyes === "glasses") put(5, 7, "GGEG");
      if (look.eyes === "shades") put(5, 7, "KKKKK");
      if (look.beard) { put(7, 4, "HHHHHHHH"); put(8, 4, "HHHHHMH"); }
      if (look.headset) { put(4, 4, "D"); put(5, 4, "D"); put(6, 4, "DD"); }
    }
  }
  if (opts.sleepy) head = head.map((r) => r.replace(/E/g, look === "monkey" ? "t" : "S"));
  let body = [...BODY[dir]];
  if (look !== "monkey" && look.tie === null && dir === "down") body = [...OPEN_COLLAR, ...body.slice(5)];
  if (look === "monkey") body = body.map((r) => r.replace(/S/g, "t"));
  const legs = [...LEGS[dir][step]];
  if (look === "monkey" && dir !== "down") legs[1] = legs[1].slice(0, 11) + "BB" + legs[1].slice(13); // tail
  return { rows: [...head, ...body, ...legs].map(fit), palette };
}

/** Extra characters who wander in during events. */
export const NPCS: Record<string, Look> = {
  pizza: { skin: "#d9a77c", hair: "#222222", hairStyle: "cap", hat: "#e03c3c", shirt: "#e03c3c", tie: null, pants: "#1f2a44" },
  janitor: { skin: "#a86b45", hair: "#555555", hairStyle: "cap", hat: "#3f6fb5", shirt: "#3f6fb5", tie: null, pants: "#3f6fb5" },
  courier: { skin: "#f2d0b1", hair: "#7a4a22", hairStyle: "cap", hat: "#f5c542", shirt: "#8b5a2b", tie: null, pants: "#5d4037" },
  band: { skin: "#d9a77c", hair: "#222222", hairStyle: "captain", hat: "#c0392b", shirt: "#c0392b", tie: "#f5c542", pants: "#ffffff" },
  baker: { skin: "#f2d0b1", hair: "#ffffff", hairStyle: "captain", hat: "#ffffff", shirt: "#ffffff", tie: null, pants: "#cfd8dc" },
};

export function lookFor(key: string): Look | "monkey" {
  return LOOKS[key] ?? NPCS[key] ?? { skin: "#f2d0b1", hair: "#5a3a1e", hairStyle: "short", shirt: "#7f8c8d", tie: "#2f5aa8" };
}

const hex = (c: string) => {
  const n = parseInt(c.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};
const shade = ([r, g, b]: number[], k: number) =>
  k < 1 ? [r * k, g * k, b * k].map(Math.round) : [r + (255 - r) * (k - 1), g + (255 - g) * (k - 1), b + (255 - b) * (k - 1)].map(Math.round);

export const OUTLINE = [20, 16, 31];

/**
 * Render a grid with a 1px margin, light from the top left (darker right and
 * bottom edges, a highlight on top edges) and a dark outline all around.
 */
export function spriteCanvas(g: Grid): HTMLCanvasElement {
  const h = g.rows.length, w = g.rows[0].length;
  const c = document.createElement("canvas");
  c.width = w + 2;
  c.height = h + 2;
  const ctx = c.getContext("2d")!;
  const img = ctx.createImageData(w + 2, h + 2);
  const solid = (x: number, y: number) => y >= 0 && y < h && x >= 0 && x < w && g.rows[y][x] !== "." && !!g.palette[g.rows[y][x]];
  const set = (x: number, y: number, [r, gg, b]: number[]) => {
    const i = ((y + 1) * (w + 2) + (x + 1)) * 4;
    img.data[i] = r; img.data[i + 1] = gg; img.data[i + 2] = b; img.data[i + 3] = 255;
  };
  for (let y = -1; y <= h; y++) {
    for (let x = -1; x <= w; x++) {
      if (solid(x, y)) {
        let col = hex(g.palette[g.rows[y][x]]);
        if (!solid(x + 1, y) || !solid(x, y + 1)) col = shade(col, 0.72);
        else if (!solid(x, y - 1) || !solid(x - 1, y)) col = shade(col, 1.18);
        set(x, y, col);
      } else if (solid(x - 1, y) || solid(x + 1, y) || solid(x, y - 1) || solid(x, y + 1)) {
        set(x, y, OUTLINE);
      }
    }
  }
  ctx.putImageData(img, 0, 0);
  return c;
}
