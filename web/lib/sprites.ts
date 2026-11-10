/**
 * 8-bit employee portraits: 16x16 pixel grids built from a few parts (hair,
 * face, eyewear, outfit) so each employee gets a distinct look without
 * hand-drawing fourteen sprites. One letter per pixel, "." is transparent.
 */

import { PORTRAITS } from "./portraits";

export type Sprite = { rows: string[]; palette: Record<string, string> };

export type Look = {
  skin: string;
  hair: string;
  hairStyle: "short" | "long" | "bald" | "cap" | "afro" | "slick" | "ponytail" | "captain" | "visor";
  hat?: string; // cap / captain hat / visor colour
  eyes?: "plain" | "glasses" | "shades";
  mouth?: "smile" | "flat" | "frown" | "grin";
  beard?: boolean;
  shirt: string;
  tie?: string | null; // null = open collar
  headset?: boolean;
  pants?: string; // for the walking sprites in the office
};

const HEADS: Record<Look["hairStyle"], string[]> = {
  short: [
    "................",
    ".....HHHHHH.....",
    "....HHHHHHHH....",
    "....HSSSSSSH....",
  ],
  slick: [
    "................",
    "....HHHHHHHH....",
    "....HHHHHHHHH...",
    "....HSSSSSSH....",
  ],
  long: [
    "................",
    ".....HHHHHH.....",
    "....HHHHHHHH....",
    "...HHSSSSSSHH...",
  ],
  ponytail: [
    "................",
    ".....HHHHHH..HH.",
    "....HHHHHHHHHH..",
    "....HSSSSSSH....",
  ],
  bald: [
    "................",
    "................",
    ".....SSSSSS.....",
    "....HSSSSSSH....",
  ],
  afro: [
    "....HHHHHHHH....",
    "...HHHHHHHHHH...",
    "...HHHHHHHHHH...",
    "...HHSSSSSSHH...",
  ],
  cap: [
    ".....AAAAAA.....",
    "....AAAAAAAA....",
    "....AAAAAAAAAA..",
    "....HSSSSSSH....",
  ],
  captain: [
    "....AAAAAAAA....",
    "...AAAAWWAAAA...",
    "...KKKKKKKKKK...",
    "....HSSSSSSH....",
  ],
  visor: [
    "................",
    ".....HHHHHH.....",
    "...AAAAAAAAAA...",
    "....HSSSSSSH....",
  ],
};

const EYES = {
  plain: "....SKSSSSKS....",
  glasses: "....GKGGGGKG....",
  shades: "....KKKSSKKK....",
};

const MOUTHS = {
  smile: ["....SSMSSMSS....", ".....SSMMSS....."],
  grin: ["....SSMMMMSS....", ".....SSSSSS....."],
  flat: ["....SSSSSSSS....", ".....SSMMSS....."],
  frown: ["....SSSMMSSS....", ".....SMSSMS....."],
};

function person(l: Look): Sprite {
  const open = l.tie === null;
  const rows = [
    ...HEADS[l.hairStyle],
    l.hairStyle === "long" ? "...HSSSSSSSSH..." : "....SSSSSSSS....",
    EYES[l.eyes ?? "plain"],
    l.hairStyle === "long" ? "...HSSSSSSSSH..." : "....SSSSSSSS....",
    ...MOUTHS[l.mouth ?? "smile"],
    "......SSSS......",
    "...CCCWSSWCCC...",
    open ? "..CCCCCSSCCCCC.." : "..CCCCWTTWCCCC..",
    open ? "..CCCCCCCCCCCC.." : "..CCCCCTTCCCCC..",
    open ? "..CCCCCCCCCCCC.." : "..CCCCCCTCCCCC..",
    "..CCCCCCCCCCCC..",
    "..CCCCCCCCCCCC..",
  ];
  if (l.beard) {
    rows[7] = "....HSSSSSSH....";
    rows[8] = "....HHMMMMHH....";
    rows[9] = ".....HHHHHH.....";
  }
  const put = (r: number, c: number, v: string) => (rows[r] = rows[r].slice(0, c) + v + rows[r].slice(c + v.length));
  if (l.headset) {
    put(4, 3, "D");
    put(5, 3, "D");
    put(6, 3, "D");
    put(7, 4, "DD");
  }
  const fixed = rows.slice(0, 16).map((r) => r.slice(0, 16).padEnd(16, "."));
  return {
    rows: fixed,
    palette: {
      H: l.hair, S: l.skin, K: "#1a1a1a", G: "#cfd8dc", M: "#7a2e2e", W: "#ffffff",
      C: l.shirt, T: l.tie ?? l.shirt, A: l.hat ?? l.hair, D: "#2b2b2b",
    },
  };
}

