/**
 * Pixel art for the office, drawn with rectangles at native resolution
 * (512x288) and scaled up with nearest-neighbour by the page.
 *
 * The room is painted in three layers:
 *   floor   floors, rugs, the wall and windows
 *   objects furniture; gets a dark outline and a soft drop shadow automatically
 *   front   chair and couch backs, drawn over whoever is sitting in them
 * Everything that moves or changes (screens, people, the sky) is drawn live.
 */

import { COLS, DESKS, HEIGHT, ROWS, TILE, WALL, WIDTH } from "./map";

type Ctx = CanvasRenderingContext2D;

export const rect = (c: Ctx, x: number, y: number, w: number, h: number, color: string) => {
  c.fillStyle = color;
  c.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h));
};

const mix = (a: string, k: number) => {
  const n = parseInt(a.slice(1), 16);
  const ch = (s: number) => {
    const v = (n >> s) & 255;
    return Math.max(0, Math.min(255, Math.round(k < 1 ? v * k : v + (255 - v) * (k - 1))));
  };
  return `rgb(${ch(16)},${ch(8)},${ch(0)})`;
};

/** A box seen from slightly above: a lit top and a darker front face. */
export const block = (c: Ctx, x: number, y: number, w: number, h: number, color: string, front = 3) => {
  rect(c, x, y, w, h, color);
  rect(c, x, y, w, 1, mix(color, 1.25));
  rect(c, x, y + h - front, w, front, mix(color, 0.7));
};

/** Seeded random, so the skyline and floor look the same on every visit. */
function seeded(seed: number) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) / 2147483647);
}

export type Sky = { top: string; bottom: string; city: string; lit: number; night: boolean; sun: string | null };

/** The view out the windows, from the viewer's own clock. */
export function skyFor(hour: number): Sky {
  if (hour >= 8 && hour < 17) return { top: "#4f9be0", bottom: "#a8d8f5", city: "#4d5d8c", lit: 0.04, night: false, sun: "#fff3b0" };
  if (hour >= 17 && hour < 20) return { top: "#3b2d6b", bottom: "#ff9a5a", city: "#2a2245", lit: 0.35, night: false, sun: "#ffcf6b" };
  if (hour >= 5 && hour < 8) return { top: "#2d3a78", bottom: "#ffb57a", city: "#2a2245", lit: 0.25, night: false, sun: "#ffd98a" };
  return { top: "#050817", bottom: "#1b1f45", city: "#120f2a", lit: 0.6, night: true, sun: null };
}

// Window panes on the top wall: [x, width]
export const WINDOWS: [number, number][] = [[118, 74], [338, 28], [386, 118]];
export const BOARD = { x: 196, y: 4, w: 126, h: 40 };
export const WHITEBOARD = { x: 10, y: 8, w: 92, h: 32 };

function windowPane(c: Ctx, x: number, w: number, sky: Sky, seed: number) {
  const y = 7, h = 31;
  rect(c, x - 3, y - 3, w + 6, h + 6, "#1b1530");
  rect(c, x - 2, y - 2, w + 4, h + 4, "#6b5fa0");
  for (let i = 0; i < h; i++) {
    const t = i / h;
    const a = parseInt(sky.top.slice(1), 16), b = parseInt(sky.bottom.slice(1), 16);
    const ch = (s: number) => Math.round(((a >> s) & 255) * (1 - t) + ((b >> s) & 255) * t);
    rect(c, x, y + i, w, 1, `rgb(${ch(16)},${ch(8)},${ch(0)})`);
  }
  const rnd = seeded(seed);
  if (sky.night) for (let i = 0; i < w / 6; i++) rect(c, x + rnd() * w, y + rnd() * (h / 2), 1, 1, "#ffffff");
  // Skyline, with a few landmark towers
  let bx = x;
  while (bx < x + w) {
    const bw = 4 + Math.floor(rnd() * 7), bh = 8 + Math.floor(rnd() * (h - 10));
    const ww = Math.min(bw, x + w - bx);
    rect(c, bx, y + h - bh, ww, bh, sky.city);
    if (rnd() < 0.25 && bh > 18) rect(c, bx + Math.floor(ww / 2), y + h - bh - 4, 1, 4, sky.city); // antenna
    for (let wy = y + h - bh + 2; wy < y + h - 1; wy += 3) {
      for (let wx = bx + 1; wx < bx + ww - 1; wx += 2) {
        if (rnd() < sky.lit) rect(c, wx, wy, 1, 1, "#ffd76a");
      }
    }
    bx += bw + (rnd() < 0.3 ? 1 : 0);
  }
  // mullions and sill
  for (let mx = x + 24; mx < x + w - 4; mx += 24) rect(c, mx, y, 2, h, "#6b5fa0");
  rect(c, x - 3, y + h + 2, w + 6, 2, "#8a7fc0");
}

