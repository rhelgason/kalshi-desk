"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Point } from "@/lib/types";
import { dollars } from "@/lib/format";
import { drawBell, drawChairs, drawClock, drawFish, drawMonitors, drawRoom, rect, skyFor, type Sky } from "@/lib/office/draw";
import { chairSpot, DESKS, findPath, HEIGHT, OPEN, PIT, SPOTS, TILE, tileSpot, WIDTH, type Spot, type Tile } from "@/lib/office/map";
import { gridCanvas, lookFor, walker, type Dir, type Step } from "@/lib/office/walkers";
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
// Agents
// ---------------------------------------------------------------------------

type Kind =
  | "desk" | "coffee" | "cooler" | "window" | "board" | "aquarium" | "vending" | "fridge" | "printer"
  | "pingpong" | "couch" | "bench" | "restroom" | "visit" | "pace" | "bell" | "bull" | "party"
  | "flee" | "chant" | "dance" | "rush" | "chase" | "leave" | "skate" | "stage" | "cheer" | "fetch";

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
  until: number; // when the current task ends (set on arrival)
  dur: number;
  arrived: boolean;
  speed: number;
  walkT: number;
  bubble: { text: string; until: number } | null;
  nextChat: number;
  carry: "mug" | "phone" | "champagne" | "megaphone" | "pizza" | "snack" | null;
  mood: Mood;
  pnl: number;
  busyUntil: number;
  hidden: boolean;
  gone?: boolean;
  partner?: string;
};

type Particle = {
  x: number; y: number; vx: number; vy: number; life: number; max: number;
  kind: "confetti" | "bill" | "balloon" | "foam" | "pop" | "coin" | "plane" | "note" | "cork" | "fish" | "z";
  color: string; seed: number;
};

type EventKind =
  | "balloons" | "confetti" | "money" | "champagne" | "skates" | "chant" | "disco" | "pizza" | "drill"
  | "sugar" | "planes" | "pigeon" | "speech" | "fish" | "band";

const EVENT_INFO: Record<EventKind, { icon: string; label: string; secs: number }> = {
  balloons: { icon: "🎈", label: "Balloon drop!", secs: 14 },
  confetti: { icon: "🎊", label: "Somebody fired the confetti cannon.", secs: 8 },
  money: { icon: "💸", label: "It's raining money.", secs: 12 },
  champagne: { icon: "🍾", label: "pops the champagne.", secs: 9 },
  skates: { icon: "🛼", label: "is roller-skating through the office.", secs: 18 },
  chant: { icon: "🥁", label: "The chest-thump chant has started. ♪ Mm-mm ♪", secs: 16 },
  disco: { icon: "🪩", label: "Lights down. Disco time.", secs: 16 },
  pizza: { icon: "🍕", label: "Pizza's here!", secs: 26 },
  drill: { icon: "🚨", label: "Fire drill! (It's just a drill.)", secs: 11 },
  sugar: { icon: "🍩", label: "Someone brought powdered donuts. SUGAR RUSH.", secs: 14 },
  planes: { icon: "✈️", label: "Paper airplane war!", secs: 11 },
  pigeon: { icon: "🐦", label: "A pigeon flew in through the window.", secs: 15 },
  speech: { icon: "📣", label: "grabs the megaphone.", secs: 16 },
  fish: { icon: "🐟", label: "Gordon the goldfish jumped out of the tank!", secs: 11 },
  band: { icon: "🎺", label: "A marching band just walked in. Nobody knows who ordered it.", secs: 22 },
};
const EVENT_KINDS = Object.keys(EVENT_INFO) as EventKind[];

const CHATTER: Record<string, string[]> = {
  coffee: ["Coffee #4 today.", "Who used the last oat milk?", "Decaf is a scam.", "This coffee tastes like fees."],
  cooler: ["Did you see bitcoin just now?", "I'm basically a genius.", "Hydrate or die-drate.", "Heard Dan beat the Professor.", "15 minutes is a long time in crypto."],
  window: ["One day, a corner office.", "Bull or bear out there?", "Rain means volatility.", "Nice day to buy the dip."],
  board: ["Up, up, up!", "Come on, green candle…", "That chart is spicy.", "Read 'em and weep."],
  aquarium: ["Hi Gordon.", "The fish has better returns than me.", "Blub blub."],
  vending: ["Out of chips AGAIN.", "Snack o'clock.", "I'm stress eating, it's fine."],
  fridge: ["Who ate my sandwich?!", "Something in here is alive."],
  printer: ["PC LOAD LETTER?!", "Why is it always jammed?"],
  pace: ["Breathe…", "It'll bounce. It'll bounce.", "Okay okay okay.", "It's just variance."],
  desk: ["Locked in.", "Watching the tape.", "Hmm…", "Spreadsheet time."],
  trading: ["BUY! BUY! BUY!", "Get me in!", "Send it!", "Locked in."],
  celebrating: ["WINNER!", "Pay me!", "Ka-ching!", "Who's the best? ME!"],
  stressed: ["Ugh.", "Why did I do that?", "Nobody talk to me.", "My portfolio…"],
  couch: ["Zzz…", "*snore*", "Five more minutes…"],
  bench: ["Put me in, coach!", "This bench is cold.", "I'll be back."],
  visit: ["Nice trade!", "You're up how much?", "Lend me five bucks?", "Teach me your ways."],
  bull: ["Rub the bull for luck.", "Shiny."],
  monkey: ["Ook ook!", "🍌?", "Ook."],
};
const pick = <T,>(xs: T[]) => xs[Math.floor(Math.random() * xs.length)];
const rand = (a: number, b: number) => a + Math.random() * (b - a);
// "Dart Monkey Dan" -> "Dan", "The Sniper" stays "The Sniper"
const firstName = (n: string) => (n.startsWith("The ") ? n : n.split(" ").slice(-1)[0]);

const ACTIVITY: Record<Kind, string> = {
  desk: "at their desk", coffee: "making coffee", cooler: "gossiping at the water cooler", window: "staring out the window",
  board: "watching the big board", aquarium: "visiting Gordon the goldfish", vending: "at the vending machine",
  fridge: "raiding the fridge", printer: "fighting the printer", pingpong: "playing ping pong", couch: "napping on the couch",
  bench: "sitting on the bench", restroom: "in the restroom", visit: "visiting a coworker", pace: "pacing around",
  bell: "ringing the bell", bull: "rubbing the golden bull", party: "celebrating", flee: "running from the fire drill",
  chant: "doing the chest-thump chant", dance: "dancing", rush: "on a sugar rush", chase: "chasing something",
  leave: "heading out", skate: "roller-skating", stage: "giving a speech", cheer: "cheering", fetch: "rescuing Gordon",
};

// ---------------------------------------------------------------------------
// The component
// ---------------------------------------------------------------------------

