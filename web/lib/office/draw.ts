/**
 * Pixel art for the office floor, drawn with plain rectangles at native
 * resolution (320x288) and scaled up with nearest-neighbour by the page.
 *
 * drawRoom() paints everything that doesn't move (redrawn when the sky
 * changes); the rest are small helpers the animation loop calls every frame.
 */

import { COLS, DESKS, HEIGHT, ROWS, TILE, WIDTH } from "./map";

type Ctx = CanvasRenderingContext2D;
export const rect = (c: Ctx, x: number, y: number, w: number, h: number, color: string) => {
  c.fillStyle = color;
  c.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h));
};

/** Seeded random, so the skyline and carpet look the same on every visit. */
function seeded(seed: number) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) / 2147483647);
}

export type Sky = { top: string; bottom: string; city: string; lit: number; night: boolean };

/** The view out the windows, from the viewer's own clock. */
export function skyFor(hour: number): Sky {
  if (hour >= 7 && hour < 17) return { top: "#5fa8e8", bottom: "#a9d6f5", city: "#5d6b94", lit: 0.04, night: false };
  if (hour >= 17 && hour < 20) return { top: "#3b2d6b", bottom: "#f08a4b", city: "#2d2547", lit: 0.35, night: false };
  if (hour >= 5 && hour < 7) return { top: "#2d3a78", bottom: "#f5b26b", city: "#2d2547", lit: 0.25, night: false };
  return { top: "#070b1f", bottom: "#1b1f45", city: "#141230", lit: 0.6, night: true };
}

function windowPane(c: Ctx, x: number, y: number, w: number, h: number, sky: Sky, seed: number) {
  rect(c, x - 2, y - 2, w + 4, h + 4, "#241d3d");
  for (let i = 0; i < h; i++) {
    const t = i / h;
    const mix = (a: string, b: string) => {
      const pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16);
      const ch = (sh: number) => Math.round(((pa >> sh) & 255) * (1 - t) + ((pb >> sh) & 255) * t);
      return `rgb(${ch(16)},${ch(8)},${ch(0)})`;
    };
    rect(c, x, y + i, w, 1, mix(sky.top, sky.bottom));
  }
  if (sky.night) {
    const rnd = seeded(seed + 7);
    for (let i = 0; i < 6; i++) rect(c, x + rnd() * w, y + rnd() * (h / 2), 1, 1, "#ffffff");
  }
  // Skyline
  const rnd = seeded(seed);
  let bx = x;
  while (bx < x + w) {
    const bw = 3 + Math.floor(rnd() * 5), bh = 6 + Math.floor(rnd() * (h - 6));
    rect(c, bx, y + h - bh, Math.min(bw, x + w - bx), bh, sky.city);
    for (let wy = y + h - bh + 2; wy < y + h - 1; wy += 2) {
      for (let wx = bx + 1; wx < Math.min(bx + bw, x + w) - 1; wx += 2) {
        if (rnd() < sky.lit) rect(c, wx, wy, 1, 1, "#ffd76a");
      }
    }
    bx += bw;
  }
  // Mullion
  rect(c, x + Math.floor(w / 2), y, 1, h, "#241d3d");
}

function plant(c: Ctx, tx: number, ty: number) {
  const x = tx * TILE, y = ty * TILE;
  rect(c, x + 4, y + 9, 8, 6, "#8b5a2b");
  rect(c, x + 4, y + 9, 8, 1, "#a8743c");
  for (const [dx, dy, col] of [[2, 3, "#2e7d32"], [6, 0, "#43a047"], [9, 3, "#2e7d32"], [4, 5, "#43a047"], [8, 6, "#388e3c"]] as const) {
    rect(c, x + dx, y + dy, 5, 4, col);
  }
}