function plant(c: Ctx, tx: number, ty: number, big = true) {
  const x = tx * TILE, y = ty * TILE;
  block(c, x + 3, y + 9, 10, 7, "#b5653a", 3);
  rect(c, x + 4, y + 9, 8, 1, "#3b2412");
  const leaves: [number, number, string][] = big
    ? [[1, 2, "#2e7d32"], [6, -3, "#43a047"], [10, 1, "#2e7d32"], [3, -1, "#66bb6a"], [8, 4, "#388e3c"], [0, 5, "#43a047"], [11, 5, "#2e7d32"]]
    : [[3, 3, "#43a047"], [7, 1, "#2e7d32"], [9, 4, "#66bb6a"]];
  for (const [dx, dy, col] of leaves) rect(c, x + dx, y + dy, 5, 5, col);
}

// ---------------------------------------------------------------------------
// Floor layer
// ---------------------------------------------------------------------------

export function drawFloor(c: Ctx, sky: Sky) {
  const rnd = seeded(5);
  for (let ty = WALL; ty < ROWS; ty++) {
    for (let tx = 0; tx < COLS; tx++) {
      const x = tx * TILE, y = ty * TILE;
      const conference = tx <= 6 && ty <= 7;
      const lounge = tx <= 7 && ty >= 9;
      const boss = tx >= 24 && ty <= 7;
      const kitchen = tx >= 23 && ty >= 9;
      if (boss || lounge) {
        // wood planks
        const base = boss ? "#7b5236" : "#6d4c35";
        rect(c, x, y, TILE, TILE, base);
        for (let py = 0; py < TILE; py += 4) {
          rect(c, x, y + py, TILE, 1, mix(base, 0.82));
          rect(c, x + ((tx * 7 + py * 3) % 16), y + py, 1, 4, mix(base, 0.78));
        }
      } else if (kitchen) {
        rect(c, x, y, TILE, TILE, (tx + ty) % 2 ? "#d9d2c0" : "#c4bca8");
        rect(c, x, y, TILE, 1, "#b3ab97");
        rect(c, x, y, 1, TILE, "#b3ab97");
      } else if (conference) {
        rect(c, x, y, TILE, TILE, "#38406a");
        rect(c, x + 4, y + 4, 1, 1, "#424b7a");
        rect(c, x + 12, y + 12, 1, 1, "#424b7a");
      } else {
        // carpet tiles, alternating grain
        rect(c, x, y, TILE, TILE, (tx + ty) % 2 ? "#283258" : "#2a355e");
        for (let k = 0; k < 4; k++) rect(c, x + Math.floor(rnd() * 16), y + Math.floor(rnd() * 16), 1, 1, "#33406f");
      }
    }
  }
  // Rugs: the trading floor's red rug with the desk's gold coin, the lounge rug, the manager's rug
  const rug = (x: number, y: number, w: number, h: number, base: string, border: string) => {
    rect(c, x, y, w, h, border);
    rect(c, x + 2, y + 2, w - 4, h - 4, base);
    rect(c, x + 4, y + 4, w - 8, 1, border);
    rect(c, x + 4, y + h - 5, w - 8, 1, border);
    for (let fx = x + 1; fx < x + w - 1; fx += 3) { rect(c, fx, y - 1, 1, 1, border); rect(c, fx, y + h, 1, 1, border); }
  };
  rug(13 * TILE + 2, 13 * TILE + 2, 6 * TILE - 4, 3 * TILE - 4, "#8e2433", "#d4a43a");
  const coinX = 16 * TILE - 7, coinY = 14 * TILE - 7;
  rect(c, coinX + 3, coinY, 8, 14, "#f5c542"); rect(c, coinX, coinY + 3, 14, 8, "#f5c542"); rect(c, coinX + 1, coinY + 1, 12, 12, "#f5c542");
  rect(c, coinX + 3, coinY + 3, 8, 8, "#d4a43a");
  const dollar = [".XXX", "X...", ".XX.", "...X", "XXX."];
  dollar.forEach((row, i) => [...row].forEach((ch, j) => ch === "X" && rect(c, coinX + 5 + j, coinY + 4 + i, 1, 1, "#7a4e10")));
  rug(1 * TILE, 11 * TILE + 2, 5 * TILE, 4 * TILE - 2, "#2f6d6a", "#9fd3c7");
  rug(25 * TILE, 3 * TILE + 4, 5 * TILE, 4 * TILE - 2, "#6b1f2a", "#c79a1e");

  // Window light falling on the floor during the day
  if (!sky.night) {
    c.fillStyle = sky.sun === "#fff3b0" ? "rgba(255, 244, 190, 0.07)" : "rgba(255, 190, 120, 0.08)";
    for (const [x, w] of WINDOWS) {
      c.beginPath();
      c.moveTo(x, WALL * TILE); c.lineTo(x + w, WALL * TILE); c.lineTo(x + w + 30, WALL * TILE + 60); c.lineTo(x + 30, WALL * TILE + 60);
      c.fill();
    }
  }

  // The top wall
  rect(c, 0, 0, WIDTH, WALL * TILE, "#2b2346");
  for (let x = 0; x < WIDTH; x += 8) rect(c, x, 0, 1, WALL * TILE - 6, "#2f274d");
  rect(c, 0, WALL * TILE - 6, WIDTH, 6, "#3a2f5c");
  rect(c, 0, WALL * TILE - 6, WIDTH, 1, "#5a4d8a");
  rect(c, 0, WALL * TILE - 1, WIDTH, 1, "#140f24");
  WINDOWS.forEach(([x, w], i) => windowPane(c, x, w, sky, 11 + i * 13));
  // Whiteboard (scribbles are drawn live)
  rect(c, WHITEBOARD.x - 2, WHITEBOARD.y - 2, WHITEBOARD.w + 4, WHITEBOARD.h + 5, "#9aa3b5");
  rect(c, WHITEBOARD.x, WHITEBOARD.y, WHITEBOARD.w, WHITEBOARD.h, "#f4f6fa");
  rect(c, WHITEBOARD.x + 10, WHITEBOARD.y + WHITEBOARD.h + 1, 14, 2, "#5f6b7a");
  rect(c, WHITEBOARD.x + 12, WHITEBOARD.y + WHITEBOARD.h, 3, 1, "#e03c3c");
  rect(c, WHITEBOARD.x + 17, WHITEBOARD.y + WHITEBOARD.h, 3, 1, "#2f5aa8");
  // The big board frame (content drawn live)
  rect(c, BOARD.x - 3, BOARD.y - 2, BOARD.w + 6, BOARD.h + 4, "#141020");
  rect(c, BOARD.x - 2, BOARD.y - 1, BOARD.w + 4, BOARD.h + 2, "#f5c542");
  rect(c, BOARD.x, BOARD.y + 1, BOARD.w, BOARD.h - 2, "#07060f");
  // Clock
  rect(c, 372, 12, 14, 14, "#141020");
  rect(c, 373, 13, 12, 12, "#ecf0f1");
  // A framed poster and a neon sign
  rect(c, 104, 12, 10, 14, "#141020"); rect(c, 105, 13, 8, 12, "#f5c542"); rect(c, 106, 18, 6, 1, "#7a4e10");
  rect(c, 105, 15, 2, 2, "#2ecc71"); rect(c, 108, 19, 4, 4, "#e03c3c");

  // Glass walls (thin, with posts): conference room and manager's office
  const glass = "rgba(150, 220, 255, 0.35)", post = "#8fa3c7";
  rect(c, 7 * TILE + 6, WALL * TILE, 3, 5 * TILE, glass);
  rect(c, 0, 8 * TILE + 6, 4 * TILE, 3, glass);
  rect(c, 5 * TILE, 8 * TILE + 6, 3 * TILE - 7, 3, glass);
  rect(c, 23 * TILE + 6, WALL * TILE, 3, 3 * TILE, glass);
  rect(c, 23 * TILE + 6, 7 * TILE, 3, 2 * TILE - 7, glass);
  rect(c, 24 * TILE - 7, 8 * TILE + 6, 8 * TILE + 7, 3, glass);
  for (const [x, y] of [[7 * TILE + 6, 3 * TILE], [7 * TILE + 6, 8 * TILE + 6], [4 * TILE - 1, 8 * TILE + 6], [5 * TILE, 8 * TILE + 6],
    [23 * TILE + 6, 6 * TILE - 2], [23 * TILE + 6, 7 * TILE], [23 * TILE + 6, 8 * TILE + 6], [WIDTH - 3, 8 * TILE + 6]] as const) {
    rect(c, x, y, 3, 3, post);
  }
}