export default function OfficeFloor({ people, total, btc, series }: {
  people: FloorPerson[];
  total: number;
  btc: number | null;
  series: Point[];
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const world = useRef<{
    agents: Agent[];
    particles: Particle[];
    event: { kind: EventKind; start: number; end: number; actor?: string; x?: number; y?: number } | null;
    nextEvent: number;
    ringing: number;
    roomba: { x: number; y: number; vx: number; vy: number };
    pizzaOnTable: number;
    donuts: number;
    seen: Record<string, string | null>;
    selected: string | null;
    hover: string | null;
    /** camera: top-left corner and zoom (1 = whole office) */
    cam: { x: number; y: number; z: number; tz: number };
    drag: { x: number; y: number; cx: number; cy: number; moved: boolean } | null;
    reduced: boolean;
    sprites: Map<string, HTMLCanvasElement>;
    bg: HTMLCanvasElement | null;
    sky: Sky | null;
    font: string;
    lastTotal: number;
  } | null>(null);
  const live = useRef({ people, total, btc, series });
  live.current = { people, total, btc, series };
  const [log, setLog] = useState<{ id: number; icon: string; text: string; at: string }[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [zoomed, setZoomed] = useState(false);
  const [, setTick] = useState(0);
  const logId = useRef(0);

  const note = useCallback((icon: string, text: string) => {
    const at = new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    setLog((l) => [{ id: ++logId.current, icon, text, at }, ...l].slice(0, 8));
  }, []);

  // ---------------- simulation helpers ----------------

  const say = (a: Agent, text: string, secs = 3.5) => {
    a.bubble = { text, until: performance.now() / 1000 + secs };
  };

  const send = (a: Agent, spot: Spot, kind: Kind, dur: number) => {
    a.path = findPath(a.tile, spot.tile);
    a.target = spot;
    a.kind = kind;
    a.dur = dur;
    a.arrived = false;
    a.hidden = false;
    if (a.carry && !["mug", "snack"].includes(a.carry)) a.carry = null;
    const w = world.current;
    if (w?.reduced) {
      a.x = spot.x; a.y = spot.y; a.tile = spot.tile; a.path = [];
    }
  };

  const randomOpen = (from: Tile[] = OPEN) => {
    const t = pick(from);
    return tileSpot(t.x, t.y, pick(["down", "left", "right", "up"] as const));
  };

  /** What someone does next, weighted by what they're really doing on Kalshi. */
  const chooseTask = (a: Agent, now: number) => {
    const w = world.current!;
    if (a.npc) return;
    const desk = () => send(a, chairSpot(a.desk), "desk", rand(20, 50));
    const options: [number, () => void][] = [];
    const add = (weight: number, f: () => void) => weight > 0 && options.push([weight, f]);
    const others = w.agents.filter((b) => b !== a && !b.npc && !b.gone);
    const m = a.mood;
    if (m === "benched") {
      add(8, () => send(a, SPOTS.bench[a.desk % 3], "bench", rand(30, 60)));
      add(1, () => send(a, SPOTS.vending, "vending", rand(5, 9)));
      add(1, () => send(a, pick(SPOTS.aquarium), "aquarium", rand(6, 10)));
    } else {
      const atDesk = { trading: 7, watching: 4, celebrating: 1, stressed: 2, coffee: 2, sleeping: 3, fired: 0, benched: 0 }[m];
      add(atDesk, desk);
      add(m === "coffee" ? 3 : 1, () => send(a, SPOTS.coffee, "coffee", rand(5, 9)));
      add(m === "coffee" ? 3 : 1, () => send(a, pick(SPOTS.cooler), "cooler", rand(8, 14)));
      add(m === "watching" || m === "stressed" ? 2 : 1, () => send(a, pick(SPOTS.windows), "window", rand(6, 12)));
      add(m === "trading" || m === "watching" ? 2 : 1, () => send(a, pick(SPOTS.board), "board", rand(6, 12)));
      add(m === "coffee" ? 1 : 0.5, () => send(a, pick(SPOTS.aquarium), "aquarium", rand(6, 10)));
      add(m === "stressed" ? 2 : 0.6, () => send(a, SPOTS.vending, "vending", rand(5, 8)));
      add(0.4, () => send(a, SPOTS.fridge, "fridge", rand(4, 7)));
      add(0.4, () => send(a, SPOTS.printer, "printer", rand(5, 9)));
      add(0.4, () => send(a, SPOTS.restroom, "restroom", rand(8, 14)));
      add(0.5, () => send(a, SPOTS.bull, "bull", rand(4, 7)));
      add(m === "sleeping" ? 5 : 0.3, () => send(a, SPOTS.couch[a.desk % 4], "couch", rand(25, 50)));
      add(m === "stressed" ? 3 : m === "watching" ? 1.5 : 0.5, () => send(a, randomOpen(), "pace", rand(3, 6)));
      add(m === "celebrating" ? 4 : 0, () => send(a, SPOTS.bell, "bell", 4));
      add(m === "celebrating" ? 3 : 0, () => send(a, randomOpen(), "party", rand(3, 5)));
      const atDesks = others.filter((b) => b.kind === "desk" && b.arrived);
      add(atDesks.length ? (m === "coffee" || m === "celebrating" ? 2 : 0.7) : 0, () => {
        const b = pick(atDesks);
        const d = DESKS[b.desk];
        send(a, tileSpot(d.col - 1, d.row + 1, "right"), "visit", rand(6, 10));
        a.partner = b.key;
      });
      const free = others.filter((b) => ["cooler", "window", "aquarium", "pace", "board"].includes(b.kind) && b.mood !== "benched");
      add(free.length && !w.agents.some((b) => b.kind === "pingpong") ? (m === "coffee" ? 2 : 0.6) : 0, () => {
        const b = pick(free);
        const dur = rand(14, 22);
        send(a, SPOTS.pingpong[0], "pingpong", dur);
        send(b, SPOTS.pingpong[1], "pingpong", dur);
        a.partner = b.key; b.partner = a.key;
        if (Math.random() < 0.5) say(b, "You're going down.");
      });
    }
    let r = Math.random() * options.reduce((s, [wt]) => s + wt, 0);
    for (const [wt, f] of options) {
      if ((r -= wt) <= 0) { f(); return; }
    }
    desk();
    void now;
  };

  const spawn = (p: Omit<Particle, "seed">) => world.current!.particles.push({ ...p, seed: Math.random() * 100 });

  const burst = (x: number, y: number, n: number, kind: Particle["kind"], colors: string[], speed = 60) => {
    for (let i = 0; i < n; i++) {
      const ang = rand(0, Math.PI * 2), v = rand(speed * 0.3, speed);
      spawn({ x, y, vx: Math.cos(ang) * v, vy: Math.sin(ang) * v - speed * 0.6, life: 0, max: rand(1.2, 2.6), kind, color: pick(colors) });
    }
  };

  const CONFETTI = ["#f5c542", "#e74c3c", "#2ecc71", "#7fd3ff", "#c56cf0", "#ff9f43"];

  const startEvent = useCallback((kind: EventKind) => {
    const w = world.current;
    if (!w) return;
    const now = performance.now() / 1000;
    const crew = w.agents.filter((a) => !a.npc && !a.gone && a.mood !== "benched");
    if (!crew.length) return;
    const info = EVENT_INFO[kind];
    const star = [...crew].sort((a, b) => b.pnl - a.pnl)[0];
    const dan = crew.find((a) => a.key === "dart_monkey");
    let actor: Agent | undefined;
    w.event = { kind, start: now, end: now + info.secs };
    const gather = (k: Kind, tiles: Tile[], dur: number) =>
      crew.forEach((a) => { const t = pick(tiles); send(a, tileSpot(t.x, t.y, "down"), k, dur); });

    switch (kind) {
      case "balloons":
        for (let i = 0; i < 46; i++) spawn({ x: rand(6, WIDTH - 6), y: HEIGHT + rand(0, 90), vx: 0, vy: -rand(14, 26), life: 0, max: 14, kind: "balloon", color: pick(CONFETTI) });
        crew.forEach((a) => Math.random() < 0.5 && say(a, pick(["BALLOONS!", "Who did this?!", "Woooo!", "🎈🎈🎈"])));
        break;
      case "confetti":
        burst(168, 44, 120, "confetti", CONFETTI, 90);
        setTimeout(() => burst(168, 44, 90, "confetti", CONFETTI, 80), 1500);
        crew.forEach((a) => Math.random() < 0.4 && say(a, pick(["WOOO!", "Yeah!!", "Confetti!"])));
        break;
      case "money":
        crew.forEach((a) => { send(a, randomOpen(), "party", info.secs); if (Math.random() < 0.6) say(a, pick(["MINE!", "Make it rain!", "Free money!", "Is this taxable?"])); });
        break;
      case "champagne":
        actor = star;
        send(actor, SPOTS.stage, "stage", info.secs - 1);
        actor.carry = "champagne";
        crew.filter((a) => a !== actor).forEach((a) => Math.random() < 0.6 && send(a, randomOpen(PIT), "cheer", info.secs - 1));
        break;
      case "skates":
        actor = dan ?? pick(crew);
        actor.kind = "skate";
        actor.speed = 95;
        say(actor, actor.key === "dart_monkey" ? "OOK OOK WHEEEE!" : "WHEEEEE!", 3);
        crew.filter((a) => a !== actor).slice(0, 3).forEach((a, i) => setTimeout(() => say(a, pick(["Is that a monkey on roller skates?!", "Not in the office!", "LOL", "Who gave him skates?"])), 900 + i * 1300));
        send(actor, randomOpen(), "skate", info.secs);
        break;
      case "chant":
        gather("chant", PIT, info.secs);
        break;
      case "disco":
        gather("dance", PIT.concat(OPEN.filter((t) => t.y >= 11 && t.y <= 15 && t.x >= 2 && t.x <= 12)), info.secs);
        break;
      case "pizza": {
        const guy = makeAgent("pizza", "Pizza Guy", 0, SPOTS.elevator[0], true);
        guy.carry = "pizza";
        w.agents.push(guy);
        send(guy, tileSpot(14, 14, "right"), "rush", 4);
        say(guy, "Pizza for… Kalshi Desk?");
        break;
      }
      case "drill":
        crew.forEach((a) => { a.speed = 70; send(a, randomOpen(), "flee", info.secs); if (Math.random() < 0.6) say(a, pick(["AAAAH!", "Save the laptops!", "Is it real?!", "Women and monkeys first!"])); });
        break;
      case "sugar":
        w.donuts = now + info.secs;
        crew.forEach((a) => { a.speed = 80; send(a, randomOpen(), "rush", info.secs); });
        crew.forEach((a, i) => setTimeout(() => say(a, pick(["SUGAR RUSH!!!", "I CAN SEE SOUNDS", "BUY EVERYTHING", "MORE DONUTS", "I feel INVINCIBLE"])), i * 600));
        break;
      case "planes":
        for (let i = 0; i < 12; i++) {
          const a = pick(crew);
          setTimeout(() => spawn({ x: a.x, y: a.y - 12, vx: rand(-70, 70), vy: rand(-25, 10), life: 0, max: 3.5, kind: "plane", color: "#ffffff" }), i * 650);
        }
        crew.forEach((a) => Math.random() < 0.5 && say(a, pick(["Incoming!", "Take that!", "Direct hit!", "My eye!"])));
        break;
      case "pigeon": {
        const bird = makeAgent("pigeon", "Pigeon", 0, tileSpot(4, 3, "down"), true);
        bird.speed = 40;
        w.agents.push(bird);
        send(bird, randomOpen(), "pace", 2);
        crew.slice(0, 3).forEach((a) => { a.speed = 55; send(a, randomOpen(), "chase", info.secs - 2); say(a, pick(["Get it!", "It's going for my sandwich!", "Shoo! SHOO!"])); });
        break;
      }
      case "speech":
        actor = star;
        send(actor, SPOTS.stage, "stage", info.secs);
        actor.carry = "megaphone";
        crew.filter((a) => a !== actor).forEach((a) => send(a, randomOpen(PIT), "cheer", info.secs));
        break;
      case "fish": {
        spawn({ x: 8, y: 12 * TILE + 8, vx: 22, vy: -50, life: 0, max: info.secs, kind: "fish", color: "#f39c12" });
        const hero = [...crew].sort((a, b) => Math.abs(a.x - 30) + Math.abs(a.y - 210) - (Math.abs(b.x - 30) + Math.abs(b.y - 210)))[0];
        hero.speed = 60;
        send(hero, tileSpot(2, 13, "left"), "fetch", 3);
        say(hero, "Gordon, NO!");
        break;
      }
      case "band":
        for (let i = 0; i < 3; i++) {
          const m = makeAgent("band", "Band", 0, SPOTS.elevator[i % 2], true);
          m.speed = 22;
          w.agents.push(m);
          setTimeout(() => send(m, tileSpot(3 + i, 8, "left"), "pace", 2), i * 700);
        }
        crew.forEach((a) => Math.random() < 0.5 && say(a, pick(["Is that… a marching band?", "Who ordered this?", "BEST. DAY. EVER.", "♪ ♪ ♪"])));
        break;
    }
    const who = actor ? `${actor.name} ` : "";
    note(info.icon, `${who}${info.label}`);
    w.nextEvent = now + info.secs + rand(25, 60);
  }, [note]);

  const makeAgent = (key: string, name: string, desk: number, at: Spot, npc = false): Agent => ({
    key, name, desk, npc, x: at.x, y: at.y, tile: at.tile, face: at.face, path: [], target: at, kind: "desk",
    until: 0, dur: 0, arrived: true, speed: 32, walkT: 0, bubble: null, nextChat: performance.now() / 1000 + rand(3, 12),
    carry: null, mood: "watching", pnl: 0, busyUntil: 0, hidden: false,
  });

  // ---------------- set up the world once ----------------

  useEffect(() => {
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const now = performance.now() / 1000;
    const agents = live.current.people.filter((p) => p.mood !== "fired").map((p, i) => {
      const chair = chairSpot(i);
      const start = p.mood === "benched" ? SPOTS.bench[i % 3] : p.mood === "sleeping" && i % 2 ? SPOTS.couch[i % 4] : Math.random() < 0.6 ? chair : randomOpen();
      const a = makeAgent(p.key, p.name, i, start);
      a.mood = p.mood;
      a.pnl = p.pnl;
      a.kind = p.mood === "benched" ? "bench" : start === chair ? "desk" : start.sit ? "couch" : "pace";
      a.until = now + rand(2, 12);
      if (p.mood === "trading") a.busyUntil = now + 20;
      return a;
    });
    world.current = {
      agents, particles: [], event: null, nextEvent: now + rand(6, 10), ringing: 0,
      roomba: { x: 120, y: 200, vx: 14, vy: 9 }, pizzaOnTable: 0, donuts: 0,
      seen: Object.fromEntries(live.current.people.map((p) => [p.key, p.lastFillTs])),
      selected: null, hover: null, cam: { x: 0, y: 0, z: 1, tz: 1 }, drag: null, reduced, sprites: new Map(), bg: null, sky: null,
      font: getComputedStyle(document.body).getPropertyValue("--pixel").trim() || "monospace",
      lastTotal: live.current.total,
    };
    const first = live.current.people.filter((p) => p.lastBet && p.mood === "trading");
    first.forEach((p) => note("💬", `${p.name}: ${p.lastBet}`));
    if (!first.length) note("🏢", "Welcome to the floor. Everyone acts out what they're really doing on Kalshi.");
    // #chaos=<event> starts that event right away (handy for previews)
    const forced = window.location.hash.match(/chaos=(\w+)/)?.[1] as EventKind | undefined;
    if (forced && forced in EVENT_INFO) {
      world.current.nextEvent = Infinity;
      setTimeout(() => startEvent(forced), 1500);
    }
  }, [note]);

  // ---------------- new data from the server (every 30s) ----------------

  useEffect(() => {
    const w = world.current;
    if (!w) return;
    const now = performance.now() / 1000;
    for (const p of people) {
      const a = w.agents.find((x) => x.key === p.key);
      if (!a) continue;
      const wasBenched = a.mood === "benched";
      const prevMood = a.mood;
      a.mood = p.mood;
      a.pnl = p.pnl;
      if (p.lastFillTs && p.lastFillTs !== w.seen[p.key]) {
        w.seen[p.key] = p.lastFillTs;
        a.busyUntil = now + 25;
        if (a.kind !== "desk") send(a, chairSpot(a.desk), "desk", rand(20, 35));
        if (p.lastBet) { say(a, p.lastBet.toUpperCase().replace(/^BET /, "") + "!", 5); note("💬", `${p.name}: ${p.lastBet}`); }
      }
      if (p.mood === "celebrating" && prevMood !== "celebrating") {
        send(a, SPOTS.bell, "bell", 4);
        note("🔔", `${p.name} rang the bell: ${p.line}`);
      }
      if (wasBenched !== (p.mood === "benched")) chooseTask(a, now);
    }
    // a big jump in the desk's total gets a party
    if (total - w.lastTotal >= 10 && !w.event) startEvent("money");
    w.lastTotal = total;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [people, total]);

  // ---------------- the animation loop ----------------

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    let raf = 0;
    let last = performance.now() / 1000;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(canvas.clientWidth * dpr);
      canvas.height = Math.round(canvas.clientWidth * dpr * (HEIGHT / WIDTH));
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const sprite = (a: Agent, dir: Dir, step: Step, sleepy: boolean) => {
      const w = world.current!;
      const id = `${a.key}|${dir}|${step}|${sleepy}`;
      let c = w.sprites.get(id);
      if (!c) {
        c = gridCanvas(walker(lookFor(a.key), dir, step, { sleepy }));
        w.sprites.set(id, c);
      }
      return c;
    };

    const frame = () => {
      raf = requestAnimationFrame(frame);
      const w = world.current;
      if (!w) return;
      const now = performance.now() / 1000;
      const dt = Math.min(0.1, now - last);
      last = now;
      const S = canvas.width / WIDTH;
      const css = canvas.clientWidth / WIDTH; // CSS pixels per native pixel
      const hour = new Date().getHours();

      // Static room, redrawn when the sky changes
      const sky = skyFor(hour);
      if (!w.bg || w.sky?.top !== sky.top) {
        const bg = document.createElement("canvas");
        bg.width = WIDTH; bg.height = HEIGHT;
        drawRoom(bg.getContext("2d")!, sky);
        w.bg = bg; w.sky = sky;
      }

      // ---- simulate ----
      if (!w.reduced && !w.event && now > w.nextEvent) {
        const party = live.current.total >= 0;
        const pool = EVENT_KINDS.flatMap((k) => Array(party && ["balloons", "confetti", "money", "champagne", "speech"].includes(k) ? 2 : !party && ["drill", "sugar", "pigeon"].includes(k) ? 2 : 1).fill(k));
        startEvent(pick(pool));
      }
      const ev = w.event;
      if (ev && now > ev.end) {
        w.event = null;
        for (const a of w.agents) {
          if (a.npc) { if (!a.gone && a.kind !== "leave") send(a, pick(SPOTS.elevator), "leave", 0); continue; }
          a.speed = 32;
          if (["chant", "dance", "flee", "rush", "cheer", "party", "skate", "stage", "chase"].includes(a.kind)) chooseTask(a, now);
        }
        if (ev.kind === "speech" || ev.kind === "champagne") burst(SPOTS.stage.x, SPOTS.stage.y - 20, 80, "confetti", CONFETTI, 70);
      }

      for (const a of w.agents) {
        if (a.gone) continue;
        // walking
        if (!a.arrived && a.target) {
          const next = a.path[0];
          const tx = next ? next.x * TILE + 8 : a.target.x;
          const ty = next ? next.y * TILE + 13 : a.target.y;
          const dx = tx - a.x, dy = ty - a.y, dist = Math.hypot(dx, dy);
          const step = a.speed * dt;
          if (dist <= step) {
            a.x = tx; a.y = ty;
            if (next) { a.tile = a.path.shift()!; }
            else {
              a.arrived = true;
              a.face = a.target.face;
              a.until = now + a.dur;
              onArrive(a, now);
            }
          } else {
            a.x += (dx / dist) * step; a.y += (dy / dist) * step;
            a.face = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : dy > 0 ? "down" : "up";
            a.walkT += dt;
          }
        } else if (now > a.until) {
          if (a.npc) {
            if (a.kind === "leave") { a.gone = true; continue; }
            if (a.key === "pizza" && a.kind === "rush") {
              w.pizzaOnTable = now + 40;
              a.carry = null;
              say(a, "Enjoy!");
              send(a, pick(SPOTS.elevator), "leave", 0);
              w.agents.filter((b) => !b.npc && b.mood !== "benched").forEach((b) => {
                const t = pick(OPEN.filter((o) => o.x >= 14 && o.y >= 10 && o.y <= 16));
                send(b, tileSpot(t.x, t.y, "right"), "rush", 12);
                if (Math.random() < 0.6) say(b, pick(["PIZZA!", "Dibs on pepperoni!", "Out of my way!", "🍕🍕🍕"]));
              });
              continue;
            }
            if (w.event) send(a, randomOpen(a.key === "band" ? PIT : OPEN), "pace", a.key === "pigeon" ? rand(0.5, 2) : 0.5);
            else send(a, pick(SPOTS.elevator), "leave", 0);
            continue;
          }
          if (a.kind === "skate" || a.kind === "flee" || a.kind === "rush" || a.kind === "chase") {
            if (w.event) { send(a, randomOpen(), a.kind, 0.2); continue; }
          }
          if (a.kind === "party" && w.event?.kind === "money") { send(a, randomOpen(), "party", 0.5); continue; }
          if (w.event && ["chant", "dance", "cheer", "stage"].includes(a.kind)) { a.until = now + 1; continue; }
          a.hidden = false;
          if (a.kind === "coffee" || a.kind === "vending" || a.kind === "fridge") a.carry = a.kind === "coffee" ? "mug" : "snack";
          else if (a.kind === "desk") a.carry = null;
          chooseTask(a, now);
        }
        // chatter
        if (now > a.nextChat && !a.npc) {
          a.nextChat = now + rand(9, 22);
          if (a.arrived && Math.random() < 0.55 && !a.bubble) {
            const pool = a.key === "dart_monkey" && Math.random() < 0.5 ? CHATTER.monkey
              : a.kind === "desk" ? CHATTER[now < a.busyUntil ? "trading" : a.mood === "stressed" ? "stressed" : "desk"]
              : CHATTER[a.kind] ?? CHATTER[a.mood];
            if (pool) {
              const extra = live.current.btc && Math.random() < 0.15 ? [`Bitcoin's at ${dollars(live.current.btc).replace(/\.\d+$/, "")}!`] : [];
              const mine = Math.random() < 0.15 ? [`I'm ${a.pnl >= 0 ? "up" : "down"} ${dollars(Math.abs(a.pnl))}.`] : [];
              say(a, pick([...pool, ...extra, ...mine]));
            }
          }
        }
        if (a.bubble && now > a.bubble.until) a.bubble = null;
      }
      w.agents = w.agents.filter((a) => !a.gone);

      // ongoing event effects
      if (ev && !w.reduced) {
        const t = now - ev.start;
        if (ev.kind === "money" && Math.random() < dt * 30) spawn({ x: rand(0, WIDTH), y: 46, vx: rand(-6, 6), vy: rand(12, 22), life: 0, max: 12, kind: "bill", color: "#2ecc71" });
        if (ev.kind === "chant") {
          const beat = Math.floor(t / 0.8);
          const crew = w.agents.filter((a) => a.kind === "chant" && a.arrived);
          if (crew.length && Math.random() < dt * 0.9) say(pick(crew), pick(["♪ Mm-mm ♪", "♪ Mm-MM ♪", "*thump thump*", "♪ Hmm-hmm ♪"]), 2);
          void beat;
        }
        if (ev.kind === "champagne" && t > 2.5 && t < 6) {
          const a = w.agents.find((x) => x.kind === "stage" && x.arrived);
          if (a) {
            if (t < 2.5 + dt * 1.5) { spawn({ x: a.x + 4, y: a.y - 14, vx: rand(-10, 10), vy: -120, life: 0, max: 2.5, kind: "cork", color: "#c79a1e" }); say(a, "POP!", 2); }
            for (let i = 0; i < 4; i++) spawn({ x: a.x + 4, y: a.y - 12, vx: rand(-30, 30), vy: rand(-70, -30), life: 0, max: rand(0.6, 1.2), kind: "foam", color: "#fffbe6" });
          }
        }
        if (ev.kind === "speech") {
          const a = w.agents.find((x) => x.kind === "stage" && x.arrived);
          const lines = ["Listen up!", "Are you ready?!", "I'M NOT LEAVING!", "The show goes on!", "PICK UP THE PHONE AND DIAL!"];
          if (a) {
            const i = Math.floor((t - 2) / 2.6);
            if (i >= 0 && i < lines.length && a.bubble?.text !== lines[i]) {
              say(a, lines[i], 2.5);
              w.agents.filter((b) => b.kind === "cheer" && Math.random() < 0.3).forEach((b) => say(b, pick(["WOOO!", "YEAH!", "👏👏👏", "Wolf! Wolf!"]), 2));
            }
          }
        }
        if (ev.kind === "band" && Math.random() < dt * 4) {
          const m = pick(w.agents.filter((a) => a.key === "band"));
          if (m) spawn({ x: m.x, y: m.y - 16, vx: rand(-8, 8), vy: -18, life: 0, max: 1.6, kind: "note", color: "#f5c542" });
        }
        if (ev.kind === "disco" && Math.random() < dt * 2) {
          const a = pick(w.agents.filter((x) => x.kind === "dance"));
          if (a && !a.bubble && Math.random() < 0.3) say(a, pick(["♪ Stayin' alive ♪", "Watch this move!", "💃", "🕺"]), 2);
        }
      }
      if (w.ringing > now && Math.random() < dt * 5) spawn({ x: TILE + 8, y: 3 * TILE, vx: rand(-15, 15), vy: -25, life: 0, max: 1.2, kind: "note", color: "#f5c542" });

      // roomba
      const r = w.roomba;
      if (!w.reduced) {
        const nx = r.x + r.vx * dt, ny = r.y + r.vy * dt;
        const t = { x: Math.floor(nx / TILE), y: Math.floor(ny / TILE) };
        const okTile = t.x >= 0 && t.x < 20 && t.y >= 3 && t.y < 18 && OPEN.some((o) => o.x === t.x && o.y === t.y);
        if (!okTile) { r.vx = -r.vx + rand(-4, 4); r.vy = -r.vy + rand(-4, 4); } else { r.x = nx; r.y = ny; }
      }

      // particles
      for (const p of w.particles) {
        p.life += dt;
        if (p.kind === "balloon") { p.x += Math.sin(now * 1.5 + p.seed) * 6 * dt; p.y += p.vy * dt; if (p.y < 12) { p.life = p.max; for (let i = 0; i < 5; i++) w.particles.push({ x: p.x, y: p.y, vx: rand(-30, 30), vy: rand(-30, 30), life: 0, max: 0.4, kind: "pop", color: p.color, seed: 0 }); } continue; }
        if (p.kind === "bill") { p.x += (p.vx + Math.sin(now * 3 + p.seed) * 10) * dt; p.y += p.vy * dt; if (p.y > HEIGHT) p.life = p.max; continue; }
        if (p.kind === "plane") { p.x += p.vx * dt; p.y += (p.vy + Math.sin(now * 4 + p.seed) * 20) * dt; continue; }
        if (p.kind === "fish") {
          if (p.y < 13 * TILE + 8 || p.vy < 0) { p.vy += 140 * dt; p.x += p.vx * dt; p.y += p.vy * dt; }
          else { p.vx = 0; p.vy = 0; if (p.life > 4) { p.life = p.max; } }
          continue;
        }
        p.vy += (p.kind === "note" || p.kind === "z" ? -5 : 120) * dt;
        if (p.kind === "confetti") { p.vx *= 0.98; p.vy = Math.min(p.vy, 30); }
        p.x += p.vx * dt; p.y += p.vy * dt;
      }
      w.particles = w.particles.filter((p) => p.life < p.max).slice(-600);

      // ---- draw ----
      // camera: zoom eases in and out, and follows whoever is selected
      const cam = w.cam;
      cam.z += (cam.tz - cam.z) * Math.min(1, dt * 6);
      if (Math.abs(cam.tz - cam.z) < 0.01) cam.z = cam.tz;
      const vw = WIDTH / cam.z, vh = HEIGHT / cam.z;
      const followed = w.selected ? w.agents.find((a) => a.key === w.selected) : null;
      if (followed && !w.drag) {
        cam.x += (followed.x - vw / 2 - cam.x) * Math.min(1, dt * 4);
        cam.y += (followed.y - 10 - vh / 2 - cam.y) * Math.min(1, dt * 4);
      }
      cam.x = Math.max(0, Math.min(WIDTH - vw, cam.x));
      cam.y = Math.max(0, Math.min(HEIGHT - vh, cam.y));
      const K = S * cam.z, ox = -cam.x * K, oy = -cam.y * K;
      ctx.setTransform(K, 0, 0, K, ox, oy);
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(w.bg!, 0, 0);
      const t = now;
      const { people: ppl, series: ser, total: tot, btc: coin } = live.current;
      for (let i = 0; i < DESKS.length; i++) {
        const a = w.agents.find((x) => !x.npc && x.desk === i);
        drawMonitors(ctx, i, a?.pnl ?? 0, !!a && now < a.busyUntil, t, i, !a);
      }
      drawClock(ctx, new Date());
      drawBell(ctx, t, w.ringing > now);
      drawFish(ctx, t);
      drawBoard(ctx, ser, tot, coin, t, K, ox, oy, w.font);
      // coffee steam
      if (w.agents.some((a) => a.kind === "coffee" && a.arrived)) for (let i = 0; i < 3; i++) rect(ctx, 19 * TILE + 7 + i * 2, 10 * TILE - 2 - ((t * 8 + i * 3) % 7), 1, 1, "rgba(255,255,255,0.6)");
      if (w.pizzaOnTable > now) { rect(ctx, 16 * TILE - 2, 12 * TILE + 8, 14, 12, "#e8c39e"); rect(ctx, 16 * TILE, 12 * TILE + 10, 10, 8, "#f5c542"); for (const [dx, dy] of [[2, 2], [6, 4], [3, 6], [8, 2]]) rect(ctx, 16 * TILE + dx, 12 * TILE + 10 + dy, 2, 2, "#c0392b"); }
      if (w.donuts > now) { rect(ctx, 7 * TILE + 2, 8 * TILE - 4, 14, 9, "#f5f5f5"); for (let i = 0; i < 3; i++) { rect(ctx, 7 * TILE + 3 + i * 4, 8 * TILE - 2, 3, 3, "#ffffff"); rect(ctx, 7 * TILE + 4 + i * 4, 8 * TILE - 1, 1, 1, "#d9a77c"); } }
      // elevator light: lit while someone is arriving or leaving
      rect(ctx, 10 * TILE - 2, 16 * TILE + 14, 4, 2, w.agents.some((a) => a.npc) ? "#f5c542" : "#5f6b7a");

      // roomba
      rect(ctx, r.x - 4, r.y - 3, 8, 6, "#2b2b2b");
      rect(ctx, r.x - 3, r.y - 4, 6, 8, "#2b2b2b");
      rect(ctx, r.x - 1, r.y - 1, 2, 2, Math.floor(t * 2) % 2 ? "#2ecc71" : "#145a32");

      // people, back to front
      const order = [...w.agents].filter((a) => !a.hidden && !(a.kind === "restroom" && a.arrived)).sort((a, b) => a.y - b.y);
      const evKind = w.event?.kind;
      for (const a of order) drawAgent(ctx, a, t, evKind, sprite);
      drawChairs(ctx);
      // ping pong: a ball going back and forth once both players are at the table
      const pp = w.agents.filter((a) => a.kind === "pingpong" && a.arrived);
      if (pp.length === 2) {
        const k = (t % 1.2) / 1.2, there = k < 0.5 ? k * 2 : 2 - k * 2;
        rect(ctx, 15 * TILE + 2 + there * 44, 12 * TILE + 10 - Math.sin(there * Math.PI * 2 % Math.PI) * 6, 2, 2, "#ffffff");
      }

      // night: lights down, monitors glow
      if (w.sky?.night) {
        ctx.fillStyle = "rgba(6, 6, 30, 0.38)";
        ctx.fillRect(0, 48, WIDTH, HEIGHT);
        ctx.globalCompositeOperation = "lighter";
        for (let i = 0; i < DESKS.length; i++) {
          const d = DESKS[i];
          const g = ctx.createRadialGradient(d.col * TILE + 16, d.row * TILE + 4, 1, d.col * TILE + 16, d.row * TILE + 4, 22);
          g.addColorStop(0, "rgba(90, 200, 255, 0.28)");
          g.addColorStop(1, "rgba(0,0,0,0)");
          ctx.fillStyle = g;
          ctx.fillRect(d.col * TILE - 8, d.row * TILE - 18, 48, 44);
        }
        ctx.globalCompositeOperation = "source-over";
      }
      if (evKind === "disco") {
        ctx.fillStyle = "rgba(10, 0, 30, 0.55)";
        ctx.fillRect(0, 48, WIDTH, HEIGHT);
        ctx.globalCompositeOperation = "lighter";
        for (let i = 0; i < 9; i++) {
          const ang = t * 1.4 + i * 0.7;
          const x = 160 + Math.cos(ang * (1 + i * 0.07)) * (40 + i * 14), y = 160 + Math.sin(ang * 0.9) * (30 + i * 8);
          ctx.fillStyle = CONFETTI[i % CONFETTI.length] + "55";
          ctx.fillRect(x - 6, y - 4, 12, 8);
        }
        ctx.globalCompositeOperation = "source-over";
        rect(ctx, 159, 48, 1, 50, "#9aa8c7");
        for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) rect(ctx, 154 + i * 3, 98 + j * 3, 3, 3, (i + j + Math.floor(t * 8)) % 2 ? "#ffffff" : "#9aa8c7");
      }
      if (evKind === "drill" && Math.floor(t * 3) % 2 === 0) {
        ctx.fillStyle = "rgba(255, 30, 30, 0.22)";
        ctx.fillRect(0, 0, WIDTH, HEIGHT);
      }

      // particles on top
      for (const p of w.particles) drawParticle(ctx, p, t);

      // speech bubbles and the selected person's name, in crisp text
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      const fontPx = Math.max(9, Math.min(12, 9 * css)) * (S / css);
      const maxW = 130 * (S / css);
      ctx.font = `${fontPx}px ${w.font}`;
      ctx.textBaseline = "top";
      const sel = w.selected ?? w.hover;
      const X = (x: number) => x * K + ox, Y = (y: number) => y * K + oy;
      for (const a of order) {
        if (a.key === sel) {
          const y = Y(a.y - (a.arrived && a.target?.sit ? 22 : 26));
          ctx.fillStyle = "#f5c542";
          const bob = Math.round(Math.sin(t * 6) * 1.5) * K;
          ctx.beginPath(); ctx.moveTo(X(a.x) - 3 * K, y + bob); ctx.lineTo(X(a.x) + 3 * K, y + bob); ctx.lineTo(X(a.x), y + 3 * K + bob); ctx.fill();
          if (!a.bubble) bubble(ctx, firstName(a.name), X(a.x), y - 2 * K + bob, fontPx, S, maxW, true);
        }
        if (a.bubble) bubble(ctx, a.bubble.text, X(a.x), Y(a.y - (a.arrived && a.target?.sit ? 20 : 24)), fontPx, S, maxW, false);
      }
      void ppl;
    };

    // Every-frame helpers that need the world
    const onArrive = (a: Agent, now: number) => {
      const w = world.current!;
      if (a.kind === "bell") { w.ringing = now + 3; say(a, "DING DING DING!", 3); }
      if (a.kind === "restroom") { a.hidden = true; setTimeout(() => say(a, "*flush*", 2), (a.dur - 1.5) * 1000); }
      if (a.kind === "coffee") say(a, Math.random() < 0.5 ? pick(CHATTER.coffee) : "☕", 3);
      if (a.kind === "visit") {
        const b = w.agents.find((x) => x.key === a.partner);
        say(a, pick(CHATTER.visit));
        if (b) setTimeout(() => say(b, pick(["Thanks!", "Get your own!", "Shh, I'm working.", "Up " + dollars(Math.max(0, b.pnl)) + ", baby."])), 1800);
      }
      if (a.kind === "fetch") {
        const fish = w.particles.find((p) => p.kind === "fish");
        if (fish) fish.life = fish.max;
        say(a, "Back you go, buddy.", 3);
      }
      if (a.kind === "couch" && a.mood === "sleeping") say(a, "Zzz…", 3);
    };

    raf = requestAnimationFrame(frame);
    const tick = setInterval(() => setTick((n) => n + 1), 5000); // refresh the "what they're doing" card
    return () => { cancelAnimationFrame(raf); ro.disconnect(); clearInterval(tick); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startEvent]);

  // ---------------- input ----------------

  /** Native floor coordinates under the pointer, through the camera. */
  const toFloor = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const cam = world.current?.cam ?? { x: 0, y: 0, z: 1 };
    return {
      x: cam.x + ((e.clientX - box.left) / box.width) * (WIDTH / cam.z),
      y: cam.y + ((e.clientY - box.top) / box.height) * (HEIGHT / cam.z),
    };
  };
  const at = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const { x, y } = toFloor(e);
    const w = world.current;
    if (!w) return null;
    let best: Agent | null = null, dist = 14;
    for (const a of w.agents) {
      if (a.npc || a.hidden) continue;
      const d = Math.hypot(a.x - x, a.y - 8 - y);
      if (d < dist) { dist = d; best = a; }
    }
    return best;
  };

  const w = world.current;
  const sel = selected ? w?.agents.find((a) => a.key === selected) : null;
  const selPerson = selected ? people.find((p) => p.key === selected) : null;

  return (
    <div className="floor">
      <canvas
        ref={canvasRef}
        className="floor-canvas"
        role="img"
        aria-label="The office floor: employees walking around, acting out what they're doing on Kalshi"
        style={{ touchAction: zoomed ? "none" : "manipulation" }}
        onPointerMove={(e) => {
          const w = world.current;
          if (!w) return;
          if (w.drag) {
            // dragging pans the zoomed-in view
            const box = e.currentTarget.getBoundingClientRect();
            const dx = ((e.clientX - w.drag.x) / box.width) * (WIDTH / w.cam.z), dy = ((e.clientY - w.drag.y) / box.height) * (HEIGHT / w.cam.z);
            if (Math.abs(dx) + Math.abs(dy) > 3) w.drag.moved = true;
            if (w.drag.moved) { w.cam.x = w.drag.cx - dx; w.cam.y = w.drag.cy - dy; }
            return;
          }
          const a = at(e);
          w.hover = a?.key ?? null;
          e.currentTarget.style.cursor = a ? "pointer" : w.cam.tz > 1 ? "grab" : "default";
        }}
        onPointerLeave={() => { if (world.current) { world.current.hover = null; world.current.drag = null; } }}
        onPointerDown={(e) => {
          const w = world.current;
          if (!w) return;
          if (w.cam.tz > 1) w.drag = { x: e.clientX, y: e.clientY, cx: w.cam.x, cy: w.cam.y, moved: false };
        }}
        onPointerUp={(e) => {
          const w = world.current;
          if (!w) return;
          const dragged = w.drag?.moved;
          w.drag = null;
          if (dragged) { w.selected = null; setSelected(null); return; }
          const a = at(e);
          w.selected = a?.key ?? null;
          setSelected(a?.key ?? null);
          if (a) { w.cam.tz = 2.2; setZoomed(true); }
        }}
      />
      <div className="floor-bar">
        <button className="btn small" onClick={() => startEvent(pick(EVENT_KINDS.filter((k) => k !== world.current?.event?.kind)))}>🎉 Cause chaos</button>
        <button className="btn small" onClick={() => {
          const w = world.current;
          if (!w) return;
          const z = zoomed ? 1 : 2.2;
          w.cam.tz = z;
          if (!zoomed && !w.selected) { w.cam.x = WIDTH / 2 - WIDTH / z / 2; w.cam.y = HEIGHT / 2 - HEIGHT / z / 2; }
          if (zoomed) { w.selected = null; setSelected(null); }
          setZoomed(!zoomed);
        }}>{zoomed ? "🏢 Whole office" : "🔍 Zoom in"}</button>
        <span className="muted small">{zoomed ? "Drag to look around." : "Tap anyone to follow them."}</span>
      </div>
      {sel && selPerson && (
        <div className="floor-card">
          <Avatar k={sel.key} size={40} />
          <div>
            <strong>{selPerson.name}</strong>
            <div className="muted small">Right now: {ACTIVITY[sel.kind]}. {selPerson.line}</div>
            <div className="small">
              <span className={selPerson.pnl > 0.004 ? "up" : selPerson.pnl < -0.004 ? "down" : "muted"}>{dollars(selPerson.pnl, true)}</span> so far ·{" "}
              <Link href={`/employee/${sel.key}`}>See their page →</Link>
            </div>
          </div>
        </div>
      )}
      <ul className="floor-log" aria-live="polite">
        {log.map((l) => (
          <li key={l.id}><span className="muted small">{l.at}</span> <span aria-hidden>{l.icon}</span> {l.text}</li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Drawing helpers
// ---------------------------------------------------------------------------

type SpriteFn = (a: Agent, dir: Dir, step: Step, sleepy: boolean) => HTMLCanvasElement;

function drawAgent(c: CanvasRenderingContext2D, a: Agent, t: number, ev: EventKind | undefined, sprite: SpriteFn) {
  if (a.key === "pigeon") {
    const hop = a.arrived ? 0 : Math.abs(Math.sin(t * 14)) * 2;
    rect(c, a.x - 3, a.y - 5 - hop, 6, 4, "#8a93a6");
    rect(c, a.x + (a.face === "left" ? -4 : 2), a.y - 7 - hop, 3, 3, "#5f6b7a");
    rect(c, a.x + (a.face === "left" ? -5 : 5), a.y - 6 - hop, 1, 1, "#f5c542");
    return;
  }
  const moving = !a.arrived;
  const sitting = a.arrived && !!a.target?.sit;
  const sleepy = a.mood === "sleeping" && sitting;
  const dir: Dir = a.face === "left" || a.face === "right" ? "side" : a.face;
  const step: Step = moving ? ((Math.floor(a.walkT / 0.14) % 4 === 1 ? 1 : Math.floor(a.walkT / 0.14) % 4 === 3 ? 2 : 0) as Step) : 0;
  const img = sprite(a, dir, step, sleepy || (a.kind === "couch" && a.mood === "sleeping"));
  let bob = 0;
  if (a.arrived && (a.kind === "chant" || a.kind === "dance" || a.kind === "cheer" || a.kind === "party")) bob = Math.abs(Math.sin(t * (a.kind === "chant" ? 7.8 : 9) + a.desk)) * 3;
  if (a.kind === "desk" && a.arrived && t < a.busyUntil) bob = Math.floor(t * 8 + a.desk) % 2;
  if (a.mood === "stressed" && a.arrived && a.kind === "desk") bob = Math.sin(t * 40) > 0 ? 1 : 0;
  if (a.kind === "skate" || a.kind === "rush" || a.kind === "flee") bob = Math.abs(Math.sin(t * 16 + a.desk)) * 1.5;
  const flip = a.face === "left" || (a.kind === "dance" && Math.floor(t * 2 + a.desk) % 2 === 0);
  const x = Math.round(a.x - 6), y = Math.round(a.y - 16 - bob);

  if (a.kind === "couch" && a.arrived && a.mood === "sleeping") {
    // lying down
    c.save();
    c.translate(Math.round(a.x), Math.round(a.y - 4));
    c.rotate(-Math.PI / 2);
    c.drawImage(img, -8, -6);
    c.restore();
    drawZ(c, a.x + 6, a.y - 10, t);
    return;
  }
  const h = sitting && dir === "up" ? 12 : 16;
  const dy = sitting ? (dir === "up" ? 2 : 0) + (sleepy ? 2 : 0) : 0;
  c.save();
  if (flip) { c.translate(x * 2 + 12, 0); c.scale(-1, 1); }
  c.drawImage(img, 0, 0, 12, h, x, y + dy, 12, h);
  c.restore();
  if (a.kind === "skate") { rect(c, a.x - 5, a.y - 1, 4, 2, "#e03c3c"); rect(c, a.x + 1, a.y - 1, 4, 2, "#e03c3c"); rect(c, a.x - 5, a.y + 1, 1, 1, "#f5c542"); rect(c, a.x + 4, a.y + 1, 1, 1, "#f5c542"); }
  // what they're holding
  const hx = flip ? a.x - 7 : a.x + 5, hy = a.y - 7 - bob;
  if (a.carry === "mug" && !sitting) { rect(c, hx, hy, 3, 3, "#ffffff"); rect(c, hx + (flip ? -1 : 3), hy + 1, 1, 1, "#ffffff"); }
  if (a.carry === "snack" && !sitting) rect(c, hx, hy, 3, 4, "#f39c12");
  if (a.carry === "champagne") { rect(c, hx, hy - 6, 2, 8, "#1e5631"); rect(c, hx, hy - 7, 2, 1, "#f5c542"); }
  if (a.carry === "megaphone") { rect(c, hx, hy - 3, 2, 3, "#f5f5f5"); rect(c, hx + 2, hy - 5, 3, 7, "#e03c3c"); }
  if (a.carry === "pizza") { rect(c, a.x - 6, a.y - 9, 12, 3, "#e8c39e"); rect(c, a.x - 6, a.y - 9, 12, 1, "#c79a1e"); }
  if (a.mood === "watching" && a.kind !== "desk" && !moving && !sitting) rect(c, a.x + (flip ? -5 : 4), a.y - 13, 2, 3, "#1a1a1a");
  if (a.key === "band") { rect(c, a.x - 4, a.y - 8, 8, 5, "#f5f5f5"); rect(c, a.x - 4, a.y - 8, 8, 1, "#c0392b"); }
  // moods
  if (sleepy) drawZ(c, a.x + 5, a.y - 18, t);
  if (a.mood === "stressed" && Math.floor(t * 2 + a.desk) % 3 !== 0) rect(c, a.x + 5, a.y - 15 + ((t * 10) % 4), 1, 2, "#7fd3ff");
  if (a.mood === "celebrating" && Math.floor(t * 3 + a.desk) % 2 === 0) { rect(c, a.x - 7, a.y - 20, 2, 3, "#f5c542"); rect(c, a.x + 6, a.y - 22, 2, 3, "#f5c542"); }
  if (a.kind === "bench" && a.arrived) { rect(c, a.x - 6, a.y - 24, 12, 6, "#f5f5f5"); rect(c, a.x - 5, a.y - 22, 10, 1, "#c0392b"); rect(c, a.x - 5, a.y - 20, 7, 1, "#c0392b"); }
  if (a.kind === "chant" && a.arrived && Math.floor(t * 7.8 / Math.PI) % 2 === 0) rect(c, a.x - 2, a.y - 9, 4, 2, "#f2d0b1");
  void ev;
}

function drawZ(c: CanvasRenderingContext2D, x: number, y: number, t: number) {
  for (let i = 0; i < 2; i++) {
    const k = (t * 0.8 + i * 0.5) % 1;
    const zx = x + i * 3 + k * 3, zy = y - k * 8;
    c.globalAlpha = 1 - k;
    rect(c, zx, zy, 3, 1, "#ffffff"); rect(c, zx + 1, zy + 1, 1, 1, "#ffffff"); rect(c, zx, zy + 2, 3, 1, "#ffffff");
    c.globalAlpha = 1;
  }
}

function drawParticle(c: CanvasRenderingContext2D, p: Particle, t: number) {
  const fade = p.kind === "pop" || p.kind === "foam" || p.kind === "note" ? 1 - p.life / p.max : 1;
  c.globalAlpha = Math.max(0, fade);
  switch (p.kind) {
    case "balloon":
      rect(c, p.x - 3, p.y - 4, 6, 6, p.color); rect(c, p.x - 2, p.y - 5, 4, 8, p.color);
      rect(c, p.x - 2, p.y - 3, 1, 2, "rgba(255,255,255,0.6)");
      rect(c, p.x, p.y + 3, 1, 6, "#dddddd");
      break;
    case "bill":
      rect(c, p.x - 3, p.y - 1, 6, 3, Math.sin(t * 6 + p.seed) > 0 ? "#2ecc71" : "#27ae60");
      rect(c, p.x - 1, p.y, 2, 1, "#145a32");
      break;
    case "plane":
      rect(c, p.x - 3, p.y, 6, 1, "#ffffff"); rect(c, p.x + (p.vx > 0 ? 1 : -2), p.y - 1, 2, 1, "#ffffff"); rect(c, p.x - 1, p.y + 1, 3, 1, "#cfd8dc");
      break;
    case "note":
      rect(c, p.x, p.y, 1, 4, p.color); rect(c, p.x - 2, p.y + 3, 2, 2, p.color); rect(c, p.x + 1, p.y, 2, 1, p.color);
      break;
    case "cork":
      rect(c, p.x, p.y, 2, 2, p.color);
      break;
    case "fish":
      rect(c, p.x - 2, p.y - 2, 4, 3, p.color); rect(c, p.x + (Math.sin(t * 20) > 0 ? 2 : -3), p.y - 2, 1, 3, p.color);
      break;
    default:
      rect(c, p.x, p.y, p.kind === "confetti" ? (Math.sin(t * 10 + p.seed) > 0 ? 2 : 1) : 2, 2, p.color);
  }
  c.globalAlpha = 1;
}

/** The big board: the desk's profit as a line graph, plus bitcoin's price. */
function drawBoard(c: CanvasRenderingContext2D, series: Point[], total: number, btc: number | null, t: number, S: number, ox: number, oy: number, font: string) {
  const x0 = 116, x1 = 220, y0 = 18, y1 = 40;
  rect(c, 114, 5, 108, 36, "#07060f");
  if (series.length > 1) {
    const ts = series.map((p) => p.t), vs = series.map((p) => p.v).concat(total, 0);
    const tmin = Math.min(...ts), tmax = Math.max(...ts), lo = Math.min(...vs), hi = Math.max(...vs);
    const X = (v: number) => x0 + ((v - tmin) / (tmax - tmin || 1)) * (x1 - x0);
    const Y = (v: number) => y1 - ((v - lo) / (hi - lo || 1)) * (y1 - y0);
    rect(c, x0, Y(0), x1 - x0, 1, "#2a2650");
    c.strokeStyle = total >= 0 ? "#2ecc71" : "#e74c3c";
    c.lineWidth = 1;
    c.beginPath();
    series.forEach((p, i) => (i ? c.lineTo(X(p.t), Y(p.v)) : c.moveTo(X(p.t), Y(p.v))));
    c.lineTo(x1, Y(total));
    c.stroke();
    if (Math.floor(t * 2) % 2) rect(c, x1 - 1, Y(total) - 1, 3, 3, total >= 0 ? "#2ecc71" : "#e74c3c");
  }
  // text in crisp pixels
  c.save();
  c.setTransform(1, 0, 0, 1, 0, 0);
  c.textBaseline = "top";
  c.font = `${Math.round(4.5 * S)}px ${font}`;
  c.fillStyle = "#f5c542";
  c.fillText("DESK", 118 * S + ox, 8 * S + oy);
  c.fillStyle = total >= 0 ? "#2ecc71" : "#e74c3c";
  c.fillText(dollars(total, true), 140 * S + ox, 8 * S + oy);
  if (btc) {
    c.fillStyle = "#7fd3ff";
    c.textAlign = "right";
    c.fillText(`BTC ${Math.round(btc).toLocaleString()}`, 219 * S + ox, 8 * S + oy);
  }
  c.restore();
}

function bubble(c: CanvasRenderingContext2D, text: string, x: number, y: number, fontPx: number, S: number, maxW: number, tag: boolean) {
  const words = text.split(" ");
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    const tryLine = cur ? `${cur} ${w}` : w;
    if (c.measureText(tryLine).width > maxW && cur) { lines.push(cur); cur = w; } else cur = tryLine;
  }
  if (cur) lines.push(cur);
  const lh = fontPx * 1.35;
  const pad = fontPx * 0.5;
  const w = Math.max(...lines.map((l) => c.measureText(l).width)) + pad * 2;
  const h = lines.length * lh + pad * 1.4;
  const cw = c.canvas.width;
  const bx = Math.max(2, Math.min(cw - w - 2, x - w / 2));
  const by = Math.max(2, y - h);
  c.fillStyle = tag ? "#f5c542" : "#ffffff";
  c.fillRect(bx, by, w, h);
  c.fillStyle = "#1a1a1a";
  const b = Math.max(1, Math.round(S / 2));
  c.fillRect(bx, by - b, w, b); c.fillRect(bx, by + h, w, b); c.fillRect(bx - b, by, b, h); c.fillRect(bx + w, by, b, h);
  if (!tag) {
    c.fillStyle = "#ffffff";
    c.beginPath(); c.moveTo(x - S * 2, by + h); c.lineTo(x + S * 2, by + h); c.lineTo(x, by + h + S * 3); c.fill();
  }
  c.fillStyle = "#1a1a1a";
  c.textAlign = "left";
  lines.forEach((l, i) => c.fillText(l, bx + pad, by + pad * 0.8 + i * lh));
}