/** Everything that stays put. */
export function drawRoom(c: Ctx, sky: Sky) {
  // Floors: carpet everywhere, linoleum in the break room, wood in the manager's office
  for (let ty = 3; ty < ROWS; ty++) {
    for (let tx = 0; tx < COLS; tx++) {
      const x = tx * TILE, y = ty * TILE;
      const breakRoom = tx >= 14 && ty >= 10;
      const office = tx >= 15 && ty >= 3 && ty <= 7;
      if (office) {
        rect(c, x, y, TILE, TILE, ty % 2 ? "#6b4a2e" : "#634429");
        rect(c, x + ((ty * 7) % 16), y, 1, TILE, "#4f3420");
      } else if (breakRoom) {
        rect(c, x, y, TILE, TILE, (tx + ty) % 2 ? "#5b5480" : "#4f4874");
      } else {
        rect(c, x, y, TILE, TILE, "#2b2552");
        rect(c, x + 3, y + 3, 1, 1, "#352e63");
        rect(c, x + 11, y + 11, 1, 1, "#352e63");
      }
    }
  }
  // A red rug with a gold dollar sign in the middle of the pit
  rect(c, 4 * TILE + 4, 7 * TILE + 2, 6 * TILE - 8, 2 * TILE - 4, "#7a1f2b");
  rect(c, 4 * TILE + 6, 7 * TILE + 4, 6 * TILE - 12, 2 * TILE - 8, "#9b2a37");
  const dollar = [".XXX.", "X.X..", ".XXX.", "..X.X", ".XXX."];
  dollar.forEach((row, i) => [...row].forEach((ch, j) => ch === "X" && rect(c, 7 * TILE + 4 + j * 2, 7 * TILE + 6 + i * 4, 2, 4, "#f5c542")));

  // Top wall
  rect(c, 0, 0, WIDTH, 3 * TILE, "#3b3160");
  rect(c, 0, 3 * TILE - 4, WIDTH, 4, "#241d3d");
  rect(c, 0, 3 * TILE - 5, WIDTH, 1, "#4a3f78");
  windowPane(c, 4, 6, 40, 30, sky, 11);
  windowPane(c, 52, 6, 52, 30, sky, 23);
  windowPane(c, 244, 6, 70, 30, sky, 37);
  // The big board frame (content drawn live)
  rect(c, 112, 3, 112, 40, "#f5c542");
  rect(c, 114, 5, 108, 36, "#07060f");
  // Clock frame
  rect(c, 228, 10, 12, 12, "#241d3d");
  rect(c, 229, 11, 10, 10, "#ecf0f1");

  // Left side: the opening bell, plants, restroom, aquarium
  plant(c, 0, 3);
  rect(c, TILE + 4, 3 * TILE + 8, 8, 8, "#5e3a1a");
  rect(c, TILE + 4, 3 * TILE + 8, 8, 1, "#7a4a22");
  rect(c, 0, 7 * TILE, 4, TILE, "#241d3d");
  rect(c, 1, 7 * TILE + 1, 11, TILE - 2, "#8b5a2b");
  rect(c, 9, 7 * TILE + 8, 2, 2, "#f5c542");
  rect(c, 3, 7 * TILE + 3, 5, 4, "#7fd3ff");
  rect(c, 0, 12 * TILE, 14, 3 * TILE, "#241d3d");
  rect(c, 1, 12 * TILE + 2, 12, 3 * TILE - 4, "#1e6fb5");
  rect(c, 1, 15 * TILE - 7, 12, 5, "#e2c48a");
  rect(c, 3, 13 * TILE, 2, 6, "#2e7d32");
  rect(c, 8, 14 * TILE - 2, 2, 8, "#43a047");
  plant(c, 0, 17);

  // Printer
  rect(c, 13 * TILE + 1, 3 * TILE + 4, 14, 10, "#cfd8dc");
  rect(c, 13 * TILE + 1, 3 * TILE + 4, 14, 2, "#90a4ae");
  rect(c, 13 * TILE + 4, 3 * TILE + 8, 8, 2, "#37474f");

  // Desks: dark tops, the monitors are drawn live
  for (const d of DESKS) {
    const x = d.col * TILE, y = d.row * TILE;
    rect(c, x, y + 2, 2 * TILE, TILE - 2, "#2b2840");
    rect(c, x + 1, y + 2, 2 * TILE - 2, TILE - 5, "#4b4668");
    rect(c, x + 12, y + 11, 8, 2, "#ecf0f1"); // keyboard
    rect(c, x + 22, y + 10, 3, 3, "#ecf0f1"); // mouse
    rect(c, x + 3, y + 10, 4, 3, "#f5f5f5"); // papers
  }

  // Manager's office: safe, plant, big desk, the golden bull, glass walls
  rect(c, 15 * TILE + 2, 3 * TILE + 2, 12, 12, "#5f6b7a");
  rect(c, 15 * TILE + 3, 3 * TILE + 3, 10, 10, "#76869a");
  rect(c, 15 * TILE + 7, 3 * TILE + 7, 3, 3, "#2b2b2b");
  plant(c, 19, 3);
  rect(c, 16 * TILE, 5 * TILE + 1, 3 * TILE, TILE - 2, "#5e3a1a");
  rect(c, 16 * TILE + 1, 5 * TILE + 1, 3 * TILE - 2, TILE - 5, "#8b5a2b");
  rect(c, 17 * TILE + 2, 5 * TILE + 3, 12, 6, "#111111");
  rect(c, 17 * TILE + 3, 5 * TILE + 4, 10, 4, "#2f5aa8");
  rect(c, 17 * TILE + 2, 4 * TILE + 2, 12, 10, "#1a1a1a"); // the big leather chair
  rect(c, 17 * TILE + 3, 4 * TILE + 3, 10, 6, "#3a2a1a");
  const bull = ["......XX..", "XXXXXXXXX.", ".XXXXXXXXX", ".XXXXXXX..", ".X.X..X.X."];
  bull.forEach((row, i) => [...row].forEach((ch, j) => ch === "X" && rect(c, 19 * TILE + 3 + j, 7 * TILE + 5 + i * 2, 1, 2, "#f5c542")));
  rect(c, 19 * TILE + 2, 7 * TILE + 14, 12, 2, "#5e3a1a");
  const glass = "rgba(127, 211, 255, 0.55)";
  rect(c, 14 * TILE + 7, 3 * TILE, 2, 6 * TILE, glass);
  rect(c, 14 * TILE + 7, 8 * TILE + 7, 2 * TILE + 1, 2, glass);
  rect(c, 17 * TILE, 8 * TILE + 7, 3 * TILE, 2, glass);
  rect(c, 16 * TILE, 8 * TILE + 6, 1, 4, "#9aa8c7");
  rect(c, 17 * TILE - 1, 8 * TILE + 6, 1, 4, "#9aa8c7");

  // Break room: water cooler, kitchen counter along the right wall, ping pong, couch
  rect(c, 13 * TILE + 4, 10 * TILE + 8, 8, 8, "#ecf0f1");
  rect(c, 13 * TILE + 5, 10 * TILE, 6, 8, "#7fd3ff");
  rect(c, 13 * TILE + 6, 10 * TILE + 1, 2, 5, "#b9ecff");
  rect(c, 19 * TILE, 10 * TILE, TILE, 4 * TILE, "#3d3a52");
  rect(c, 19 * TILE + 2, 10 * TILE + 2, 12, 12, "#1a1a1a"); // coffee machine
  rect(c, 19 * TILE + 4, 10 * TILE + 4, 8, 3, "#e03c3c");
  rect(c, 19 * TILE + 6, 10 * TILE + 10, 4, 3, "#ecf0f1");
  rect(c, 19 * TILE + 2, 11 * TILE + 4, 12, 7, "#90a4ae"); // sink
  rect(c, 19 * TILE + 4, 11 * TILE + 6, 8, 3, "#5d7380");
  rect(c, 19 * TILE + 1, 12 * TILE, 14, TILE, "#ecf0f1"); // fridge
  rect(c, 19 * TILE + 1, 12 * TILE + 7, 14, 1, "#b0bec5");
  rect(c, 19 * TILE + 3, 12 * TILE + 3, 1, 3, "#90a4ae");
  rect(c, 19 * TILE + 1, 13 * TILE, 14, TILE, "#c0392b"); // vending machine
  rect(c, 19 * TILE + 3, 13 * TILE + 2, 7, 11, "#7fd3ff");
  for (let i = 0; i < 3; i++) rect(c, 19 * TILE + 4, 13 * TILE + 3 + i * 4, 5, 2, ["#f5c542", "#43a047", "#e03c3c"][i]);
  rect(c, 15 * TILE, 12 * TILE + 2, 3 * TILE, 2 * TILE - 4, "#1b5e20");
  rect(c, 15 * TILE + 1, 12 * TILE + 3, 3 * TILE - 2, 2 * TILE - 6, "#2e7d32");
  rect(c, 15 * TILE + 1, 13 * TILE - 1, 3 * TILE - 2, 1, "#ffffff");
  rect(c, 16 * TILE + 8, 12 * TILE + 1, 1, 2 * TILE - 2, "#ecf0f1"); // net
  rect(c, 15 * TILE, 17 * TILE + 2, 4 * TILE, TILE - 2, "#4a2a78");
  for (let i = 0; i < 4; i++) rect(c, 15 * TILE + i * TILE + 1, 17 * TILE + 4, TILE - 2, TILE - 6, "#6c3fa0");
  plant(c, 19, 9);
  plant(c, 13, 17);

  // The elevator and The Bench
  rect(c, 9 * TILE, 17 * TILE, 2 * TILE, TILE, "#5f6b7a");
  rect(c, 9 * TILE + 1, 17 * TILE + 2, 2 * TILE - 2, TILE - 2, "#8a93a6");
  rect(c, 10 * TILE, 17 * TILE + 2, 1, TILE - 2, "#5f6b7a");
  rect(c, 4 * TILE, 17 * TILE + 5, 3 * TILE, 5, "#a8743c");
  rect(c, 4 * TILE, 17 * TILE + 10, 3 * TILE, 2, "#5e3a1a");
  rect(c, 4 * TILE + 2, 17 * TILE + 12, 2, 4, "#5e3a1a");
  rect(c, 7 * TILE - 4, 17 * TILE + 12, 2, 4, "#5e3a1a");
}