// ---------------------------------------------------------------------------
// Objects layer (outlined, with shadows)
// ---------------------------------------------------------------------------

export function drawObjects(c: Ctx) {
  // Conference room: long table, chairs on the far side (their backs face us on the near side)
  block(c, 2 * TILE - 2, 5 * TILE + 1, 4 * TILE + 4, 2 * TILE - 2, "#8b5a2b", 4);
  rect(c, 2 * TILE + 4, 5 * TILE + 6, 8, 5, "#ecf0f1"); rect(c, 3 * TILE + 8, 5 * TILE + 5, 9, 6, "#ecf0f1");
  rect(c, 4 * TILE + 10, 5 * TILE + 7, 5, 4, "#2b2b2b"); rect(c, 5 * TILE + 2, 5 * TILE + 4, 3, 3, "#ffffff");
  for (let x = 2; x <= 5; x++) block(c, x * TILE + 3, 4 * TILE + 2, 10, 9, "#3a3f58", 2);
  plant(c, 0, 3, false);
  // Projector screen on the conference table? A speakerphone
  rect(c, 3 * TILE + 13, 6 * TILE - 1, 6, 4, "#1a1a1a"); rect(c, 3 * TILE + 15, 6 * TILE, 2, 1, "#2ecc71");

  // Lounge: TV console + TV, couch seat, arcade cabinets, aquarium, beanbags
  block(c, 1 * TILE, 10 * TILE + 6, 4 * TILE, 10, "#4a3424", 3);
  rect(c, 1 * TILE + 8, 10 * TILE - 10, 4 * TILE - 16, 17, "#111111"); // TV (screen drawn live)
  rect(c, 3 * TILE - 3, 10 * TILE + 7, 6, 2, "#111111");
  rect(c, 1 * TILE + 4, 10 * TILE + 10, 6, 3, "#2b2b2b"); rect(c, 4 * TILE + 6, 10 * TILE + 10, 6, 3, "#2b2b2b"); // speakers
  block(c, 1 * TILE, 13 * TILE + 2, 4 * TILE, 10, "#6c3fa0", 2); // couch seat (back in front layer)
  for (let i = 0; i < 4; i++) rect(c, 1 * TILE + i * TILE + 2, 13 * TILE + 3, TILE - 4, 6, "#7d4fb5");
  for (const [x, col] of [[6, "#c0392b"], [7, "#2f5aa8"]] as const) {
    block(c, x * TILE + 1, 10 * TILE - 8, 14, 22, col, 4);
    rect(c, x * TILE + 3, 10 * TILE - 6, 10, 8, "#07060f"); // screen (drawn live)
    rect(c, x * TILE + 3, 10 * TILE + 4, 10, 4, "#2b2b2b");
    rect(c, x * TILE + 5, 10 * TILE + 5, 2, 2, "#e03c3c"); rect(c, x * TILE + 9, 10 * TILE + 5, 2, 2, "#f5c542");
  }
  block(c, 0, 15 * TILE, 14, 3 * TILE, "#5f6b7a", 3);
  rect(c, 1, 15 * TILE + 2, 12, 3 * TILE - 8, "#1e6fb5"); // water (fish drawn live)
  rect(c, 1, 18 * TILE - 10, 12, 4, "#e2c48a");
  rect(c, 3, 17 * TILE, 2, 8, "#2e7d32"); rect(c, 8, 17 * TILE - 4, 2, 10, "#43a047");
  rect(c, 5 * TILE + 2, 15 * TILE + 4, 12, 10, "#e67e22"); rect(c, 5 * TILE + 4, 15 * TILE + 5, 8, 3, "#f39c12");
  rect(c, 6 * TILE + 2, 16 * TILE + 4, 12, 10, "#16a085"); rect(c, 6 * TILE + 4, 16 * TILE + 5, 8, 3, "#1abc9c");
  plant(c, 0, 10, false); plant(c, 7, 17);

  // Trading floor: desks with monitors, keyboards and personal touches
  DESKS.forEach((d, i) => {
    const x = d.col * TILE, y = d.row * TILE;
    block(c, x + 1, y + 3, 30, 12, "#c8ab82", 4);
    rect(c, x + 1, y + 11, 30, 1, "#8b6a45");
    for (const mx of [x + 4, x + 17]) {
      rect(c, mx, y - 3, 11, 9, "#1d1d26"); // bezel (screen drawn live)
      rect(c, mx + 4, y + 6, 3, 2, "#1d1d26");
      rect(c, mx + 2, y + 7, 7, 1, "#3a3a48");
    }
    rect(c, x + 10, y + 9, 12, 2, "#e8ebf0"); rect(c, x + 10, y + 9, 12, 1, "#ffffff"); // keyboard
    rect(c, x + 24, y + 9, 2, 3, "#e8ebf0");
    // personal touch per desk
    const touch = i % 4;
    if (touch === 0) { rect(c, x + 3, y + 7, 3, 4, "#ffffff"); rect(c, x + 6, y + 8, 1, 2, "#ffffff"); }
    if (touch === 1) { rect(c, x + 2, y + 6, 5, 5, "#f5f5f5"); rect(c, x + 3, y + 7, 3, 3, "#f5c542"); }
    if (touch === 2) { rect(c, x + 3, y + 5, 4, 6, "#43a047"); rect(c, x + 3, y + 9, 4, 2, "#b5653a"); }
    if (touch === 3) { rect(c, x + 27, y + 5, 3, 6, "#f5c542"); rect(c, x + 26, y + 4, 5, 2, "#ffffff"); }
    // empty chair seat (the back is in the front layer)
    const cx = (d.col + 1) * TILE;
    block(c, cx - 6, (d.row + 1) * TILE + 2, 12, 8, "#2b2b36", 2);
  });
  // Printer, the bell on its podium, the server rack, trash cans, water cooler
  block(c, 8 * TILE + 1, 3 * TILE + 2, 14, 12, "#cfd8dc", 4);
  rect(c, 8 * TILE + 3, 3 * TILE + 4, 10, 2, "#37474f");
  rect(c, 8 * TILE + 11, 3 * TILE + 8, 2, 2, "#2ecc71");
  block(c, 21 * TILE + 3, 3 * TILE + 6, 10, 10, "#5e3a1a", 3);
  block(c, 22 * TILE + 1, 3 * TILE - 6, 14, 22, "#2b2f3a", 2);
  for (let k = 0; k < 5; k++) rect(c, 22 * TILE + 3, 3 * TILE - 4 + k * 4, 10, 2, "#1a1d24");
  for (const [tx, ty] of [[8, 8], [21, 8]] as const) {
    block(c, tx * TILE + 4, ty * TILE + 5, 8, 10, "#7f8c8d", 2);
    rect(c, tx * TILE + 5, ty * TILE + 5, 6, 2, "#4a5459");
  }
  const cooler = (tx: number, ty: number) => {
    block(c, tx * TILE + 3, ty * TILE + 7, 10, 9, "#ecf0f1", 3);
    rect(c, tx * TILE + 4, ty * TILE - 2, 8, 9, "#7fd3ff");
    rect(c, tx * TILE + 5, ty * TILE - 1, 2, 6, "#c7efff");
    rect(c, tx * TILE + 6, ty * TILE + 10, 2, 2, "#2f5aa8"); rect(c, tx * TILE + 9, ty * TILE + 10, 2, 2, "#e03c3c");
  };
  cooler(22, 13);
  // The bench and the elevator
  block(c, 10 * TILE, 17 * TILE + 3, 3 * TILE, 7, "#a8743c", 3);
  rect(c, 10 * TILE + 2, 17 * TILE + 10, 2, 6, "#5e3a1a"); rect(c, 13 * TILE - 4, 17 * TILE + 10, 2, 6, "#5e3a1a");
  rect(c, 14 * TILE - 2, 17 * TILE - 2, 2 * TILE + 4, TILE + 2, "#5f6b7a");
  rect(c, 14 * TILE, 17 * TILE, 2 * TILE, TILE, "#a9b2c4");
  rect(c, 15 * TILE, 17 * TILE, 1, TILE, "#5f6b7a");
  plant(c, 8, 17); plant(c, 22, 17);

  // Manager's office: safe, plant, the big desk and chair, sofa, golden bull
  block(c, 24 * TILE + 1, 3 * TILE, 14, 15, "#5f6b7a", 3);
  rect(c, 24 * TILE + 3, 3 * TILE + 2, 10, 9, "#76869a");
  rect(c, 24 * TILE + 6, 3 * TILE + 4, 4, 4, "#2b2b2b"); rect(c, 24 * TILE + 7, 3 * TILE + 5, 2, 2, "#f5c542");
  plant(c, 31, 3);
  block(c, 26 * TILE - 2, 5 * TILE + 1, 3 * TILE + 4, 13, "#6b3d1e", 4);
  rect(c, 26 * TILE + 2, 5 * TILE + 3, 10, 6, "#2b2b2b"); rect(c, 26 * TILE + 3, 5 * TILE + 4, 8, 4, "#2f5aa8");
  rect(c, 27 * TILE + 6, 5 * TILE + 4, 8, 3, "#f5f5f5"); rect(c, 28 * TILE + 6, 5 * TILE + 3, 4, 5, "#c79a1e");
  rect(c, 27 * TILE + 4, 5 * TILE + 9, 8, 2, "#f5c542"); // nameplate
  block(c, 27 * TILE + 1, 4 * TILE - 2, 14, 14, "#1a1a1a", 3);
  rect(c, 27 * TILE + 3, 4 * TILE, 10, 7, "#4a2a18");
  block(c, 31 * TILE, 5 * TILE - 2, 16, 2 * TILE + 2, "#3b2412", 3);
  rect(c, 31 * TILE + 2, 5 * TILE + 1, 12, 12, "#5a3a22"); rect(c, 31 * TILE + 2, 6 * TILE + 3, 12, 12, "#5a3a22");
  const bull = ["......XX..", "X.XXXXXXX.", "XXXXXXXXXX", ".XXXXXXXX.", ".X.X..X.X."];
  rect(c, 30 * TILE + 1, 7 * TILE + 12, 14, 4, "#2b2b2b");
  bull.forEach((row, i) => [...row].forEach((ch, j) => ch === "X" && rect(c, 30 * TILE + 3 + j, 7 * TILE + 2 + i * 2, 1, 2, i === 0 ? "#fff3b0" : "#f5c542")));

  // Kitchen: counter with coffee machine, sink, fridge, vending, snack shelf; island; cooler; ping pong
  block(c, 31 * TILE, 10 * TILE - 4, TILE, 5 * TILE + 4, "#3d3a52", 2);
  block(c, 31 * TILE + 2, 10 * TILE - 2, 12, 14, "#1a1a1a", 3); // coffee
  rect(c, 31 * TILE + 4, 10 * TILE, 8, 3, "#e03c3c"); rect(c, 31 * TILE + 6, 10 * TILE + 7, 4, 3, "#ecf0f1");
  rect(c, 31 * TILE + 2, 11 * TILE + 3, 12, 9, "#90a4ae"); rect(c, 31 * TILE + 4, 11 * TILE + 5, 8, 5, "#5d7380"); // sink
  block(c, 31 * TILE + 1, 12 * TILE - 4, 14, 20, "#ecf0f1", 2); // fridge
  rect(c, 31 * TILE + 1, 12 * TILE + 4, 14, 1, "#b0bec5"); rect(c, 31 * TILE + 3, 12 * TILE, 1, 3, "#90a4ae"); rect(c, 31 * TILE + 3, 12 * TILE + 7, 1, 4, "#90a4ae");
  block(c, 31 * TILE + 1, 13 * TILE - 2, 14, 18, "#c0392b", 2); // vending
  rect(c, 31 * TILE + 3, 13 * TILE, 8, 12, "#7fd3ff");
  for (let i = 0; i < 3; i++) rect(c, 31 * TILE + 4, 13 * TILE + 1 + i * 4, 6, 2, ["#f5c542", "#43a047", "#e03c3c"][i]);
  block(c, 31 * TILE + 1, 14 * TILE + 2, 14, 12, "#8b5a2b", 2); // snack shelf
  for (let i = 0; i < 4; i++) rect(c, 31 * TILE + 3 + i * 3, 14 * TILE + 4, 2, 4, ["#e67e22", "#f5c542", "#e03c3c", "#9b59b6"][i]);
  cooler(24, 10);
  block(c, 25 * TILE, 12 * TILE + 2, 3 * TILE, 12, "#e8e2d0", 3);
  rect(c, 25 * TILE + 6, 12 * TILE + 4, 6, 4, "#e67e22"); rect(c, 25 * TILE + 7, 12 * TILE + 3, 4, 2, "#f39c12"); // fruit bowl
  rect(c, 26 * TILE + 8, 12 * TILE + 4, 3, 4, "#ffffff"); rect(c, 27 * TILE + 4, 12 * TILE + 5, 5, 3, "#c0392b");
  block(c, 25 * TILE, 15 * TILE + 2, 3 * TILE, 2 * TILE - 4, "#1b5e20", 3);
  rect(c, 25 * TILE + 1, 15 * TILE + 3, 3 * TILE - 2, 2 * TILE - 9, "#2e7d32");
  rect(c, 25 * TILE + 1, 16 * TILE - 1, 3 * TILE - 2, 1, "#ffffff");
  rect(c, 26 * TILE + 8, 15 * TILE + 1, 1, 2 * TILE - 5, "#ecf0f1");
  plant(c, 31, 17);
}

