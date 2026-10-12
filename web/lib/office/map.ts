/**
 * The office floor plan: a 20x18 grid of 16px tiles, seen from above.
 *
 *   top wall    windows · the big board (desk profit chart) · windows
 *   left        the opening bell, restroom door, aquarium, plants
 *   middle      the trading pit: eight desks in two rows
 *   top right   the manager's glass office (that's you)
 *   bottom      break room (coffee, cooler, vending, ping pong, couch),
 *               the elevator, and The Bench
 */

export const TILE = 16;
export const COLS = 20;
export const ROWS = 18;
export const WIDTH = COLS * TILE;
export const HEIGHT = ROWS * TILE;

export type Tile = { x: number; y: number };
/** A place to stand (pixel position of the feet) and which way to face there. */
export type Spot = { x: number; y: number; face: "down" | "up" | "left" | "right"; tile: Tile; sit?: boolean };

export const tileSpot = (tx: number, ty: number, face: Spot["face"] = "down", dx = 0, dy = 0, sit = false): Spot => ({
  x: tx * TILE + 8 + dx, y: ty * TILE + 13 + dy, face, tile: { x: tx, y: ty }, sit,
});

// Desk pairs (left tile column) and their rows
export const DESKS: { col: number; row: number }[] = [5, 9].flatMap((row) => [2, 5, 8, 11].map((col) => ({ col, row })));

/** Where an employee sits at desk i: on the chair just south of it, facing their monitors. */
export const chairSpot = (i: number): Spot => {
  const d = DESKS[i % DESKS.length];
  return tileSpot(d.col, d.row + 1, "up", 8, -2, true);
};

type Rect = { x: number; y: number; w: number; h: number };
const BLOCKED: Rect[] = [
  { x: 0, y: 0, w: COLS, h: 3 }, // top wall
  { x: 1, y: 3, w: 1, h: 1 }, // the bell
  { x: 0, y: 3, w: 1, h: 1 }, // plant
  { x: 13, y: 3, w: 1, h: 1 }, // printer
  // manager's office: glass walls with a door at (16, 8)
  { x: 14, y: 3, w: 1, h: 6 },
  { x: 15, y: 8, w: 1, h: 1 },
  { x: 17, y: 8, w: 3, h: 1 },
  { x: 16, y: 5, w: 3, h: 1 }, // manager's desk
  { x: 19, y: 7, w: 1, h: 1 }, // golden bull
  { x: 15, y: 3, w: 1, h: 1 }, // safe
  { x: 19, y: 3, w: 1, h: 1 }, // plant
  ...DESKS.map((d) => ({ x: d.col, y: d.row, w: 2, h: 1 })),
  { x: 13, y: 10, w: 1, h: 1 }, // water cooler
  { x: 19, y: 10, w: 1, h: 4 }, // coffee, counter, fridge, vending
  { x: 19, y: 9, w: 1, h: 1 }, // plant
  { x: 15, y: 12, w: 3, h: 2 }, // ping pong table
  { x: 15, y: 17, w: 4, h: 1 }, // couch
  { x: 0, y: 12, w: 1, h: 3 }, // aquarium
  { x: 4, y: 17, w: 3, h: 1 }, // the bench
  { x: 9, y: 17, w: 2, h: 1 }, // elevator
  { x: 0, y: 7, w: 1, h: 1 }, // restroom door
  { x: 0, y: 17, w: 1, h: 1 }, // plant
  { x: 13, y: 17, w: 1, h: 1 }, // plant
];

export const walkable: boolean[][] = Array.from({ length: ROWS }, (_, y) =>
  Array.from({ length: COLS }, (_, x) => !BLOCKED.some((r) => x >= r.x && x < r.x + r.w && y >= r.y && y < r.y + r.h)),
);

export const SPOTS = {
  coffee: tileSpot(18, 10, "right"),
  fridge: tileSpot(18, 11, "right"),
  vending: tileSpot(18, 13, "right"),
  cooler: [tileSpot(13, 11, "up"), tileSpot(14, 10, "left"), tileSpot(12, 11, "right")],
  windows: [tileSpot(3, 3, "up"), tileSpot(5, 3, "up"), tileSpot(6, 4, "up")],
  board: [tileSpot(9, 3, "up"), tileSpot(10, 3, "up"), tileSpot(8, 4, "up"), tileSpot(11, 4, "up")],
  bell: tileSpot(2, 3, "left"),
  aquarium: [tileSpot(1, 13, "left"), tileSpot(1, 12, "left")],
  printer: tileSpot(12, 3, "right"),
  restroom: tileSpot(1, 7, "left"),
  elevator: [tileSpot(9, 16, "down"), tileSpot(10, 16, "down")],
  pingpong: [tileSpot(14, 12, "right", 0, 6), tileSpot(18, 12, "left", 0, 6)],
  couch: [15, 16, 17, 18].map((x) => tileSpot(x, 16, "down", 0, 10, true)),
  bench: [4, 5, 6].map((x) => tileSpot(x, 16, "down", 0, 10, true)),
  bull: tileSpot(18, 7, "right"),
  boss: tileSpot(17, 6, "up"),
  stage: tileSpot(7, 7, "down", 8, 0),
};

/** Open floor tiles, for wandering, pacing, parties and fire drills. */
export const OPEN: Tile[] = walkable.flatMap((row, y) => row.flatMap((ok, x) => (ok && y >= 3 ? [{ x, y }] : [])));
export const PIT: Tile[] = OPEN.filter((t) => t.y >= 7 && t.y <= 8 && t.x >= 1 && t.x <= 13);

/** Shortest walk between two tiles (4 directions), as a list of tiles after the start. */
export function findPath(from: Tile, to: Tile): Tile[] {
  if (from.x === to.x && from.y === to.y) return [];
  const key = (t: Tile) => t.y * COLS + t.x;
  const prev = new Map<number, number>();
  const seen = new Set<number>([key(from)]);
  const queue: Tile[] = [from];
  const goal = key(to);
  // Breadth-first is plenty for a 20x18 floor
  while (queue.length) {
    const cur = queue.shift()!;
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const n = { x: cur.x + dx, y: cur.y + dy };
      if (n.x < 0 || n.y < 0 || n.x >= COLS || n.y >= ROWS) continue;
      const k = key(n);
      if (seen.has(k) || (!walkable[n.y][n.x] && k !== goal)) continue;
      seen.add(k);
      prev.set(k, key(cur));
      if (k === goal) {
        const out: Tile[] = [];
        let c = k;
        while (c !== key(from)) {
          out.unshift({ x: c % COLS, y: Math.floor(c / COLS) });
          c = prev.get(c)!;
        }
        return out;
      }
      queue.push(n);
    }
  }
  return [];
}