/** Chair backs: drawn after the people, so whoever sits looks like they're in the chair. */
export function drawChairs(c: Ctx) {
  for (const d of DESKS) {
    const x = (d.col + 1) * TILE, y = (d.row + 1) * TILE;
    rect(c, x - 6, y + 8, 12, 5, "#1a1a1a");
    rect(c, x - 5, y + 9, 10, 3, "#2b2b2b");
    rect(c, x - 1, y + 13, 2, 2, "#1a1a1a");
  }
}

/** Two monitors per desk: green when they're up, red when down, flashing when they just bet. */
export function drawMonitors(c: Ctx, i: number, pnl: number, busy: boolean, t: number, rnd: number, off = false) {
  const d = DESKS[i];
  const x = d.col * TILE, y = d.row * TILE;
  const glow = pnl > 0.005 ? "#2ecc71" : pnl < -0.005 ? "#e74c3c" : "#7fd3ff";
  for (const mx of [x + 4, x + 17]) {
    rect(c, mx, y, 11, 8, "#111111");
    const flash = busy && Math.floor(t * 6 + mx) % 2 === 0;
    rect(c, mx + 1, y + 1, 9, 6, flash ? "#ffffff" : off ? "#15131f" : "#0b1a12");
    if (!flash && !off) {
      // a tiny wiggly price line
      for (let k = 0; k < 9; k++) {
        const h = 2 + Math.round(Math.sin(t * (busy ? 3 : 0.6) + k * 0.9 + mx + rnd) * 1.5 + (pnl >= 0 ? -k * 0.15 : k * 0.15));
        rect(c, mx + 1 + k, y + 1 + Math.max(0, Math.min(5, h)), 1, 1, glow);
      }
    }
    rect(c, mx + 4, y + 8, 3, 2, "#111111");
  }
}