/** Chair and couch backs: drawn after the people, so whoever sits looks like they're in the chair. */
export function drawFront(c: Ctx) {
  for (const d of DESKS) {
    const x = (d.col + 1) * TILE, y = (d.row + 1) * TILE;
    block(c, x - 7, y + 9, 14, 6, "#23232d", 2);
    rect(c, x - 5, y + 10, 10, 2, "#3a3a48");
  }
  for (let x = 2; x <= 5; x++) block(c, x * TILE + 3, 7 * TILE + 7, 10, 6, "#3a3f58", 2);
  block(c, 1 * TILE - 1, 14 * TILE - 3, 4 * TILE + 2, 6, "#5a2f8a", 2);
}

/** Paint all three layers into canvases at native size, with outlines and shadows. */
export function paintRoom(sky: Sky): { base: HTMLCanvasElement; front: HTMLCanvasElement } {
  const make = () => {
    const cv = document.createElement("canvas");
    cv.width = WIDTH; cv.height = HEIGHT;
    return cv;
  };
  const base = make(), objects = make(), front = make();
  drawFloor(base.getContext("2d")!, sky);
  drawObjects(objects.getContext("2d")!);
  drawFront(front.getContext("2d")!);
  outline(objects); outline(front);
  const b = base.getContext("2d")!;
  // soft drop shadow down and to the right
  const shadow = make(), s = shadow.getContext("2d")!;
  s.drawImage(objects, 0, 0);
  s.globalCompositeOperation = "source-in";
  s.fillStyle = "rgba(5, 3, 15, 0.35)";
  s.fillRect(0, 0, WIDTH, HEIGHT);
  b.drawImage(shadow, 2, 3);
  b.drawImage(objects, 0, 0);
  return { base, front };
}

