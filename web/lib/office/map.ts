/**
 * The office floor plan: a 32x18 grid of 16px tiles, seen from above.
 *
 *   top wall     whiteboard · windows · the big board · bell · windows
 *   left         conference room (glass), lounge (TV, couch, arcade, aquarium)
 *   middle       the trading floor: ten desks in two rows, a rug, the bench,
 *                the elevator
 *   right        the manager's glass office (that's you), the kitchen and
 *                ping pong
 */

export const TILE = 16;
export const COLS = 32;
export const ROWS = 18;
export const WIDTH = COLS * TILE;
export const HEIGHT = ROWS * TILE;
export const WALL = 3; // rows of wall at the top

export type Tile = { x: number; y: number };
export type Face = "down" | "up" | "left" | "right";
/** A place to stand (pixel position of the feet) and which way to face there. */
export type Spot = { x: number; y: number; face: Face; tile: Tile; sit?: boolean };

export const tileSpot = (tx: number, ty: number, face: Face = "down", dx = 0, dy = 0, sit = false): Spot => ({
  x: tx * TILE + 8 + dx, y: ty * TILE + 13 + dy, face, tile: { x: tx, y: ty }, sit,
});

// Desk pairs (left tile column) and their rows: two rows of five
export const DESKS: { col: number; row: number }[] = [5, 10].flatMap((row) => [9, 12, 15, 18, 21].map((col) => ({ col, row })));

/** Where an employee sits at desk i: on the chair just south of it, facing their monitors. */
export const chairSpot = (i: number): Spot => {
  const d = DESKS[i % DESKS.length];
  return tileSpot(d.col, d.row + 1, "up", 8, -1, true);
};

type Rect = { x: number; y: number; w: number; h: number };
const r = (x: number, y: number, w = 1, h = 1): Rect => ({ x, y, w, h });

export const BLOCKED: Rect[] = [
  r(0, 0, COLS, WALL),
  // conference room: glass on the right (col 7) and bottom (row 8, door at col 4)
  r(7, 3, 1, 5), r(0, 8, 4), r(5, 8, 3),
  r(2, 5, 4, 2), // conference table
  // lounge
  r(1, 10, 4), // TV console
  r(1, 13, 4), // couch
  r(6, 10, 2), // arcade cabinets
  r(0, 15, 1, 3), // aquarium
  r(0, 10), r(7, 17), // plants
  // trading floor
  ...DESKS.map((d) => r(d.col, d.row, 2)),
  r(8, 3), // printer
  r(21, 3), r(22, 3), // the bell, server rack
  r(22, 13), // water cooler
  r(8, 8), r(21, 8), // trash cans
  r(8, 17), r(22, 17), // plants
  r(10, 17, 3), // the bench
  r(14, 17, 2), // elevator
  // manager's office: glass on the left (col 23, door at row 6) and bottom (row 8)
  r(23, 3, 1, 3), r(23, 7, 1, 2), r(24, 8, 8),
  r(26, 5, 3), // manager's desk
  r(27, 4), // the big chair
  r(24, 3), // safe
  r(31, 3), // plant
  r(30, 7), // golden bull
  r(31, 5, 1, 2), // leather sofa
  // kitchen
  r(31, 10, 1, 5), // coffee, sink, fridge, vending, snacks
  r(24, 10), // water cooler
  r(25, 12, 3), // island
  r(25, 15, 3, 2), // ping pong table
  r(31, 17), // plant
];

export const walkable: boolean[][] = Array.from({ length: ROWS }, (_, y) =>
  Array.from({ length: COLS }, (_, x) => !BLOCKED.some((b) => x >= b.x && x < b.x + b.w && y >= b.y && y < b.y + b.h)),
);

export const SPOTS = {
  coffee: tileSpot(30, 10, "right"),
  sink: tileSpot(30, 11, "right"),
  fridge: tileSpot(30, 12, "right"),
  vending: tileSpot(30, 13, "right"),
  snacks: tileSpot(30, 14, "right"),
  cooler: [tileSpot(24, 11, "up"), tileSpot(25, 10, "left"), tileSpot(21, 13, "right"), tileSpot(22, 14, "up")],
  island: [tileSpot(25, 11, "down"), tileSpot(26, 11, "down"), tileSpot(27, 13, "up"), tileSpot(26, 13, "up")],
  windows: [tileSpot(9, 3, "up"), tileSpot(10, 3, "up"), tileSpot(11, 3, "up"), tileSpot(28, 3, "up"), tileSpot(29, 3, "up")],
  board: [tileSpot(13, 3, "up"), tileSpot(15, 3, "up"), tileSpot(16, 3, "up"), tileSpot(18, 3, "up"), tileSpot(14, 4, "up"), tileSpot(17, 4, "up")],
  bell: tileSpot(20, 3, "right"),
  aquarium: [tileSpot(1, 16, "left"), tileSpot(1, 15, "left")],
  printer: tileSpot(9, 4, "left", -4),
  servers: tileSpot(22, 4, "up"),
  elevator: [tileSpot(14, 16, "down"), tileSpot(15, 16, "down")],
  pingpong: [tileSpot(24, 15, "right", 0, 8), tileSpot(28, 15, "left", 0, 8)],
  couch: [1, 2, 3, 4].map((x) => tileSpot(x, 13, "up", 0, -2, true)),
  tv: [tileSpot(2, 11, "up"), tileSpot(3, 12, "up")],
  arcade: [tileSpot(6, 11, "up"), tileSpot(7, 11, "up")],
  beanbags: [tileSpot(5, 15, "up", 0, 0, true), tileSpot(6, 16, "left", 0, 0, true)],
  bench: [10, 11, 12].map((x) => tileSpot(x, 16, "down", 0, 9, true)),
  conference: [
    ...[2, 3, 4, 5].map((x) => tileSpot(x, 4, "down", 0, 2, true)),
    ...[2, 3, 4, 5].map((x) => tileSpot(x, 7, "up", 0, -3, true)),
  ],
  whiteboard: tileSpot(3, 3, "up", 8),
  bull: tileSpot(29, 7, "right"),
  boss: [tileSpot(27, 6, "up"), tileSpot(26, 6, "up")],
  sofa: tileSpot(30, 5, "right"),
  stage: tileSpot(15, 14, "down", 8),
  rug: [] as Spot[],
};

/** Open floor tiles, for wandering, pacing, parties and fire drills. */
export const OPEN: Tile[] = walkable.flatMap((row, y) => row.flatMap((ok, x) => (ok && y >= WALL ? [{ x, y }] : [])));
/** The big open middle of the trading floor. */
export const PIT: Tile[] = OPEN.filter((t) => t.x >= 9 && t.x <= 21 && ((t.y >= 7 && t.y <= 9) || (t.y >= 12 && t.y <= 15)));
SPOTS.rug = OPEN.filter((t) => t.x >= 13 && t.x <= 18 && t.y >= 13 && t.y <= 15).map((t) => tileSpot(t.x, t.y, "down"));

/** Shortest walk between two tiles (4 directions), as a list of tiles after the start. */
export function findPath(from: Tile, to: Tile): Tile[] {
  if (from.x === to.x && from.y === to.y) return [];
  const key = (t: Tile) => t.y * COLS + t.x;
  const prev = new Map<number, number>();
  const seen = new Set<number>([key(from)]);
  const queue: Tile[] = [from];
  const goal = key(to);
  for (let qi = 0; qi < queue.length; qi++) {
    const cur = queue[qi];
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