export function drawClock(c: Ctx, now: Date) {
  const cx = 234, cy = 16;
  rect(c, 229, 11, 10, 10, "#ecf0f1");
  const h = ((now.getHours() % 12) + now.getMinutes() / 60) / 12 * Math.PI * 2;
  const m = (now.getMinutes() / 60) * Math.PI * 2;
  for (let k = 0; k <= 3; k++) rect(c, cx + Math.sin(m) * k, cy - Math.cos(m) * k, 1, 1, "#1a1a1a");
  for (let k = 0; k <= 2; k++) rect(c, cx + Math.sin(h) * k, cy - Math.cos(h) * k, 1, 1, "#c0392b");
}

export function drawBell(c: Ctx, t: number, ringing: boolean) {
  const swing = ringing ? Math.round(Math.sin(t * 30) * 2) : 0;
  const x = TILE + 5 + swing, y = 3 * TILE + 1;
  rect(c, x + 2, y, 2, 1, "#c79a1e");
  rect(c, x + 1, y + 1, 4, 2, "#f5c542");
  rect(c, x, y + 3, 6, 3, "#f5c542");
  rect(c, x - 1, y + 6, 8, 1, "#c79a1e");
  rect(c, x + 2, y + 7, 2, 1, "#5e3a1a");
}

export function drawFish(c: Ctx, t: number) {
  const fish = [["#f39c12", 0], ["#e74c3c", 2.1], ["#f5c542", 4.2]] as const;
  fish.forEach(([col, off], i) => {
    const fx = 2 + ((Math.sin(t * 0.4 + off) + 1) / 2) * 8;
    const fy = 12 * TILE + 6 + i * 11 + Math.sin(t * 1.3 + off) * 2;
    rect(c, fx, fy, 3, 2, col);
    rect(c, fx + (Math.cos(t * 0.4 + off) > 0 ? -1 : 3), fy, 1, 2, col);
  });
  // bubbles
  const by = 15 * TILE - 8 - ((t * 6) % 36);
  rect(c, 6, by, 1, 1, "#b9ecff");
  rect(c, 10, by + 14, 1, 1, "#b9ecff");
}

export { WIDTH, HEIGHT };