/** Give everything drawn on a canvas a 1px dark outline. */
function outline(cv: HTMLCanvasElement) {
  const ctx = cv.getContext("2d")!;
  const img = ctx.getImageData(0, 0, cv.width, cv.height);
  const d = img.data, w = cv.width, h = cv.height;
  const solid = (x: number, y: number) => x >= 0 && y >= 0 && x < w && y < h && d[(y * w + x) * 4 + 3] > 40;
  const out = new Uint8ClampedArray(d);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (solid(x, y)) continue;
      if (solid(x - 1, y) || solid(x + 1, y) || solid(x, y - 1) || solid(x, y + 1)) {
        const i = (y * w + x) * 4;
        out[i] = 20; out[i + 1] = 16; out[i + 2] = 31; out[i + 3] = 255;
      }
    }
  }
  ctx.putImageData(new ImageData(out, w, h), 0, 0);
}

// ---------------------------------------------------------------------------
// Live bits
// ---------------------------------------------------------------------------

/** Two monitors per desk: green when they're up, red when down, flashing when they just bet. */
export function drawMonitors(c: Ctx, i: number, pnl: number, busy: boolean, t: number, off: boolean) {
  const d = DESKS[i];
  const x = d.col * TILE, y = d.row * TILE;
  const glow = pnl > 0.005 ? "#2ecc71" : pnl < -0.005 ? "#e74c3c" : "#7fd3ff";
  [x + 5, x + 18].forEach((mx, k) => {
    const flash = busy && Math.floor(t * 6 + k) % 2 === 0;
    rect(c, mx, y - 2, 9, 6, off ? "#15131f" : flash ? "#e8fff2" : "#0a1420");
    if (off || flash) return;
    if (k === 0) {
      for (let j = 0; j < 9; j++) {
        const h = 2 + Math.round(Math.sin(t * (busy ? 3 : 0.7) + j * 0.9 + i) * 1.4 + (pnl >= 0 ? -j * 0.18 : j * 0.18));
        rect(c, mx + j, y - 2 + Math.max(0, Math.min(5, h)), 1, 1, glow);
      }
    } else {
      // order book: rows of bars
      for (let j = 0; j < 3; j++) {
        const w = 2 + Math.round((Math.sin(t * 1.3 + j * 2 + i) + 1) * 2.5);
        rect(c, mx + 1, y - 1 + j * 2, w, 1, j === 1 ? "#f5c542" : glow);
      }
    }
  });
}

