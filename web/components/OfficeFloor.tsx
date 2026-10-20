"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { Point } from "@/lib/types";
import { dollars, shortName } from "@/lib/format";
import {
  BOARD, drawArcade, drawBell, drawClock, drawFish, drawMonitors, drawServers, paintRoom, PIECES, rect, skyFor,
  WHITEBOARD, WINDOWS, type Sky,
} from "@/lib/office/draw";
import { chairSpot, DESKS, findPath, HEIGHT, OPEN, PIT, SPOTS, TILE, tileSpot, WALL, WIDTH, type Spot, type Tile } from "@/lib/office/map";
import { lookFor, spriteCanvas, walker, type Dir, type Step } from "@/lib/office/walkers";
import Avatar from "./Avatar";

export type Mood = "celebrating" | "stressed" | "trading" | "watching" | "coffee" | "sleeping" | "benched" | "fired";

export type FloorPerson = {
  key: string;
  name: string;
  pnl: number;
  mood: Mood;
  line: string;
  lastFillTs: string | null;
  lastBet: string | null;
  pnlLastHour: number;
};

// ---------------------------------------------------------------------------
// People
// ---------------------------------------------------------------------------

type Kind =
  | "desk" | "phone" | "coffee" | "cooler" | "window" | "board" | "aquarium" | "vending" | "fridge" | "snacks"
  | "printer" | "servers" | "pingpong" | "couch" | "tv" | "arcade" | "beanbag" | "bench" | "restroom" | "visit"
  | "pace" | "bell" | "bull" | "boss" | "meeting" | "present" | "island" | "pushups" | "toss" | "highfive"
  | "party" | "huddle" | "dance" | "rush" | "chase" | "leave" | "skate" | "stage" | "cheer" | "fetch" | "conga"
  | "nerf" | "gawk" | "game";

type Agent = {
  key: string;
  name: string;
  desk: number;
  npc?: boolean;
  x: number;
  y: number;
  tile: Tile;
  face: "down" | "up" | "left" | "right";
  path: Tile[];
  target: Spot | null;
  kind: Kind;
  until: number;
  dur: number;
  arrived: boolean;
  speed: number;
  walkT: number;
  bubble: { text: string; until: number } | null;
  nextChat: number;
  carry: "mug" | "phone" | "champagne" | "megaphone" | "pizza" | "cake" | "snack" | "blaster" | null;
  mood: Mood;
  pnl: number;
  busyUntil: number;
  hidden: boolean;
  gone?: boolean;
  partner?: string;
  leader?: string; // conga line: who they follow
  spotlight: number; // when they last did something worth watching
};

type Particle = {
  x: number; y: number; vx: number; vy: number; life: number; max: number;
  kind: "confetti" | "bill" | "balloon" | "foam" | "pop" | "coin" | "plane" | "note" | "cork" | "fish" | "dart" | "paper" | "spark";
  color: string; seed: number;
};

type EventKind =
  | "balloons" | "confetti" | "money" | "toast" | "skates" | "huddle" | "disco" | "pizza" | "outage"
  | "espresso" | "planes" | "pigeon" | "pep" | "fish" | "band" | "conga" | "nerf" | "cake" | "pushups";

const EVENT_SECS: Record<EventKind, number> = {
  balloons: 14, confetti: 8, money: 12, toast: 10, skates: 18, huddle: 12, disco: 18, pizza: 28, outage: 9,
  espresso: 14, planes: 12, pigeon: 16, pep: 16, fish: 11, band: 22, conga: 20, nerf: 14, cake: 24, pushups: 14,
};
const EVENT_KINDS = Object.keys(EVENT_SECS) as EventKind[];

const CHATTER: Record<string, string[]> = {
  coffee: ["Coffee number four.", "Who used the last oat milk?", "Decaf is a scam.", "This tastes like fees."],
  cooler: ["Did you see bitcoin just now?", "I'm basically a genius.", "Hydrate or die-drate.", "Heard Dan beat the Sniper today.", "Fifteen minutes is forever in crypto."],
  window: ["One day, a corner office.", "Bull or bear out there?", "Rain means volatility.", "Nice day to buy the dip."],
  board: ["Up, up, up!", "Come on, green candle…", "That chart is spicy.", "Read 'em and weep."],
  aquarium: ["Hi Gordon.", "The fish has better returns than me.", "Blub blub."],
  vending: ["Out of chips AGAIN.", "Snack o'clock.", "Stress snack. It's fine."],
  fridge: ["Who ate my sandwich?!", "Something in here is alive."],
  snacks: ["Trail mix for the trail.", "Just one more cookie."],
  printer: ["PC LOAD LETTER?!", "Why is it always jammed?", "Who prints things anymore?"],
  servers: ["Have you tried turning it off and on?", "So many blinky lights."],
  pace: ["Breathe…", "It'll bounce. It'll bounce.", "Okay okay okay.", "It's just variance."],
  phone: ["Yeah. Yeah. Buy it.", "No, the OTHER bitcoin.", "I'll call you back!", "Mom, I'm at work."],
  desk: ["Locked in.", "Watching the tape.", "Hmm…", "Spreadsheet time.", "Refresh. Refresh. Refresh."],
  trading: ["BUY! BUY! BUY!", "Get me in!", "Send it!", "Locked in."],
  celebrating: ["WINNER!", "Pay me!", "Ka-ching!", "Who's the best? ME!"],
  stressed: ["Ugh.", "Why did I do that?", "Nobody talk to me.", "My portfolio…"],
  couch: ["Zzz…", "*snore*", "Five more minutes…"],
  tv: ["Turn it up!", "They're talking about us!", "Pundits, man."],
  arcade: ["New high score!", "One more credit…", "This is research."],
  beanbag: ["I live here now.", "Ahh."],
  bench: ["Put me in, coach!", "This bench is cold.", "I'll be back."],
  game: ["King me!", "Your move.", "That's not how the knight moves.", "Best of three?", "Do Monopoly dollars count?", "No take-backs!"],
  visit: ["Nice trade!", "You're up how much?", "Lend me five bucks?", "Teach me your ways."],
  bull: ["Rub the bull for luck.", "Shiny."],
  boss: ["About that raise…", "Got a minute, boss?", "I have an idea."],
  meeting: ["Let's circle back.", "Per my last email…", "Can everyone see my screen?", "Synergy!", "Who has the clicker?"],
  island: ["Good fruit today.", "Is this anyone's?", "Banana for Dan."],
  monkey: ["Ook ook!", "🍌?", "Ook."],
};
const pick = <T,>(xs: T[]) => xs[Math.floor(Math.random() * xs.length)];
const rand = (a: number, b: number) => a + Math.random() * (b - a);
const now = () => performance.now() / 1000;

const ACTIVITY: Record<Kind, string> = {
  desk: "at their desk", phone: "on the phone", coffee: "making coffee", cooler: "at the water cooler", window: "staring out the window",
  board: "watching the big board", aquarium: "visiting Gordon the goldfish", vending: "at the vending machine", fridge: "raiding the fridge",
  snacks: "at the snack shelf", printer: "fighting the printer", servers: "poking the servers", pingpong: "playing ping pong",
  couch: "on the couch", game: "playing a board game in the conference room", tv: "watching TV", arcade: "playing arcade games", beanbag: "in a beanbag", bench: "on the bench",
  restroom: "on a break", visit: "visiting a coworker", pace: "pacing", bell: "ringing the bell", bull: "rubbing the golden bull",
  boss: "in your office", meeting: "in a meeting", present: "presenting in a meeting", island: "at the kitchen island",
  pushups: "doing push-ups", toss: "shooting paper balls", highfive: "high-fiving", party: "celebrating", huddle: "in the hype huddle",
  dance: "dancing", rush: "running around", chase: "chasing something", leave: "heading out", skate: "skating",
  stage: "giving a speech", cheer: "cheering", fetch: "rescuing Gordon", conga: "in the conga line",
  nerf: "in a nerf war", gawk: "watching bitcoin move",
};

const CONFETTI = ["#f5c542", "#e74c3c", "#2ecc71", "#7fd3ff", "#c56cf0", "#ff9f43"];

type World = {
  agents: Agent[];
  particles: Particle[];
  event: { kind: EventKind; start: number; end: number; focus?: { x: number; y: number } } | null;
  nextEvent: number;
  ringing: number;
  roomba: { x: number; y: number; vx: number; vy: number };
  props: { pizza: number; cake: number; alert: number };
  seen: Record<string, string | null>;
  selected: string | null;
  hover: string | null;
  cam: { x: number; manualUntil: number; focus: string | null; switchAt: number };
  drag: { x: number; cx: number; moved: boolean } | null;
  reduced: boolean;
  sprites: Map<string, HTMLCanvasElement>;
  room: { base: HTMLCanvasElement; objects: HTMLCanvasElement; front: HTMLCanvasElement } | null;
  sky: Sky | null;
  font: string;
  lastTotal: number;
  scribble: number; // how much of the whiteboard chart is drawn
  clouds: { x: number; y: number; w: number }[];
  plane: number; // x position of a plane crossing the sky, or -1
};

// ---------------------------------------------------------------------------
// The component
// ---------------------------------------------------------------------------