const MONKEY: Sprite = {
  rows: [
    "..............rr",
    "....BBBBBBBB.gr.",
    "...BbbbbbbbgB...",
    "..BbbbbbbbbbbB..",
    "..BbbbbbbbbbbB..",
    ".BBbttbbbbttbBB.",
    "BtBbtwkbbwktbBtB",
    "BtBbtkkttkktbBtB",
    ".BBbttttttttbBB.",
    "..BtttkttktttB..",
    "..BttkttttkttB..",
    "...BtttkkkkttB..",
    "....BBBttBBB....",
    "...CCCCWWCCCC...",
    "..CCCCCTTCCCCC..",
    "..CCCCCTTCCCCC..",
  ],
  palette: { B: "#3b2412", b: "#8b5a2b", t: "#e8c39e", k: "#1a1a1a", w: "#ffffff", r: "#e03c3c", g: "#9a9a9a", C: "#4a5568", W: "#ffffff", T: "#e03c3c" },
};

const SKIN = { light: "#f2d0b1", tan: "#d9a77c", brown: "#a86b45", dark: "#6b4226" };

/** Each employee's look, shared by the portraits and the office's walking sprites. */
export const LOOKS: Record<string, Look | "monkey"> = {
  cover_arb: { skin: SKIN.light, hair: "#5a3a1e", hairStyle: "short", eyes: "glasses", shirt: "#2f5aa8", tie: "#c0392b" },
  bucket_arb: { skin: SKIN.light, hair: "#c0471f", hairStyle: "long", shirt: "#7b3fa0", tie: null, mouth: "grin" },
  fair_value: { skin: SKIN.tan, hair: "#b8b8b8", hairStyle: "bald", eyes: "glasses", shirt: "#7a5230", tie: "#2e7d32", mouth: "flat" },
  vol_arb: { skin: SKIN.light, hair: "#111111", hairStyle: "slick", eyes: "shades", shirt: "#222631", tie: "#f5c542" },
  sniper: { skin: SKIN.brown, hair: "#222222", hairStyle: "cap", hat: "#56732f", shirt: "#56732f", tie: null, mouth: "flat", pants: "#36461f" },
  momentum: { skin: SKIN.tan, hair: "#f2c94c", hairStyle: "long", shirt: "#f2994a", tie: null, mouth: "grin" },
  mean_revert: { skin: SKIN.dark, hair: "#2b1a10", hairStyle: "afro", shirt: "#1abc9c", tie: null },
  longshot_fade: { skin: SKIN.light, hair: "#6b6b6b", hairStyle: "bald", shirt: "#3f5d8a", tie: null, mouth: "frown" },
  longshot_buy: { skin: SKIN.tan, hair: "#3b2412", hairStyle: "cap", hat: "#d63031", shirt: "#f39c12", tie: null, mouth: "grin" },
  nickel_picker: { skin: SKIN.light, hair: "#c8c8c8", hairStyle: "visor", hat: "#1f7a4d", eyes: "glasses", shirt: "#6d4c2f", tie: "#c0392b", mouth: "flat" },
  heavy_favorite: { skin: SKIN.tan, hair: "#2b1a10", hairStyle: "long", shirt: "#2a9d8f", tie: null, mouth: "smile" },
  heavy_maker: { skin: SKIN.tan, hair: "#2b1a10", hairStyle: "long", shirt: "#6b8e4e", tie: null, mouth: "smile" },
  maker_btc: { skin: SKIN.tan, hair: "#e0a630", hairStyle: "long", shirt: "#f2c230", tie: null, mouth: "smile" },
  maker_eth: { skin: SKIN.tan, hair: "#e6e6ef", hairStyle: "long", shirt: "#b3a6e6", tie: null, mouth: "smile" },
  maker_sol: { skin: SKIN.tan, hair: "#b5532a", hairStyle: "long", eyes: "shades", shirt: "#f5d042", tie: null, mouth: "grin" },
  maker_xrp: { skin: SKIN.tan, hair: "#1b2a3a", hairStyle: "long", shirt: "#2e86c1", tie: null, mouth: "smile" },
  maker_doge: { skin: SKIN.tan, hair: "#d9822b", hairStyle: "long", shirt: "#efe3c8", tie: null, mouth: "grin" },
  maker_hype: { skin: SKIN.light, hair: "#ff4fa3", hairStyle: "ponytail", shirt: "#7ddc3a", tie: null, mouth: "grin" },
  maker_bnb: { skin: SKIN.light, hair: "#16130f", hairStyle: "short", shirt: "#2b2b2b", tie: "#f3ba2f", mouth: "smile" },
  maker_near: { skin: SKIN.brown, hair: "#7a4a24", hairStyle: "long", shirt: "#2f6b4f", tie: null, mouth: "smile" },
  maker_zec: { skin: SKIN.tan, hair: "#ece6d2", hairStyle: "long", eyes: "shades", shirt: "#3a3a40", tie: null, mouth: "flat" },
  late_maker: { skin: SKIN.light, hair: "#3a3150", hairStyle: "short", eyes: "glasses", shirt: "#283a6b", tie: null, mouth: "smile" },
  runner_up_maker: { skin: SKIN.light, hair: "#7a5230", hairStyle: "bald", shirt: "#5c6670", tie: null, mouth: "flat" },
  weather_maker: { skin: SKIN.light, hair: "#a4482a", hairStyle: "cap", hat: "#f5c542", shirt: "#6fb3e0", tie: null, mouth: "smile" },
  hourly_btc: { skin: SKIN.light, hair: "#c0602a", hairStyle: "long", shirt: "#e8b130", tie: null, mouth: "smile" },
  maker_gold: { skin: SKIN.light, hair: "#1c1f2a", hairStyle: "short", shirt: "#f4f4f4", tie: "#e8b130", mouth: "smile" },
  maker_wti: { skin: SKIN.tan, hair: "#8a6248", hairStyle: "cap", hat: "#f5c542", shirt: "#3d4a5c", tie: null, mouth: "flat" },
  maker_silver: { skin: SKIN.light, hair: "#a9b1bb", hairStyle: "short", shirt: "#7a5c3e", tie: "#d63031", mouth: "smile" },
  sports_closer: { skin: SKIN.tan, hair: "#1f1410", hairStyle: "ponytail", shirt: "#20242c", tie: null, mouth: "grin", pants: "#20242c" },
  favorite_sports: { skin: SKIN.brown, hair: "#f2d16b", hairStyle: "ponytail", shirt: "#c0392b", tie: null, mouth: "grin" },
  market_maker: { skin: SKIN.tan, hair: "#4a2c17", hairStyle: "short", headset: true, shirt: "#ecf0f1", tie: "#1f3a68" },
  whale_follow: { skin: SKIN.light, hair: "#eeeeee", hairStyle: "captain", hat: "#1f3a68", beard: true, shirt: "#1f3a68", tie: null },
  breakout: { skin: SKIN.light, hair: "#f0b542", hairStyle: "ponytail", eyes: "shades", shirt: "#20242c", tie: null, mouth: "grin", pants: "#20242c" },
  early_favorite: { skin: SKIN.brown, hair: "#e03c3c", hairStyle: "afro", shirt: "#f5c542", tie: null, mouth: "grin", pants: "#f5c542" },
  // the patient twins look like their siblings
  nickel_maker: { skin: SKIN.light, hair: "#c9ccd6", hairStyle: "afro", eyes: "glasses", shirt: "#e78fb3", tie: null, mouth: "smile" },
  early_maker: { skin: SKIN.brown, hair: "#3b2412", hairStyle: "short", eyes: "glasses", shirt: "#9b8fd0", tie: null, mouth: "smile", pants: "#5d4037" },
  breakout_maker: { skin: SKIN.light, hair: "#e8a33d", hairStyle: "cap", hat: "#e6c86e", shirt: "#16a085", tie: null, mouth: "smile", pants: "#16a085" },
  dart_monkey: "monkey",
};

/** Portraits: the hand-drawn 24x24 ones for current staff, part-built 16x16 faces for the rest (and Dan). */
export const SPRITES: Record<string, Sprite> = {
  ...Object.fromEntries(Object.entries(LOOKS).map(([k, l]) => [k, l === "monkey" ? MONKEY : person(l)])),
  ...PORTRAITS,
};

/** Runs of same-coloured pixels per row: far fewer SVG rects than one per pixel. */
export function spriteRects(s: Sprite): { x: number; y: number; w: number; fill: string }[] {
  const out: { x: number; y: number; w: number; fill: string }[] = [];
  s.rows.forEach((row, y) => {
    let x = 0;
    while (x < row.length) {
      const c = row[x];
      let end = x + 1;
      while (end < row.length && row[end] === c) end++;
      if (c !== "." && s.palette[c]) out.push({ x, y, w: end - x, fill: s.palette[c] });
      x = end;
    }
  });
  return out;
}