export function drawClock(c: Ctx, now: Date) {
  const cx = 379, cy = 19;
  rect(c, 373, 13, 12, 12, "#ecf0f1");
  const h = ((now.getHours() % 12) + now.getMinutes() / 60) / 12 * Math.PI * 2;
  const m = (now.getMinutes() / 60) * Math.PI * 2;
  for (let k = 0; k <= 4; k++) rect(c, cx + Math.sin(m) * k, cy - Math.cos(m) * k, 1, 1, "#1a1a1a");
  for (let k = 0; k <= 3; k++) rect(c, cx + Math.sin(h) * k, cy - Math.cos(h) * k, 1, 1, "#c0392b");
}

export function drawBell(c: Ctx, t: number, ringing: boolean) {
  const swing = ringing ? Math.round(Math.sin(t * 30) * 2) : 0;
  const x = 21 * TILE + 5 + swing, y = 3 * TILE - 3;
  rect(c, x + 2, y - 1, 2, 1, "#5e3a1a");
  rect(c, x + 1, y, 4, 2, "#f5c542");
  rect(c, x, y + 2, 6, 4, "#f5c542");
  rect(c, x - 1, y + 6, 8, 2, "#c79a1e");
  rect(c, x + 1, y + 1, 1, 4, "#fff3b0");
}