export default function OfficeFloor({ people, total, btc, series, btcSeries }: {
  people: FloorPerson[];
  total: number;
  btc: number | null;
  series: Point[];
  btcSeries: Point[];
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const world = useRef<World | null>(null);
  const live = useRef({ people, total, btc, series, btcSeries });
  live.current = { people, total, btc, series, btcSeries };
  const [selected, setSelected] = useState<string | null>(null);
  const [, setTick] = useState(0);

  // ---------------- simulation helpers (they only touch refs) ----------------

  const say = (a: Agent, text: string, secs = 3.5) => {
    a.bubble = { text, until: now() + secs };
    a.spotlight = now();
  };

  const send = (a: Agent, spot: Spot, kind: Kind, dur: number) => {
    a.path = findPath(a.tile, spot.tile);
    a.target = spot;
    a.kind = kind;
    a.dur = dur;
    a.arrived = false;
    a.hidden = false;
    if (a.carry && !["mug", "snack"].includes(a.carry)) a.carry = null;
    if (world.current?.reduced) {
      a.x = spot.x; a.y = spot.y; a.tile = spot.tile; a.path = [];
    }
  };

  const openSpot = (from: Tile[] = OPEN) => {
    const t = pick(from);
    return tileSpot(t.x, t.y, pick(["down", "left", "right", "up"] as const));
  };

  // Bench seats first, then the beanbags and couch: more people can be benched than the bench seats
  const BENCHES: [Spot, Kind][] = [
    ...SPOTS.bench.map((s): [Spot, Kind] => [s, "bench"]),
    ...SPOTS.beanbags.map((s): [Spot, Kind] => [s, "beanbag"]),
    ...SPOTS.couch.map((s): [Spot, Kind] => [s, "couch"]),
  ];
  const benchSeat = (a: Agent | null, taken: Agent[]): [Spot, Kind] =>
    BENCHES.find(([s]) => !taken.some((b) => b !== a && b.target?.tile.x === s.tile.x && b.target?.tile.y === s.tile.y))
      ?? BENCHES[(a?.desk ?? 0) % BENCHES.length];

  const crewOf = (w: World) => w.agents.filter((a) => !a.npc && !a.gone && a.mood !== "benched" && a.mood !== "fired");

  const makeAgent = (key: string, name: string, desk: number, at: Spot, npc = false): Agent => ({
    key, name, desk, npc, x: at.x, y: at.y, tile: at.tile, face: at.face, path: [], target: at, kind: "desk",
    until: 0, dur: 0, arrived: true, speed: 34, walkT: 0, bubble: null, nextChat: now() + rand(3, 12),
    carry: null, mood: "watching", pnl: 0, busyUntil: 0, hidden: false, spotlight: 0,
  });

  /** What someone does next, weighted by what they're really doing on Kalshi. */
  const chooseTask = (a: Agent) => {
    const w = world.current!;
    if (a.npc) return;
    const desk = () => send(a, chairSpot(a.desk), "desk", rand(20, 50));
    const options: [number, () => void][] = [];
    const add = (weight: number, f: () => void) => weight > 0 && options.push([weight, f]);
    const others = w.agents.filter((b) => b !== a && !b.npc && !b.gone);
    const m = a.mood;
    const hour = new Date().getHours();
    const late = hour >= 23 || hour < 6;
    if (m === "benched") {
      // Off the trading floor: no desk, no phone, no big board. Breaks, games and snacks instead
      add(2, () => { const [seat, kind] = benchSeat(a, others); send(a, seat, kind, rand(20, 40)); });
      add(2, () => send(a, SPOTS.coffee, "coffee", rand(6, 10)));
      add(2, () => send(a, pick(SPOTS.cooler), "cooler", rand(8, 14)));
      add(1, () => send(a, pick(SPOTS.island), "island", rand(8, 14)));
      add(1, () => send(a, SPOTS.vending, "vending", rand(5, 9)));
      add(0.6, () => send(a, SPOTS.snacks, "snacks", rand(4, 7)));
      add(0.5, () => send(a, SPOTS.fridge, "fridge", rand(4, 7)));
      add(1, () => send(a, pick(SPOTS.aquarium), "aquarium", rand(6, 10)));
      add(1, () => send(a, pick(SPOTS.tv), "tv", rand(10, 20)));
      add(1.2, () => send(a, pick(SPOTS.arcade), "arcade", rand(10, 20)));
      add(1, () => send(a, pick(SPOTS.beanbags), "beanbag", rand(12, 25)));
      add(0.8, () => send(a, pick(SPOTS.windows), "window", rand(6, 12)));
      add(0.4, () => send(a, pick(SPOTS.elevator), "restroom", rand(8, 14)));
      // Games with another benchwarmer: a board game at the conference table, or ping pong
      const mates = others.filter((b) => b.mood === "benched" && b.arrived && !["game", "pingpong"].includes(b.kind));
      add(mates.length && !w.agents.some((b) => b.kind === "game") && !w.event ? 3 : 0, () => {
        const b = pick(mates);
        const dur = rand(30, 50);
        send(a, SPOTS.conference[1], "game", dur);
        send(b, SPOTS.conference[5], "game", dur);
        a.partner = b.key; b.partner = a.key;
        say(a, pick(["Board game?", "Checkers. Now.", "Loser buys coffee."]), 3);
      });
      add(mates.length && !w.agents.some((b) => b.kind === "pingpong") ? 1.5 : 0, () => {
        const b = pick(mates);
        const dur = rand(14, 22);
        send(a, SPOTS.pingpong[0], "pingpong", dur);
        send(b, SPOTS.pingpong[1], "pingpong", dur);
        a.partner = b.key; b.partner = a.key;
      });
    } else {
      const atDesk = { trading: 7, watching: 4, celebrating: 1, stressed: 2, coffee: 2, sleeping: 3, fired: 0, benched: 0 }[m];
      const chill = m === "coffee" || m === "sleeping" ? 2 : 1;
      add(atDesk, desk);
      add(m === "watching" || m === "trading" ? 2 : 0.5, () => { send(a, openSpot(PIT), "phone", rand(6, 12)); a.carry = "phone"; });
      add(chill * 1.5, () => send(a, SPOTS.coffee, "coffee", rand(5, 9)));
      add(chill * 1.5, () => send(a, pick(SPOTS.cooler), "cooler", rand(8, 14)));
      add(1, () => send(a, pick(SPOTS.island), "island", rand(8, 14)));
      add(m === "watching" || m === "stressed" ? 2 : 1, () => send(a, pick(SPOTS.windows), "window", rand(6, 12)));
      add(m === "trading" || m === "watching" ? 2 : 1, () => send(a, pick(SPOTS.board), "board", rand(6, 12)));
      add(chill * 0.6, () => send(a, pick(SPOTS.aquarium), "aquarium", rand(6, 10)));
      add(m === "stressed" ? 2 : 0.5, () => send(a, SPOTS.vending, "vending", rand(5, 8)));
      add(0.4, () => send(a, SPOTS.fridge, "fridge", rand(4, 7)));
      add(0.4, () => send(a, SPOTS.snacks, "snacks", rand(4, 7)));
      add(0.4, () => send(a, SPOTS.printer, "printer", rand(5, 9)));
      add(0.2, () => send(a, SPOTS.servers, "servers", rand(5, 9)));
      add(0.4, () => send(a, pick(SPOTS.elevator), "restroom", rand(8, 14)));
      add(0.5, () => send(a, SPOTS.bull, "bull", rand(4, 7)));
      add(0.4, () => send(a, pick(SPOTS.boss), "boss", rand(6, 10)));
      add(chill * 0.6, () => send(a, pick(SPOTS.tv), "tv", rand(8, 16)));
      add(chill * 0.6, () => send(a, pick(SPOTS.arcade), "arcade", rand(10, 20)));
      add(chill * 0.5, () => send(a, pick(SPOTS.beanbags), "beanbag", rand(12, 25)));
      add(m === "sleeping" ? 5 : late ? 2 : 0.4, () => send(a, SPOTS.couch[a.desk % 4], "couch", rand(25, 50)));
      add(m === "stressed" ? 3 : m === "watching" ? 1.5 : 0.5, () => send(a, openSpot(), "pace", rand(3, 6)));
      add(m === "stressed" ? 1.5 : 0.4, () => send(a, tileSpot(DESKS[a.desk].col - 1, DESKS[a.desk].row + 2, "left"), "toss", rand(5, 8)));
      add(m === "celebrating" ? 4 : 0, () => send(a, SPOTS.bell, "bell", 4));
      add(m === "celebrating" ? 2 : 0.2, () => send(a, pick(SPOTS.rug), "pushups", rand(6, 10)));
      const atDesks = others.filter((b) => b.kind === "desk" && b.arrived);
      add(atDesks.length ? (m === "coffee" || m === "celebrating" ? 2 : 0.7) : 0, () => {
        const b = pick(atDesks);
        const d = DESKS[b.desk];
        send(a, tileSpot(d.col - 1, d.row + 1, "right"), "visit", rand(6, 10));
        a.partner = b.key;
      });
      const free = others.filter((b) => ["cooler", "window", "aquarium", "pace", "board", "island", "tv"].includes(b.kind) && b.mood !== "benched");
      add(free.length && !w.agents.some((b) => b.kind === "pingpong") ? chill : 0, () => {
        const b = pick(free);
        const dur = rand(14, 22);
        send(a, SPOTS.pingpong[0], "pingpong", dur);
        send(b, SPOTS.pingpong[1], "pingpong", dur);
        a.partner = b.key; b.partner = a.key;
        if (Math.random() < 0.5) say(b, "You're going down.");
      });
      // a meeting: two or three people in the conference room, one presenting
      add(free.length >= 1 && !w.agents.some((b) => b.kind === "meeting" || b.kind === "present") ? 0.8 : 0, () => {
        const group = [a, ...free.slice(0, 2)];
        const dur = rand(20, 35);
        send(a, SPOTS.whiteboard, "present", dur);
        group.slice(1).forEach((b, i) => send(b, SPOTS.conference[(i * 3 + 1) % SPOTS.conference.length], "meeting", dur));
        w.scribble = 0;
      });
    }
    let r = Math.random() * options.reduce((s, [wt]) => s + wt, 0);
    for (const [wt, f] of options) {
      if ((r -= wt) <= 0) { f(); return; }
    }
    desk();
  };

  const spawn = (p: Omit<Particle, "seed">) => world.current!.particles.push({ ...p, seed: Math.random() * 100 });
  const burst = (x: number, y: number, n: number, kind: Particle["kind"], colors: string[], speed = 60) => {
    for (let i = 0; i < n; i++) {
      const ang = rand(0, Math.PI * 2), v = rand(speed * 0.3, speed);
      spawn({ x, y, vx: Math.cos(ang) * v, vy: Math.sin(ang) * v - speed * 0.6, life: 0, max: rand(1.2, 2.6), kind, color: pick(colors) });
    }
  };

  const startEvent = (kind: EventKind) => {
    const w = world.current;
    if (!w) return;
    const t = now();
    const crew = crewOf(w);
    if (!crew.length) return;
    const secs = EVENT_SECS[kind];
    const star = [...crew].sort((a, b) => b.pnl - a.pnl)[0];
    const dan = crew.find((a) => a.key === "dart_monkey");
    w.event = { kind, start: t, end: t + secs };
    const gather = (k: Kind, tiles: Tile[], dur: number) =>
      crew.forEach((a) => { const tt = pick(tiles); send(a, tileSpot(tt.x, tt.y, "down"), k, dur); });
    const focus = (x: number, y: number) => { w.event!.focus = { x, y }; };

    switch (kind) {
      case "balloons":
        for (let i = 0; i < 70; i++) spawn({ x: rand(6, WIDTH - 6), y: HEIGHT + rand(0, 120), vx: 0, vy: -rand(22, 40), life: 0, max: 16, kind: "balloon", color: pick(CONFETTI) });
        crew.forEach((a) => Math.random() < 0.5 && say(a, pick(["BALLOONS!", "Who did this?!", "Woooo!", "🎈🎈🎈"])));
        break;
      case "confetti":
        burst(BOARD.x + BOARD.w / 2, BOARD.y + BOARD.h, 160, "confetti", CONFETTI, 95);
        setTimeout(() => burst(BOARD.x + BOARD.w / 2, BOARD.y + BOARD.h, 110, "confetti", CONFETTI, 85), 1500);
        crew.forEach((a) => Math.random() < 0.4 && say(a, pick(["WOOO!", "Yeah!!", "Confetti!"])));
        focus(BOARD.x + BOARD.w / 2, 120);
        break;
      case "money":
        crew.forEach((a) => { send(a, openSpot(), "party", secs); if (Math.random() < 0.6) say(a, pick(["MINE!", "Make it rain!", "Free money!", "Is this taxable?"])); });
        break;
      case "toast":
        send(star, SPOTS.stage, "stage", secs - 1);
        star.carry = "champagne";
        crew.filter((a) => a !== star).forEach((a) => { send(a, openSpot(PIT), "cheer", secs - 1); a.carry = "champagne"; });
        focus(SPOTS.stage.x, SPOTS.stage.y);
        break;
      case "skates": {
        const rider = dan ?? pick(crew);
        rider.speed = 100;
        send(rider, openSpot(), "skate", secs);
        say(rider, rider.key === "dart_monkey" ? "OOK OOK WHEEEE!" : "WHEEEEE!", 3);
        crew.filter((a) => a !== rider).slice(0, 3).forEach((a, i) => setTimeout(() => say(a, pick(["Is that a monkey on skates?!", "Not in the office!", "LOL", "Who gave him skates?"])), 900 + i * 1300));
        rider.spotlight = t + 100;
        break;
      }
      case "huddle":
        gather("huddle", SPOTS.rug.map((s) => s.tile), secs);
        focus(SPOTS.stage.x, SPOTS.stage.y);
        break;
      case "disco":
        gather("dance", PIT, secs);
        focus(15 * TILE, 10 * TILE);
        break;
      case "pizza": {
        const guy = makeAgent("pizza", "Pizza Guy", 0, SPOTS.elevator[0], true);
        guy.carry = "pizza";
        w.agents.push(guy);
        send(guy, tileSpot(26, 11, "down"), "rush", 3);
        say(guy, "Pizza for… Kalshi Desk?");
        guy.spotlight = t + 100;
        break;
      }
      case "outage":
        crew.forEach((a) => { if (Math.random() < 0.5) say(a, pick(["Who turned off the lights?!", "My trades!", "Don't panic!", "Is it the servers?"])); a.speed = 20; });
        break;
      case "espresso":
        crew.forEach((a) => { a.speed = 85; send(a, openSpot(), "rush", secs); });
        crew.forEach((a, i) => setTimeout(() => say(a, pick(["TRIPLE ESPRESSO!", "I CAN HEAR COLORS", "BUY EVERYTHING", "I feel INVINCIBLE", "Is my heart supposed to do this?"])), i * 600));
        break;
      case "planes":
        for (let i = 0; i < 16; i++) {
          const a = pick(crew);
          setTimeout(() => spawn({ x: a.x, y: a.y - 14, vx: rand(-80, 80), vy: rand(-25, 10), life: 0, max: 3.5, kind: "plane", color: "#ffffff" }), i * 600);
        }
        crew.forEach((a) => Math.random() < 0.5 && say(a, pick(["Incoming!", "Take that!", "Direct hit!", "My eye!"])));
        break;
      case "pigeon": {
        const bird = makeAgent("pigeon", "Pigeon", 0, tileSpot(10, 3, "down"), true);
        bird.speed = 45;
        w.agents.push(bird);
        send(bird, openSpot(PIT), "pace", 2);
        crew.slice(0, 3).forEach((a) => { a.speed = 60; send(a, openSpot(PIT), "chase", secs - 2); say(a, pick(["Get it!", "It's going for my sandwich!", "Shoo! SHOO!"])); });
        bird.spotlight = t + 100;
        break;
      }
      case "pep":
        send(star, SPOTS.stage, "stage", secs);
        star.carry = "megaphone";
        crew.filter((a) => a !== star).forEach((a) => send(a, openSpot(PIT), "cheer", secs));
        focus(SPOTS.stage.x, SPOTS.stage.y);
        break;
      case "fish": {
        spawn({ x: 8, y: 15 * TILE + 8, vx: 22, vy: -50, life: 0, max: secs, kind: "fish", color: "#f39c12" });
        const hero = [...crew].sort((a, b) => Math.hypot(a.x - 30, a.y - 260) - Math.hypot(b.x - 30, b.y - 260))[0];
        hero.speed = 65;
        send(hero, tileSpot(2, 16, "left"), "fetch", 3);
        say(hero, "Gordon, NO!");
        focus(40, 250);
        break;
      }
      case "band":
        for (let i = 0; i < 3; i++) {
          const m = makeAgent("band", "Band", 0, SPOTS.elevator[i % 2], true);
          m.speed = 24;
          w.agents.push(m);
          setTimeout(() => send(m, tileSpot(11 + i * 3, 8, "left"), "pace", 2), i * 700);
        }
        crew.forEach((a) => Math.random() < 0.5 && say(a, pick(["Is that… a marching band?", "Who ordered this?", "BEST. DAY. EVER.", "♪ ♪ ♪"])));
        focus(15 * TILE, 9 * TILE);
        break;
      case "conga": {
        const line = [...crew].sort(() => Math.random() - 0.5);
        line.forEach((a, i) => {
          a.kind = "conga"; a.arrived = true; a.path = []; a.dur = secs;
          a.leader = i ? line[i - 1].key : undefined;
          a.speed = 30;
          a.until = t + secs;
        });
        send(line[0], openSpot(PIT), "conga", 0.2);
        say(line[0], "CONGA LINE!", 3);
        line[0].spotlight = t + 100;
        break;
      }
      case "nerf":
        crew.forEach((a, i) => {
          const side = i % 2 ? PIT.filter((p) => p.x < 14) : PIT.filter((p) => p.x > 17);
          send(a, openSpot(side.length ? side : PIT), "nerf", secs);
          a.carry = "blaster";
        });
        crew.forEach((a) => Math.random() < 0.4 && say(a, pick(["NERF WAR!", "You're going down!", "Cover me!"])));
        focus(15 * TILE, 9 * TILE);
        break;
      case "cake": {
        const baker = makeAgent("baker", "Baker", 0, SPOTS.elevator[1], true);
        baker.carry = "cake";
        w.agents.push(baker);
        send(baker, tileSpot(26, 11, "down"), "rush", 3);
        const who = pick(crew);
        const spots = SPOTS.island.concat(OPEN.filter((o) => o.x >= 23 && o.y >= 10 && o.y <= 14).map((o) => tileSpot(o.x, o.y, "right")));
        crew.forEach((a) => send(a, pick(spots), "cheer", secs));
        setTimeout(() => crew.forEach((a) => a !== who && Math.random() < 0.7 && say(a, `♪ Happy birthday, ${shortName(who.name)}! ♪`, 3)), 7000);
        setTimeout(() => say(who, "You guys! 🥹", 3), 11000);
        focus(26 * TILE, 12 * TILE);
        break;
      }
      case "pushups": {
        const [a, b] = [...crew].sort(() => Math.random() - 0.5);
        if (!b) break;
        send(a, SPOTS.rug[2], "pushups", secs);
        send(b, SPOTS.rug[SPOTS.rug.length - 3], "pushups", secs);
        crew.filter((c) => c !== a && c !== b).forEach((c) => send(c, openSpot(PIT.filter((p) => p.y >= 12)), "cheer", secs));
        say(a, "Push-up contest. NOW.");
        focus(SPOTS.stage.x, SPOTS.stage.y);
        break;
      }
    }
    w.nextEvent = t + secs + rand(40, 100);
  };

  // ---------------- set up the world once ----------------

  useEffect(() => {
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const t = now();
    const agents: Agent[] = [];
    live.current.people.filter((p) => p.mood !== "fired").forEach((p, i) => {
      const chair = chairSpot(i);
      const seat = p.mood === "benched" ? benchSeat(null, agents) : null;
      const start = seat ? seat[0] : p.mood === "sleeping" && i % 2 ? SPOTS.couch[i % 4] : Math.random() < 0.6 ? chair : openSpot();
      const a = makeAgent(p.key, p.name, i, start);
      a.mood = p.mood;
      a.pnl = p.pnl;
      a.kind = seat ? seat[1] : start === chair ? "desk" : start.sit ? "couch" : "pace";
      a.until = t + rand(2, 12);
      if (p.mood === "trading") a.busyUntil = t + 20;
      agents.push(a);
    });
    world.current = {
      agents, particles: [], event: null, nextEvent: t + rand(20, 40), ringing: 0,
      roomba: { x: 15 * TILE, y: 13 * TILE, vx: 14, vy: 9 }, props: { pizza: 0, cake: 0, alert: 0 },
      seen: Object.fromEntries(live.current.people.map((p) => [p.key, p.lastFillTs])),
      selected: null, hover: null, cam: { x: 7 * TILE, manualUntil: 0, focus: null, switchAt: 0 }, drag: null, reduced,
      sprites: new Map(), room: null, sky: null,
      font: getComputedStyle(document.body).getPropertyValue("--pixel").trim() || "monospace",
      lastTotal: live.current.total, scribble: 0,
      clouds: Array.from({ length: 6 }, () => ({ x: rand(0, WIDTH), y: rand(8, 22), w: rand(8, 18) })), plane: -1,
    };
    // #chaos=<event> starts that event right away (for previews)
    const forced = window.location.hash.match(/chaos=(\w+)/)?.[1] as EventKind | undefined;
    if (forced && forced in EVENT_SECS) setTimeout(() => startEvent(forced), 1500);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------------- new data from the server (every 30s) ----------------

  useEffect(() => {
    const w = world.current;
    if (!w) return;
    const t = now();
    for (const p of people) {
      const a = w.agents.find((x) => x.key === p.key);
      if (!a) continue;
      const prev = a.mood;
      a.mood = p.mood;
      a.pnl = p.pnl;
      if (p.lastFillTs && p.lastFillTs !== w.seen[p.key]) {
        w.seen[p.key] = p.lastFillTs;
        a.busyUntil = t + 25;
        if (a.kind !== "desk") send(a, chairSpot(a.desk), "desk", rand(20, 35));
        if (p.lastBet) say(a, pick(["BUY! ", "I'm in! ", "Send it! "]) + p.lastBet.replace(/^bet /, ""), 5);
        a.spotlight = t + 5;
      }
      if (p.mood === "celebrating" && prev !== "celebrating") {
        send(a, SPOTS.bell, "bell", 4);
        a.spotlight = t + 8;
        // a high-five from whoever is closest
        const buddy = crewOf(w).filter((b) => b !== a).sort((b1, b2) => Math.hypot(b1.x - a.x, b1.y - a.y) - Math.hypot(b2.x - a.x, b2.y - a.y))[0];
        if (buddy) setTimeout(() => send(buddy, tileSpot(SPOTS.bell.tile.x - 1, SPOTS.bell.tile.y + 1, "right"), "highfive", 3), 500);
      }
      if (p.mood === "stressed" && prev !== "stressed") say(a, pick(CHATTER.stressed), 4);
      if ((prev === "benched") !== (p.mood === "benched")) chooseTask(a);
    }
    if (total - w.lastTotal >= 10 && !w.event) startEvent(pick(["money", "confetti", "toast"] as EventKind[]));
    w.lastTotal = total;
    // bitcoin moving fast? everyone rushes to the board
    const bs = btcSeries;
    if (bs.length > 2) {
      const lastP = bs[bs.length - 1];
      const before = bs.find((p) => p.t >= lastP.t - 15 * 60_000) ?? bs[0];
      if (Math.abs(lastP.v / before.v - 1) >= 0.004 && t > w.props.alert + 600 && !w.event) {
        w.props.alert = t;
        const up = lastP.v > before.v;
        crewOf(w).forEach((a, i) => { send(a, SPOTS.board[i % SPOTS.board.length], "gawk", 12); if (i < 3) say(a, up ? "BITCOIN IS RIPPING!" : "BITCOIN IS DUMPING!", 4); });
        w.event = { kind: "huddle", start: t, end: t + 12, focus: { x: BOARD.x + BOARD.w / 2, y: 80 } };
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [people, total, btcSeries]);

  // ---------------- the animation loop ----------------

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    let raf = 0;
    let last = now();

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(canvas.clientWidth * dpr);
      canvas.height = Math.round(canvas.clientHeight * dpr);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const sprite = (a: Agent, dir: Dir, step: Step, sleepy: boolean) => {
      const w = world.current!;
      const id = `${a.key}|${dir}|${step}|${sleepy}`;
      let c = w.sprites.get(id);
      if (!c) {
        c = spriteCanvas(walker(lookFor(a.key), dir, step, { sleepy }));
        w.sprites.set(id, c);
      }
      return c;
    };

    const onArrive = (a: Agent, t: number) => {
      const w = world.current!;
      if (a.kind === "bell") { w.ringing = t + 3; say(a, "DING DING DING!", 3); burst(21 * TILE + 8, 3 * TILE, 40, "confetti", CONFETTI, 60); }
      if (a.kind === "highfive") { say(a, "UP TOP!", 2); spawn({ x: a.x + 6, y: a.y - 26, vx: 0, vy: -10, life: 0, max: 0.8, kind: "spark", color: "#fff3b0" }); }
      if (a.kind === "restroom") { a.hidden = true; setTimeout(() => say(a, pick(["*ding*", "Back!", "Miss me?"]), 2), (a.dur - 1.5) * 1000); }
      if (a.kind === "coffee") say(a, Math.random() < 0.5 ? pick(CHATTER.coffee) : "☕", 3);
      if (a.kind === "visit") {
        const b = w.agents.find((x) => x.key === a.partner);
        say(a, pick(CHATTER.visit));
        if (b) setTimeout(() => say(b, pick(["Thanks!", "Get your own!", "Shh, I'm working.", `Up ${dollars(Math.max(0, b.pnl))}, baby.`])), 1800);
      }
      if (a.kind === "fetch") {
        const fish = w.particles.find((p) => p.kind === "fish");
        if (fish) fish.life = fish.max;
        say(a, "Back you go, buddy.", 3);
      }
      if (a.kind === "couch" && a.mood === "sleeping") say(a, "Zzz…", 3);
      if (a.kind === "boss") say(a, pick(CHATTER.boss), 3);
      if (a.kind === "present") say(a, pick(["As you can see, line goes up.", "This is OUR quarter.", "Next slide please."]), 4);
    };

    const frame = () => {
      raf = requestAnimationFrame(frame);
      const w = world.current;
      if (!w) return;
      const t = now();
      const dt = Math.min(0.1, t - last);
      last = t;
      const date = new Date();
      // #hour=13 previews another time of day
      const sky = skyFor(Number(window.location.hash.match(/hour=(\d+)/)?.[1] ?? date.getHours()));
      if (!w.room || w.sky?.top !== sky.top) {
        w.room = paintRoom(sky);
        w.sky = sky;
      }

      // ---- simulate ----
      if (!w.reduced && !w.event && t > w.nextEvent) {
        const party = live.current.total >= 0;
        const pool = EVENT_KINDS.flatMap((k) => Array(party && ["balloons", "confetti", "money", "toast", "pep", "conga"].includes(k) ? 2 : 1).fill(k)) as EventKind[];
        startEvent(pick(pool));
      }
      const ev = w.event;
      if (ev && t > ev.end) {
        w.event = null;
        for (const a of w.agents) {
          if (a.npc) { if (!a.gone && a.kind !== "leave") send(a, pick(SPOTS.elevator), "leave", 0); continue; }
          a.speed = 34;
          a.leader = undefined;
          if (["huddle", "dance", "rush", "cheer", "party", "skate", "stage", "chase", "conga", "nerf", "gawk", "pushups"].includes(a.kind)) chooseTask(a);
        }
        if (ev.kind === "pep" || ev.kind === "toast") burst(SPOTS.stage.x, SPOTS.stage.y - 24, 90, "confetti", CONFETTI, 75);
      }

      for (const a of w.agents) {
        if (a.gone) continue;
        // conga: follow whoever is in front
        if (a.kind === "conga" && a.leader) {
          const lead = w.agents.find((b) => b.key === a.leader);
          if (lead) {
            const dx = lead.x - a.x, dy = lead.y - a.y, dist = Math.hypot(dx, dy);
            if (dist > 12) {
              const step = Math.min(dist - 12, a.speed * 1.4 * dt);
              a.x += (dx / dist) * step; a.y += (dy / dist) * step;
              a.face = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : dy > 0 ? "down" : "up";
              a.walkT += dt;
            }
            a.tile = { x: Math.floor(a.x / TILE), y: Math.max(WALL, Math.floor((a.y - 5) / TILE)) };
            if (a.bubble && t > a.bubble.until) a.bubble = null;
            continue;
          }
        }
        if (!a.arrived && a.target) {
          const next = a.path[0];
          const tx = next ? next.x * TILE + 8 : a.target.x;
          const ty = next ? next.y * TILE + 13 : a.target.y;
          const dx = tx - a.x, dy = ty - a.y, dist = Math.hypot(dx, dy);
          const step = a.speed * dt;
          if (dist <= step) {
            a.x = tx; a.y = ty;
            if (next) a.tile = a.path.shift()!;
            else {
              a.arrived = true;
              a.face = a.target.face;
              a.until = t + a.dur;
              onArrive(a, t);
            }
          } else {
            a.x += (dx / dist) * step; a.y += (dy / dist) * step;
            a.face = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : dy > 0 ? "down" : "up";
            a.walkT += dt;
          }
        } else if (t > a.until) {
          if (a.npc) {
            if (a.kind === "leave") { a.gone = true; continue; }
            if ((a.key === "pizza" || a.key === "baker") && a.kind === "rush") {
              if (a.key === "pizza") w.props.pizza = t + 45; else w.props.cake = t + 30;
              a.carry = null;
              say(a, a.key === "pizza" ? "Enjoy!" : "Happy birthday!");
              send(a, pick(SPOTS.elevator), "leave", 0);
              if (a.key === "pizza") {
                crewOf(w).forEach((b) => {
                  const o = pick(OPEN.filter((q) => q.x >= 23 && q.y >= 10 && q.y <= 14));
                  send(b, tileSpot(o.x, o.y, "right"), "rush", 12);
                  if (Math.random() < 0.6) say(b, pick(["PIZZA!", "Dibs on pepperoni!", "Out of my way!", "🍕🍕🍕"]));
                });
              }
              continue;
            }
            if (w.event) send(a, openSpot(PIT), "pace", a.key === "pigeon" ? rand(0.3, 1.5) : 0.4);
            else send(a, pick(SPOTS.elevator), "leave", 0);
            continue;
          }
          if (["skate", "rush", "chase", "party"].includes(a.kind) && w.event) { send(a, openSpot(a.kind === "chase" ? PIT : OPEN), a.kind, 0.3); continue; }
          if (w.event && ["huddle", "dance", "cheer", "stage", "nerf", "gawk", "pushups", "conga"].includes(a.kind)) {
            a.until = t + 1;
            if (a.kind === "conga" && !a.leader) send(a, openSpot(PIT), "conga", 0.2);
            continue;
          }
          a.hidden = false;
          if (a.kind === "coffee") a.carry = "mug";
          else if (a.kind === "vending" || a.kind === "snacks" || a.kind === "fridge") a.carry = "snack";
          else if (a.kind === "desk") a.carry = null;
          chooseTask(a);
        }
        // little things people do while they're somewhere
        if (a.arrived && !w.reduced) {
          if (a.kind === "toss" && Math.random() < dt * 0.8) {
            spawn({ x: a.x - 4, y: a.y - 18, vx: -rand(30, 45), vy: -rand(40, 60), life: 0, max: 1.2, kind: "paper", color: "#f5f5f5" });
            if (Math.random() < 0.3) setTimeout(() => say(a, pick(["Swish!", "Air ball.", "Nothing but net."]), 1.5), 900);
          }
          if (a.kind === "nerf" && Math.random() < dt * 1.5) {
            spawn({ x: a.x, y: a.y - 14, vx: a.x < 15 * TILE ? 120 : -120, vy: rand(-15, 15), life: 0, max: 1.4, kind: "dart", color: "#ff9f43" });
          }
          if (a.kind === "printer" && Math.random() < dt * 0.6) spawn({ x: 8 * TILE + 8, y: 3 * TILE + 4, vx: rand(-20, 20), vy: -30, life: 0, max: 1.4, kind: "paper", color: "#ffffff" });
          if (a.mood === "celebrating" && Math.random() < dt * 1.5) spawn({ x: a.x, y: a.y - 22, vx: rand(-10, 10), vy: -25, life: 0, max: 1.2, kind: "coin", color: "#f5c542" });
        }
        // chatter
        if (t > a.nextChat && !a.npc) {
          a.nextChat = t + rand(9, 22);
          if (a.arrived && Math.random() < 0.55 && !a.bubble && w.event?.kind !== "outage") {
            const pool = a.key === "dart_monkey" && Math.random() < 0.5 ? CHATTER.monkey
              : a.kind === "desk" ? CHATTER[t < a.busyUntil ? "trading" : a.mood === "stressed" ? "stressed" : "desk"]
              : a.kind === "present" ? CHATTER.meeting
              : CHATTER[a.kind] ?? CHATTER[a.mood];
            if (pool) {
              const extra = live.current.btc && Math.random() < 0.15 ? [`Bitcoin's at ${dollars(live.current.btc).replace(/\.\d+$/, "")}!`] : [];
              const mine = Math.random() < 0.15 ? [`I'm ${a.pnl >= 0 ? "up" : "down"} ${dollars(Math.abs(a.pnl))}.`] : [];
              say(a, pick([...pool, ...extra, ...mine]));
            }
          }
        }
        if (a.bubble && t > a.bubble.until) a.bubble = null;
      }
      w.agents = w.agents.filter((a) => !a.gone);
      if (w.agents.some((a) => a.kind === "present" && a.arrived)) w.scribble = Math.min(1, w.scribble + dt / 20);

      // ongoing event effects
      if (ev && !w.reduced) {
        const et = t - ev.start;
        if (ev.kind === "money" && Math.random() < dt * 40) spawn({ x: rand(0, WIDTH), y: WALL * TILE, vx: rand(-6, 6), vy: rand(14, 24), life: 0, max: 12, kind: "bill", color: "#2ecc71" });
        if (ev.kind === "huddle") {
          const crew = w.agents.filter((a) => (a.kind === "huddle" || a.kind === "gawk") && a.arrived);
          if (crew.length && Math.random() < dt * 1.2) say(pick(crew), pick(["LET'S GO!", "WHO'S HUNGRY?!", "ONE MORE WINDOW!", "*clap clap clap*"]), 2);
        }
        if (ev.kind === "toast" && et > 3 && et < 6.5) {
          const a = w.agents.find((x) => x.kind === "stage" && x.arrived);
          if (a) {
            if (!a.bubble || !a.bubble.text.startsWith("POP")) { spawn({ x: a.x + 6, y: a.y - 22, vx: rand(-10, 10), vy: -130, life: 0, max: 2.5, kind: "cork", color: "#c79a1e" }); say(a, "POP! To us!", 3.5); }
            for (let i = 0; i < 4; i++) spawn({ x: a.x + 6, y: a.y - 20, vx: rand(-30, 30), vy: rand(-70, -30), life: 0, max: rand(0.6, 1.2), kind: "foam", color: "#fffbe6" });
          }
        }
        if (ev.kind === "pep") {
          const a = w.agents.find((x) => x.kind === "stage" && x.arrived);
          const lines = ["Listen up, desk!", "Who's hungry?!", "Bitcoin waits for NO ONE!", "Every window is a new chance!", "NOW GET BACK TO WORK!"];
          if (a) {
            const i = Math.floor((et - 2) / 2.6);
            if (i >= 0 && i < lines.length && a.bubble?.text !== lines[i]) {
              say(a, lines[i], 2.5);
              w.agents.filter((b) => b.kind === "cheer" && Math.random() < 0.3).forEach((b) => say(b, pick(["WOOO!", "YEAH!", "👏👏👏", "LET'S GO!"]), 2));
            }
          }
        }
        if (ev.kind === "band" && Math.random() < dt * 5) {
          const m = pick(w.agents.filter((a) => a.key === "band"));
          if (m) spawn({ x: m.x, y: m.y - 22, vx: rand(-8, 8), vy: -18, life: 0, max: 1.6, kind: "note", color: "#f5c542" });
        }
        if (ev.kind === "disco" && Math.random() < dt * 2) {
          const a = pick(w.agents.filter((x) => x.kind === "dance"));
          if (a && !a.bubble && Math.random() < 0.3) say(a, pick(["♪ Stayin' alive ♪", "Watch this move!", "💃", "🕺", "The robot!"]), 2);
        }
        if (ev.kind === "conga" && Math.random() < dt * 0.8) {
          const a = pick(w.agents.filter((x) => x.kind === "conga"));
          if (a && !a.bubble) say(a, pick(["♪ Da da da da da da DA ♪", "CONGA!", "Hey!"]), 2);
        }
      }
      if (w.ringing > t && Math.random() < dt * 6) spawn({ x: 21 * TILE + 8, y: 3 * TILE - 6, vx: rand(-15, 15), vy: -25, life: 0, max: 1.2, kind: "note", color: "#f5c542" });

      // roomba
      const rb = w.roomba;
      if (!w.reduced) {
        const nx = rb.x + rb.vx * dt, ny = rb.y + rb.vy * dt;
        const tt = { x: Math.floor(nx / TILE), y: Math.floor(ny / TILE) };
        const okTile = OPEN.some((o) => o.x === tt.x && o.y === tt.y);
        if (!okTile) { rb.vx = -rb.vx + rand(-4, 4); rb.vy = -rb.vy + rand(-4, 4); } else { rb.x = nx; rb.y = ny; }
      }
      // sky: clouds drift, the odd plane
      for (const cl of w.clouds) { cl.x += dt * 2; if (cl.x > WIDTH + 20) cl.x = -20; }
      if (w.plane < 0 && Math.random() < dt / 40) w.plane = 0;
      if (w.plane >= 0) { w.plane += dt * 25; if (w.plane > WIDTH + 20) w.plane = -1; }

      // particles
      for (const p of w.particles) {
        p.life += dt;
        if (p.kind === "balloon") {
          p.x += Math.sin(t * 1.5 + p.seed) * 8 * dt; p.y += p.vy * dt;
          if (p.y < WALL * TILE - 10) {
            p.life = p.max;
            for (let i = 0; i < 6; i++) w.particles.push({ x: p.x, y: p.y, vx: rand(-30, 30), vy: rand(-30, 30), life: 0, max: 0.4, kind: "pop", color: p.color, seed: 0 });
          }
          continue;
        }
        if (p.kind === "bill") { p.x += (p.vx + Math.sin(t * 3 + p.seed) * 10) * dt; p.y += p.vy * dt; if (p.y > HEIGHT) p.life = p.max; continue; }
        if (p.kind === "plane") { p.x += p.vx * dt; p.y += (p.vy + Math.sin(t * 4 + p.seed) * 20) * dt; continue; }
        if (p.kind === "dart") { p.x += p.vx * dt; p.y += p.vy * dt; continue; }
        if (p.kind === "fish") {
          if (p.y < 16 * TILE || p.vy < 0) { p.vy += 140 * dt; p.x += p.vx * dt; p.y += p.vy * dt; }
          else { p.vx = 0; p.vy = 0; if (p.life > 4) p.life = p.max; }
          continue;
        }
        p.vy += (p.kind === "note" || p.kind === "coin" || p.kind === "spark" ? -5 : 120) * dt;
        if (p.kind === "confetti") { p.vx *= 0.98; p.vy = Math.min(p.vy, 30); }
        p.x += p.vx * dt; p.y += p.vy * dt;
      }
      w.particles = w.particles.filter((p) => p.life < p.max).slice(-900);

      // ---- camera: fit the office's height; pan sideways on narrow screens ----
      const K = canvas.height / HEIGHT;
      const viewW = canvas.width / K;
      const cam = w.cam;
      if (viewW >= WIDTH) {
        cam.x = -(viewW - WIDTH) / 2;
      } else {
        let fx: number | null = null;
        const sel = w.selected ? w.agents.find((a) => a.key === w.selected) : null;
        if (sel) fx = sel.x;
        else if (t < cam.manualUntil) fx = null;
        else if (w.event?.focus) fx = w.event.focus.x;
        else {
          // the director: watch whoever is doing the most interesting thing, switching now and then
          const hot = [...w.agents].filter((a) => !a.hidden).sort((a, b) => b.spotlight - a.spotlight)[0];
          if (hot && hot.spotlight > t - 6) cam.focus = hot.key;
          else if (t > cam.switchAt) {
            const movers = w.agents.filter((a) => !a.hidden && (a.bubble || !a.arrived));
            cam.focus = pick(movers.length ? movers : w.agents)?.key ?? null;
            cam.switchAt = t + rand(10, 16);
          }
          const f = w.agents.find((a) => a.key === cam.focus);
          if (f) fx = f.x;
        }
        if (fx != null) cam.x += (fx - viewW / 2 - cam.x) * Math.min(1, dt * 1.8);
        cam.x = Math.max(0, Math.min(WIDTH - viewW, cam.x));
      }
      const ox = -cam.x * K;

      // ---- draw ----
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.fillStyle = "#14101f";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.setTransform(K, 0, 0, K, ox, 0);
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(w.room.base, 0, 0);
      drawSky(ctx, w, sky);
      drawBoard(ctx, live.current.series, live.current.total, t);
      drawWhiteboard(ctx, w.scribble);
      drawClock(ctx, date);
      drawBell(ctx, t, w.ringing > t);
      drawFish(ctx, t);
      drawServers(ctx, t);
      if (w.agents.some((a) => a.kind === "coffee" && a.arrived)) for (let i = 0; i < 3; i++) rect(ctx, 31 * TILE + 7 + i * 2, 10 * TILE - 6 - ((t * 8 + i * 3) % 7), 1, 1, "rgba(255,255,255,0.7)");
      rect(ctx, 15 * TILE - 2, 16 * TILE + 13, 4, 2, w.agents.some((a) => a.npc) ? "#f5c542" : "#5f6b7a"); // elevator light

      // roomba
      rect(ctx, rb.x - 5, rb.y - 3, 10, 6, "#14101f");
      rect(ctx, rb.x - 4, rb.y - 4, 8, 8, "#14101f");
      rect(ctx, rb.x - 4, rb.y - 2, 8, 4, "#3a3a48");
      rect(ctx, rb.x - 3, rb.y - 3, 6, 6, "#3a3a48");
      rect(ctx, rb.x - 1, rb.y - 1, 2, 2, Math.floor(t * 2) % 2 ? "#2ecc71" : "#145a32");

      // people and furniture together, back to front: nearer the bottom of the screen is drawn on top
      const room = w.room;
      const order = [...w.agents].filter((a) => !a.hidden).sort((a, b) => a.y - b.y);
      const layers: { y: number; k: number; draw: () => void }[] = order.map((a) => ({ y: a.y, k: 0, draw: () => drawAgent(ctx, a, t, sprite) }));
      for (const p of PIECES) {
        layers.push({ y: p.base, k: 1, draw: () => {
          ctx.drawImage(p.layer === "front" ? room.front : room.objects, p.x, p.y, p.w, p.h, p.x, p.y, p.w, p.h);
          if (p.live === "tv") drawTV(ctx, live.current.btcSeries, t);
          if (p.live === "arcade") drawArcade(ctx, t);
          if (p.live === "island") {
            if (w.props.pizza > t) drawPizza(ctx);
            if (w.props.cake > t) drawCake(ctx, t);
            if (w.event?.kind === "espresso") drawEspresso(ctx);
          }
          if (p.live === "desk" && p.desk !== undefined) {
            const a = w.agents.find((x) => !x.npc && x.desk === p.desk);
            drawMonitors(ctx, p.desk, a?.pnl ?? 0, !!a && t < a.busyUntil, t, !a);
          }
        } });
      }
      layers.sort((a, b) => a.y - b.y || a.k - b.k);
      for (const l of layers) l.draw();
      const game = w.agents.filter((a) => a.kind === "game" && a.arrived);
      if (game.length === 2) {
        // a checkerboard on the conference table, with a few pieces that shuffle now and then
        const bx = 3 * TILE + 2, by = 5 * TILE + 9;
        rect(ctx, bx - 1, by - 1, 14, 14, "#3b2412");
        for (let i = 0; i < 6; i++) for (let j = 0; j < 6; j++) rect(ctx, bx + i * 2, by + j * 2, 2, 2, (i + j) % 2 ? "#1a1a1a" : "#e8d5b0");
        const turn = Math.floor(t / 3);
        for (let n = 0; n < 4; n++) {
          const i = (n * 2 + turn + (n > 1 ? 1 : 0)) % 6, j = n < 2 ? n % 2 : 4 + (n % 2);
          rect(ctx, bx + i * 2, by + j * 2, 2, 2, n < 2 ? "#d63031" : "#f5f5f5");
        }
      }
      const pp = w.agents.filter((a) => a.kind === "pingpong" && a.arrived);
      if (pp.length === 2) {
        const k = (t % 1.1) / 1.1, there = k < 0.5 ? k * 2 : 2 - k * 2;
        rect(ctx, 25 * TILE + 2 + there * 44, 15 * TILE + 12 - Math.sin(there * Math.PI) * 8, 2, 2, "#ffffff");
      }

      // lighting
      const dark = w.event?.kind === "outage" ? 0.72 : w.event?.kind === "disco" ? 0.55 : sky.night ? 0.32 : 0;
      if (dark) {
        ctx.fillStyle = `rgba(6, 6, 30, ${dark})`;
        ctx.fillRect(0, 0, WIDTH, HEIGHT);
        ctx.globalCompositeOperation = "lighter";
        const glow = (x: number, y: number, r: number, color: string) => {
          const g = ctx.createRadialGradient(x, y, 1, x, y, r);
          g.addColorStop(0, color); g.addColorStop(1, "rgba(0,0,0,0)");
          ctx.fillStyle = g;
          ctx.fillRect(x - r, y - r, r * 2, r * 2);
        };
        if (w.event?.kind !== "outage") {
          for (const d of DESKS) glow(d.col * TILE + 16, d.row * TILE + 2, 26, "rgba(90, 200, 255, 0.22)");
          glow(3 * TILE, 10 * TILE - 2, 34, "rgba(120, 160, 255, 0.25)");
          glow(7 * TILE, 10 * TILE - 2, 22, "rgba(255, 120, 200, 0.2)");
          glow(BOARD.x + BOARD.w / 2, BOARD.y + BOARD.h, 60, "rgba(255, 210, 90, 0.12)");
        } else {
          for (const a of order.slice(0, 4)) glow(a.x + (a.face === "left" ? -14 : 14), a.y - 4, 18, "rgba(255, 250, 200, 0.35)");
        }
        if (w.event?.kind === "disco") {
          for (let i = 0; i < 12; i++) {
            const ang = t * 1.3 + i * 0.6;
            const x = 15 * TILE + Math.cos(ang * (1 + i * 0.06)) * (50 + i * 16), y = 9 * TILE + Math.sin(ang * 0.9) * (40 + i * 6);
            glow(x, y, 14, CONFETTI[i % CONFETTI.length] + "66");
          }
        }
        ctx.globalCompositeOperation = "source-over";
        if (w.event?.kind === "disco") {
          rect(ctx, 15 * TILE + 7, WALL * TILE, 1, 30, "#9aa8c7");
          for (let i = 0; i < 5; i++) for (let j = 0; j < 5; j++) rect(ctx, 15 * TILE + 3 + i * 2, WALL * TILE + 30 + j * 2, 2, 2, (i + j + Math.floor(t * 8)) % 2 ? "#ffffff" : "#9aa8c7");
        }
      }

      for (const p of w.particles) drawParticle(ctx, p, t);

      // crisp text: the big board's numbers and ticker, speech bubbles, the selected person's name
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      const dpr = window.devicePixelRatio || 1;
      const X = (x: number) => x * K + ox, Y = (y: number) => y * K;
      drawBoardText(ctx, live.current.total, live.current.btc, live.current.people, w.font, K, ox, t);
      const fontPx = Math.round(Math.max(9, Math.min(11, (K / dpr) * 4)) * dpr);
      ctx.font = `${fontPx}px ${w.font}`;
      ctx.textBaseline = "top";
      const sel = w.selected ?? w.hover;
      const maxW = 150 * dpr;
      for (const a of order) {
        const headY = a.y - (a.arrived && a.target?.sit ? 22 : 27);
        if (a.key === sel) {
          const bob = Math.round(Math.sin(t * 6) * 1.5) * K;
          ctx.fillStyle = "#f5c542";
          ctx.strokeStyle = "#14101f";
          ctx.lineWidth = Math.max(1, K / 2);
          ctx.beginPath(); ctx.moveTo(X(a.x) - 4 * K, Y(headY) + bob); ctx.lineTo(X(a.x) + 4 * K, Y(headY) + bob); ctx.lineTo(X(a.x), Y(headY) + 4 * K + bob); ctx.closePath(); ctx.fill(); ctx.stroke();
          if (!a.bubble) bubble(ctx, shortName(a.name), X(a.x), Y(headY) - 2 * K + bob, fontPx, K, maxW, true);
        }
        if (a.bubble) bubble(ctx, a.bubble.text, X(a.x), Y(headY), fontPx, K, maxW, false);
      }
    };

    raf = requestAnimationFrame(frame);
    const tick = setInterval(() => setTick((n) => n + 1), 5000); // refresh the "what they're doing" card
    return () => { cancelAnimationFrame(raf); ro.disconnect(); clearInterval(tick); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------------- input: tap someone to follow them, drag to look around ----------------

  const toFloor = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const K = box.height / HEIGHT;
    return { x: (world.current?.cam.x ?? 0) + (e.clientX - box.left) / K, y: (e.clientY - box.top) / K };
  };
  const at = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const { x, y } = toFloor(e);
    const w = world.current;
    if (!w) return null;
    let best: Agent | null = null, dist = 16;
    for (const a of w.agents) {
      if (a.npc || a.hidden) continue;
      const d = Math.hypot(a.x - x, a.y - 12 - y);
      if (d < dist) { dist = d; best = a; }
    }
    return best;
  };

  const sel = selected ? world.current?.agents.find((a) => a.key === selected) : null;
  const selPerson = selected ? people.find((p) => p.key === selected) : null;

  return (
    <div className="floor">
      <canvas
        ref={canvasRef}
        className="floor-canvas"
        role="img"
        aria-label="The office: employees walking around and acting out what they're doing on Kalshi"
        onPointerMove={(e) => {
          const w = world.current;
          if (!w) return;
          if (w.drag) {
            const box = e.currentTarget.getBoundingClientRect();
            const dx = (e.clientX - w.drag.x) / (box.height / HEIGHT);
            if (Math.abs(dx) > 4) w.drag.moved = true;
            if (w.drag.moved) { w.cam.x = w.drag.cx - dx; w.cam.manualUntil = now() + 8; w.selected = null; }
            return;
          }
          const a = at(e);
          w.hover = a?.key ?? null;
          e.currentTarget.style.cursor = a ? "pointer" : "default";
        }}
        onPointerLeave={() => { if (world.current) { world.current.hover = null; world.current.drag = null; } }}
        onPointerDown={(e) => { const w = world.current; if (w) w.drag = { x: e.clientX, cx: w.cam.x, moved: false }; }}
        onPointerUp={(e) => {
          const w = world.current;
          if (!w) return;
          const dragged = w.drag?.moved;
          w.drag = null;
          if (dragged) { setSelected(null); return; }
          const a = at(e);
          w.selected = a?.key ?? null;
          setSelected(a?.key ?? null);
        }}
      />
      {sel && selPerson && (
        <div className="floor-card">
          <Avatar k={sel.key} size={40} />
          <div>
            <strong>{selPerson.name}</strong> <span className="muted small">is {ACTIVITY[sel.kind]}.</span>
            <div className="small">
              <span className={selPerson.pnl > 0.004 ? "up" : selPerson.pnl < -0.004 ? "down" : "muted"}>{dollars(selPerson.pnl, true)}</span> so far ·{" "}
              <Link href={`/employee/${sel.key}`}>Their page →</Link>
            </div>
          </div>
          <button className="btn small" onClick={() => { if (world.current) world.current.selected = null; setSelected(null); }} aria-label="Stop following">✕</button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Drawing helpers
// ---------------------------------------------------------------------------

type SpriteFn = (a: Agent, dir: Dir, step: Step, sleepy: boolean) => HTMLCanvasElement;

function drawAgent(c: CanvasRenderingContext2D, a: Agent, t: number, sprite: SpriteFn) {
  if (a.key === "pigeon") {
    const hop = a.arrived ? 0 : Math.abs(Math.sin(t * 14)) * 2;
    const left = a.face === "left";
    rect(c, a.x - 4, a.y - 7 - hop, 8, 6, "#14101f");
    rect(c, a.x - 3, a.y - 6 - hop, 6, 4, "#8a93a6");
    rect(c, a.x + (left ? -5 : 2), a.y - 9 - hop, 4, 4, "#14101f");
    rect(c, a.x + (left ? -4 : 3), a.y - 8 - hop, 2, 2, "#5f6b7a");
    rect(c, a.x + (left ? -6 : 6), a.y - 7 - hop, 1, 1, "#f5c542");
    return;
  }
  const congaWalk = a.kind === "conga" && !!a.leader;
  const moving = !a.arrived || congaWalk;
  const sitting = a.arrived && !!a.target?.sit && a.kind !== "conga";
  const sleepy = a.mood === "sleeping" && sitting;
  let dir: Dir = a.face === "left" || a.face === "right" ? "side" : a.face;
  let flip = a.face === "left";
  const phase = Math.floor(a.walkT / 0.13) % 4;
  const step: Step = moving ? (phase === 1 ? 1 : phase === 3 ? 2 : 0) : 0;
  let bob = 0;
  if (a.arrived && ["huddle", "cheer", "party", "gawk"].includes(a.kind)) bob = Math.abs(Math.sin(t * 9 + a.desk)) * 3;
  if (a.kind === "dance" && a.arrived) { bob = Math.abs(Math.sin(t * 8 + a.desk)) * 3; dir = Math.floor(t * 2 + a.desk) % 3 === 0 ? "side" : "down"; flip = Math.floor(t * 2 + a.desk) % 2 === 0; }
  if (a.kind === "desk" && a.arrived && t < a.busyUntil) bob = Math.floor(t * 8 + a.desk) % 2;
  if (a.mood === "stressed" && a.arrived && a.kind === "desk") bob = Math.sin(t * 40) > 0 ? 1 : 0;
  if (["skate", "rush"].includes(a.kind)) bob = Math.abs(Math.sin(t * 16 + a.desk)) * 1.5;
  const img = sprite(a, dir, step, sleepy || (a.kind === "couch" && a.mood === "sleeping"));
  const x = Math.round(a.x - 8), y = Math.round(a.y - 23 - bob);

  if (!sitting) {
    c.fillStyle = "rgba(5,3,15,0.35)";
    c.fillRect(Math.round(a.x - 5), Math.round(a.y - 1), 10, 3);
    c.fillRect(Math.round(a.x - 4), Math.round(a.y - 2), 8, 5);
  }
  if (a.kind === "pushups" && a.arrived) {
    const up = Math.floor(t * 2.2 + a.desk) % 2;
    c.save();
    c.translate(Math.round(a.x), Math.round(a.y - 6 - up));
    c.rotate(Math.PI / 2);
    c.drawImage(img, -12, -8);
    c.restore();
    return;
  }
  const h = sitting && dir === "up" ? 18 : 24;
  const dy = sitting ? (dir === "up" ? 3 : -2) + (sleepy ? 2 : 0) : 0;
  c.save();
  if (flip) { c.translate(x * 2 + 16, 0); c.scale(-1, 1); }
  c.drawImage(img, 0, 0, 16, h, x, y + dy, 16, h);
  c.restore();
  if (a.kind === "skate") { rect(c, a.x - 6, a.y - 1, 5, 3, "#14101f"); rect(c, a.x + 1, a.y - 1, 5, 3, "#14101f"); rect(c, a.x - 5, a.y, 3, 1, "#e03c3c"); rect(c, a.x + 2, a.y, 3, 1, "#e03c3c"); }
  // what they're holding
  const hx = flip ? a.x - 9 : a.x + 6, hy = a.y - 10 - bob;
  const hold = (w: number, h2: number, col: string, ddx = 0, ddy = 0) => { rect(c, hx + ddx - 1, hy + ddy - 1, w + 2, h2 + 2, "#14101f"); rect(c, hx + ddx, hy + ddy, w, h2, col); };
  if (!sitting) {
    if (a.carry === "mug") hold(3, 3, "#ffffff");
    if (a.carry === "snack") hold(3, 4, "#f39c12");
    if (a.carry === "phone") hold(2, 4, "#2b2b36", flip ? 3 : -3, -8);
    if (a.carry === "champagne") { hold(2, 8, "#1e5631", 0, -6); rect(c, hx, hy - 7, 2, 1, "#f5c542"); }
    if (a.carry === "megaphone") { hold(4, 6, "#e03c3c", 0, -4); rect(c, hx - 1, hy - 2, 1, 3, "#f5f5f5"); }
    if (a.carry === "blaster") { hold(6, 3, "#ff9f43", flip ? -4 : 0, -2); rect(c, hx + (flip ? -3 : 1), hy - 1, 2, 1, "#2f5aa8"); }
  }
  if (a.carry === "pizza") { rect(c, a.x - 8, a.y - 13, 16, 5, "#14101f"); rect(c, a.x - 7, a.y - 12, 14, 3, "#e8c39e"); }
  if (a.carry === "cake") { rect(c, a.x - 7, a.y - 16, 14, 9, "#14101f"); rect(c, a.x - 6, a.y - 15, 12, 7, "#f8bbd0"); rect(c, a.x - 1, a.y - 19, 2, 3, "#f5c542"); }
  if (a.key === "band") { rect(c, a.x - 5, a.y - 12, 10, 7, "#14101f"); rect(c, a.x - 4, a.y - 11, 8, 5, "#f5f5f5"); rect(c, a.x - 4, a.y - 11, 8, 1, "#c0392b"); }
  if (sleepy || (a.kind === "couch" && a.mood === "sleeping" && a.arrived)) drawZ(c, a.x + 6, a.y - 24, t);
  if (a.mood === "stressed" && Math.floor(t * 2 + a.desk) % 3 !== 0 && !sitting) rect(c, a.x + 6, a.y - 22 + ((t * 10) % 4), 1, 2, "#7fd3ff");
  if (a.kind === "bench" && a.arrived) { rect(c, a.x - 7, a.y - 34, 14, 7, "#14101f"); rect(c, a.x - 6, a.y - 33, 12, 5, "#f5f5f5"); rect(c, a.x - 5, a.y - 31, 10, 1, "#c0392b"); }
}

function drawZ(c: CanvasRenderingContext2D, x: number, y: number, t: number) {
  for (let i = 0; i < 2; i++) {
    const k = (t * 0.8 + i * 0.5) % 1;
    const zx = x + i * 4 + k * 3, zy = y - k * 10;
    c.globalAlpha = 1 - k;
    rect(c, zx - 1, zy - 1, 5, 5, "#14101f");
    rect(c, zx, zy, 3, 1, "#ffffff"); rect(c, zx + 1, zy + 1, 1, 1, "#ffffff"); rect(c, zx, zy + 2, 3, 1, "#ffffff");
    c.globalAlpha = 1;
  }
}

function drawParticle(c: CanvasRenderingContext2D, p: Particle, t: number) {
  const fade = ["pop", "foam", "note", "coin", "spark", "paper"].includes(p.kind) ? 1 - p.life / p.max : 1;
  c.globalAlpha = Math.max(0, fade);
  switch (p.kind) {
    case "balloon":
      rect(c, p.x - 4, p.y - 6, 8, 9, "#14101f"); rect(c, p.x - 3, p.y - 7, 6, 11, "#14101f");
      rect(c, p.x - 3, p.y - 5, 6, 7, p.color); rect(c, p.x - 2, p.y - 6, 4, 9, p.color);
      rect(c, p.x - 2, p.y - 4, 1, 2, "rgba(255,255,255,0.7)");
      rect(c, p.x, p.y + 4, 1, 7, "#dddddd");
      break;
    case "bill":
      rect(c, p.x - 4, p.y - 2, 8, 5, "#14101f");
      rect(c, p.x - 3, p.y - 1, 6, 3, Math.sin(t * 6 + p.seed) > 0 ? "#2ecc71" : "#27ae60");
      rect(c, p.x - 1, p.y, 2, 1, "#145a32");
      break;
    case "plane":
      rect(c, p.x - 3, p.y, 7, 1, "#ffffff"); rect(c, p.x + (p.vx > 0 ? 1 : -2), p.y - 1, 2, 1, "#ffffff"); rect(c, p.x - 1, p.y + 1, 3, 1, "#cfd8dc");
      break;
    case "note":
      rect(c, p.x, p.y, 1, 4, p.color); rect(c, p.x - 2, p.y + 3, 2, 2, p.color); rect(c, p.x + 1, p.y, 2, 1, p.color);
      break;
    case "dart":
      rect(c, p.x - 2, p.y, 4, 1, "#ff9f43"); rect(c, p.x + (p.vx > 0 ? 2 : -3), p.y, 1, 1, "#2f5aa8");
      break;
    case "paper":
      rect(c, p.x - 1, p.y - 1, 3, 3, "#14101f"); rect(c, p.x, p.y, 2, 2, p.color);
      break;
    case "coin":
      rect(c, p.x - 1, p.y - 1, 4, 4, "#14101f"); rect(c, p.x, p.y, 2, 2, "#f5c542");
      break;
    case "cork":
      rect(c, p.x, p.y, 2, 2, p.color);
      break;
    case "fish":
      rect(c, p.x - 3, p.y - 3, 6, 5, "#14101f"); rect(c, p.x - 2, p.y - 2, 4, 3, p.color); rect(c, p.x + (Math.sin(t * 20) > 0 ? 2 : -3), p.y - 2, 1, 3, p.color);
      break;
    case "spark":
      rect(c, p.x - 2, p.y, 5, 1, p.color); rect(c, p.x, p.y - 2, 1, 5, p.color);
      break;
    default:
      rect(c, p.x, p.y, p.kind === "confetti" ? (Math.sin(t * 10 + p.seed) > 0 ? 2 : 1) : 2, 2, p.color);
  }
  c.globalAlpha = 1;
}

function drawSky(c: CanvasRenderingContext2D, w: World, sky: Sky) {
  for (const [x, wd] of WINDOWS) {
    c.save();
    c.beginPath(); c.rect(x, 7, wd, 31); c.clip();
    if (!sky.night) {
      for (const cl of w.clouds) { rect(c, cl.x, cl.y, cl.w, 3, "rgba(255,255,255,0.75)"); rect(c, cl.x + 2, cl.y - 2, cl.w - 5, 2, "rgba(255,255,255,0.75)"); }
    }
    if (w.plane >= 0) {
      const py = 14;
      if (sky.night) { if (Math.floor(performance.now() / 400) % 2) rect(c, w.plane, py, 1, 1, "#ff4444"); rect(c, w.plane + 3, py, 1, 1, "#ffffff"); }
      else { rect(c, w.plane, py, 7, 1, "#eef3f8"); rect(c, w.plane + 2, py - 1, 2, 3, "#eef3f8"); }
    }
    c.restore();
  }
}

/** The big board: the desk's profit as a line graph. Numbers are drawn crisply later. */
function drawBoard(c: CanvasRenderingContext2D, series: Point[], total: number, t: number) {
  const x0 = BOARD.x + 4, x1 = BOARD.x + BOARD.w - 4, y0 = BOARD.y + 13, y1 = BOARD.y + BOARD.h - 11;
  if (series.length > 1) {
    const ts = series.map((p) => p.t), vs = series.map((p) => p.v).concat(total, 0);
    const tmin = Math.min(...ts), tmax = Math.max(...ts), lo = Math.min(...vs), hi = Math.max(...vs);
    const X = (v: number) => x0 + ((v - tmin) / (tmax - tmin || 1)) * (x1 - x0);
    const Y = (v: number) => y1 - ((v - lo) / (hi - lo || 1)) * (y1 - y0);
    rect(c, x0, Math.round(Y(0)), x1 - x0, 1, "#2a2650");
    c.strokeStyle = total >= 0 ? "#2ecc71" : "#e74c3c";
    c.lineWidth = 1;
    c.beginPath();
    series.forEach((p, i) => (i ? c.lineTo(X(p.t), Y(p.v)) : c.moveTo(X(p.t), Y(p.v))));
    c.lineTo(x1, Y(total));
    c.stroke();
    if (Math.floor(t * 2) % 2) rect(c, x1 - 1, Y(total) - 1, 3, 3, total >= 0 ? "#2ecc71" : "#e74c3c");
  }
}

function drawBoardText(c: CanvasRenderingContext2D, total: number, btc: number | null, people: FloorPerson[],
                       font: string, K: number, ox: number, t: number) {
  const px = (x: number) => x * K + ox, py = (y: number) => y * K;
  c.save();
  c.textBaseline = "top";
  c.font = `${Math.round(5 * K)}px ${font}`;
  c.fillStyle = "#f5c542";
  c.textAlign = "left";
  c.fillText("DESK", px(BOARD.x + 4), py(BOARD.y + 4));
  c.fillStyle = total >= 0 ? "#2ecc71" : "#e74c3c";
  c.fillText(dollars(total, true), px(BOARD.x + 30), py(BOARD.y + 4));
  if (btc) {
    c.fillStyle = "#7fd3ff";
    c.textAlign = "right";
    c.fillText(`BTC ${Math.round(btc).toLocaleString()}`, px(BOARD.x + BOARD.w - 4), py(BOARD.y + 4));
  }
  // LED ticker along the bottom of the board
  c.beginPath(); c.rect(px(BOARD.x + 1), py(BOARD.y + BOARD.h - 9), (BOARD.w - 2) * K, 8 * K); c.clip();
  c.textAlign = "left";
  c.font = `${Math.round(4 * K)}px ${font}`;
  const items = [...people].sort((a, b) => b.pnl - a.pnl).map((p) => `${shortName(p.name).toUpperCase()} ${dollars(p.pnl, true)}`).join("  ★  ");
  const text = `${items}  ★  `;
  const wPx = c.measureText(text).width || 1;
  const off = (t * 16 * K) % wPx;
  c.fillStyle = "#f5c542";
  c.fillText(text, px(BOARD.x + 2) - off, py(BOARD.y + BOARD.h - 8));
  c.fillText(text, px(BOARD.x + 2) - off + wPx, py(BOARD.y + BOARD.h - 8));
  c.restore();
}

/** The conference whiteboard: a chart that gets drawn during meetings. */
function drawWhiteboard(c: CanvasRenderingContext2D, k: number) {
  const { x, y, w, h } = WHITEBOARD;
  rect(c, x + 6, y + 4, 22, 2, "#2f5aa8"); rect(c, x + 6, y + 8, 14, 1, "#9aa3b5");
  rect(c, x + 60, y + 4, 24, 1, "#9aa3b5"); rect(c, x + 60, y + 7, 18, 1, "#9aa3b5");
  const n = Math.floor(k * 30);
  for (let i = 0; i < n; i++) {
    const px = x + 8 + i * 2.6, pyv = y + h - 6 - (i * 0.6 + Math.sin(i * 0.9) * 3);
    rect(c, px, pyv, 2, 1, i > 24 ? "#2ecc71" : "#e03c3c");
  }
  if (k > 0.9) { rect(c, x + w - 16, y + 12, 8, 1, "#2ecc71"); rect(c, x + w - 10, y + 10, 2, 5, "#2ecc71"); }
}

/** The lounge TV: bitcoin's price over the last few hours, like a finance channel. */
function drawTV(c: CanvasRenderingContext2D, series: Point[], t: number) {
  const x = 1 * TILE + 9, y = 10 * TILE - 9, w = 4 * TILE - 18, h = 15;
  rect(c, x, y, w, h, "#0b1430");
  rect(c, x, y + h - 3, w, 3, "#c0392b");
  for (let i = 0; i < w - 4; i += 6) rect(c, x + i + ((t * 10) % 6), y + h - 2, 3, 1, "#ffffff");
  if (series.length > 1) {
    const vs = series.map((p) => p.v), lo = Math.min(...vs), hi = Math.max(...vs);
    c.strokeStyle = vs[vs.length - 1] >= vs[0] ? "#2ecc71" : "#e74c3c";
    c.lineWidth = 1;
    c.beginPath();
    series.forEach((p, i) => {
      const px = x + 1 + (i / (series.length - 1)) * (w - 2), py = y + 2 + (1 - (p.v - lo) / (hi - lo || 1)) * (h - 7);
      i ? c.lineTo(px, py) : c.moveTo(px, py);
    });
    c.stroke();
  }
  rect(c, x + 1, y + 1, 5, 2, "#f5c542");
}

function drawPizza(c: CanvasRenderingContext2D) {
  const x = 26 * TILE - 4, y = 12 * TILE;
  rect(c, x - 1, y - 1, 18, 12, "#14101f"); rect(c, x, y, 16, 10, "#e8c39e"); rect(c, x + 2, y + 2, 12, 6, "#f5c542");
  for (const [dx, dy] of [[3, 3], [7, 5], [10, 3], [5, 6], [12, 6]]) rect(c, x + dx, y + dy, 2, 2, "#c0392b");
}

function drawCake(c: CanvasRenderingContext2D, t: number) {
  const x = 26 * TILE - 2, y = 12 * TILE - 2;
  rect(c, x - 1, y - 1, 14, 11, "#14101f"); rect(c, x, y, 12, 9, "#f8bbd0"); rect(c, x, y + 3, 12, 1, "#ffffff");
  for (let i = 0; i < 3; i++) { rect(c, x + 2 + i * 4, y - 4, 1, 4, "#7fd3ff"); if (Math.floor(t * 6 + i) % 2) rect(c, x + 2 + i * 4, y - 6, 1, 2, "#ffcf6b"); }
}

function drawEspresso(c: CanvasRenderingContext2D) {
  for (let i = 0; i < 4; i++) { rect(c, 25 * TILE + 4 + i * 6, 12 * TILE + 3, 5, 5, "#14101f"); rect(c, 25 * TILE + 5 + i * 6, 12 * TILE + 4, 3, 3, "#ffffff"); }
}

function bubble(c: CanvasRenderingContext2D, text: string, x: number, y: number, fontPx: number, K: number, maxW: number, tag: boolean) {
  const words = text.split(" ");
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    const tryLine = cur ? `${cur} ${w}` : w;
    if (c.measureText(tryLine).width > maxW && cur) { lines.push(cur); cur = w; } else cur = tryLine;
  }
  if (cur) lines.push(cur);
  const lh = fontPx * 1.35;
  const pad = fontPx * 0.55;
  const w = Math.max(...lines.map((l) => c.measureText(l).width)) + pad * 2;
  const h = lines.length * lh + pad * 1.3;
  const cw = c.canvas.width;
  const bx = Math.round(Math.max(2, Math.min(cw - w - 2, x - w / 2)));
  const by = Math.round(Math.max(2, y - h - 3 * K));
  const b = Math.max(2, Math.round(K / 1.5));
  c.fillStyle = "rgba(5,3,15,0.45)";
  c.fillRect(bx + b, by + b, w, h);
  c.fillStyle = "#14101f";
  c.fillRect(bx - b, by - b, w + 2 * b, h + 2 * b);
  c.fillStyle = tag ? "#f5c542" : "#ffffff";
  c.fillRect(bx, by, w, h);
  if (!tag) {
    c.fillStyle = "#14101f";
    c.beginPath(); c.moveTo(x - 3 * K, by + h); c.lineTo(x + 3 * K, by + h); c.lineTo(x, by + h + 3.5 * K); c.fill();
    c.fillStyle = "#ffffff";
    c.beginPath(); c.moveTo(x - 2 * K, by + h - 1); c.lineTo(x + 2 * K, by + h - 1); c.lineTo(x, by + h + 2 * K); c.fill();
  }
  c.fillStyle = "#14101f";
  c.textAlign = "left";
  lines.forEach((l, i) => c.fillText(l, bx + pad, by + pad * 0.85 + i * lh));
}