export function drawFish(c: Ctx, t: number) {
  const fish = [["#f39c12", 0], ["#e74c3c", 2.1], ["#f5c542", 4.2]] as const;
  fish.forEach(([col, off], i) => {
    const fx = 2 + ((Math.sin(t * 0.4 + off) + 1) / 2) * 7;
    const fy = 15 * TILE + 6 + i * 11 + Math.sin(t * 1.3 + off) * 2;
    rect(c, fx, fy, 3, 2, col);
    rect(c, fx + (Math.cos(t * 0.4 + off) > 0 ? -1 : 3), fy, 1, 2, col);
  });
  const by = 18 * TILE - 12 - ((t * 6) % 36);
  rect(c, 6, by, 1, 1, "#b9ecff");
  rect(c, 10, by + 14, 1, 1, "#b9ecff");
}

export function drawServers(c: Ctx, t: number) {
  for (let k = 0; k < 5; k++) {
    for (let j = 0; j < 3; j++) {
      const on = Math.sin(t * (3 + j) + k * 1.7 + j) > 0.2;
      rect(c, 22 * TILE + 4 + j * 3, 3 * TILE - 4 + k * 4, 1, 1, on ? (j === 2 ? "#f5c542" : "#2ecc71") : "#0d2a14");
    }
  }
}

export function drawArcade(c: Ctx, t: number) {
  for (const [x, hue] of [[6, 0], [7, 1]] as const) {
    const sx = x * TILE + 3, sy = 10 * TILE - 6;
    rect(c, sx, sy, 10, 8, "#07060f");
    const k = Math.floor(t * 4 + hue * 3);
    if (hue === 0) {
      rect(c, sx + (k % 8), sy + 5, 2, 2, "#f5c542"); // a little runner
      rect(c, sx + ((k * 3) % 9), sy + 1, 1, 1, "#e74c3c");
      rect(c, sx, sy + 7, 10, 1, "#2ecc71");
    } else {
      for (let j = 0; j < 4; j++) rect(c, sx + 1 + j * 2, sy + 1 + ((k + j) % 3), 1, 1, "#c56cf0"); // invaders
      rect(c, sx + 4 + Math.round(Math.sin(t * 2) * 3), sy + 6, 2, 1, "#7fd3ff");
    }
  }
}

export { WIDTH, HEIGHT };
