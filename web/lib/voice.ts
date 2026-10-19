import type { Employee } from "./types";

type Lines = { up: string[]; down: string[]; idle: string[] };

/** How each employee would describe their day, in their own words (a different line every hour or so). */
const LINES: Record<string, Lines> = {
  sniper: {
    up: ["Target down.", "One shot. That's all it takes.", "Told you. Patience.", "…"],
    down: ["Wind shifted.", "Missed. Resetting.", "Even I miss sometimes. Not often."],
    idle: ["Shh. Waiting for the shot.", "In position.", "Not yet. Not yet…"],
  },
  nickel_picker: {
    up: ["Another nickel for the jar.", "A penny saved is a penny I bet tomorrow.", "Back in my day, a nickel was a nickel.", "Ka-ching. Quietly."],
    down: ["The steamroller got me. Again.", "I'll be reusing this tea bag for a week.", "That one cost me a lot of nickels."],
    idle: ["No sure things yet. I'll wait.", "Counting my change. Twice.", "Nothing worth the shoe leather."],
  },
  nickel_maker: {
    up: ["Never paid full price in my life, darling.", "Got it at a discount. As always.", "Clip, clip, cash.", "Retail is for amateurs."],
    down: ["They only sold because it was going bad. Rude.", "Even a bargain can be a bad deal.", "Returning this one. Oh wait, I can't."],
    idle: ["My bid's out there. I can wait.", "Not paying that. Next.", "Coupons ready."],
  },
  longshot_fade: {
    up: ["Long shots never hit. Told you.", "Statistically, no. Again.", "Your lottery ticket lost. You're welcome.", "Not to be that guy, but… I was right."],
    down: ["One actually hit. Ugh.", "That was a one-in-ten. Unbelievable.", "I'm not upset. I'm disappointed."],
    idle: ["Nothing silly to bet against yet.", "Waiting for someone to get excited.", "Arms crossed. Standing by."],
  },
  longshot_buy: {
    up: ["TOLD YOU! It only has to hit once!", "Scratch, scratch, WINNER!", "Feeling lucky? I always am."],
    down: ["The next one's the one.", "So close. I could feel it.", "Lucky toothpick's just warming up."],
    idle: ["Looking for lottery tickets.", "Anything under 12 cents? Anyone?", "Feelin' lucky."],
  },
  breakout: {
    up: ["Cowabunga! Caught the wave!", "Shredded that one!", "Stoked, dude. Totally stoked."],
    down: ["Wiped out. Paddling back.", "Ate it on that one. Big time.", "Gnarly crash. Going again."],
    idle: ["Flat seas. Waiting for bitcoin to swell.", "Waxing the board.", "Watching the horizon."],
  },
  breakout_maker: {
    up: ["Caught the wave without even paddling.", "Mmm. Nice. Floated right into that one.", "Effort is overrated."],
    down: ["The wave broke on me.", "Flipped off the flamingo. Ugh.", "Too relaxed? Never."],
    idle: ["Floating. Waiting for a swell.", "Five more minutes…", "Working on my tan, technically."],
  },
  early_favorite: {
    up: ["COCK-A-DOODLE-PROFIT!", "Early bird gets the worm!", "Three coffees, three wins!"],
    down: ["Picked the wrong horse. Need more coffee.", "Ugh. Too early for that.", "Fine. FINE. Next window!"],
    idle: ["Waiting for the next window to open!", "Is it time yet? Is it time yet?", "Refilling the mug."],
  },
  early_maker: {
    up: ["Let them come to me.", "Another row done, another bid filled.", "Lovely. More tea?"],
    down: ["They only sold when it was going wrong.", "Dropped a stitch.", "Oh dear. Never mind."],
    idle: ["Bid's posted. Kettle's on.", "Knit one, purl one, wait.", "No rush, dear."],
  },
  dart_monkey: { up: ["Ook! 🍌"], down: ["Ook…"], idle: ["Ook?"] },
};
const DEFAULT: Lines = { up: ["Up and to the right."], down: ["Rough patch."], idle: ["Waiting."] };

/** One line, in character, about how it's going (changes about once an hour, same for everyone looking). */
export function quip(e: Employee): string {
  if (e.status === "fired") return "Packing up my desk.";
  if (e.status === "suspended") return "Riding the bench.";
  const l = LINES[e.key] ?? DEFAULT;
  const pnl = e.pnl ?? 0;
  const pool = !(e.fills ?? 0) && Math.abs(pnl) < 0.005 ? l.idle : pnl >= 0 ? l.up : l.down;
  const seed = Math.floor(Date.now() / 3_600_000) + [...e.key].reduce((s, ch) => s + ch.charCodeAt(0), 0);
  return pool[seed % pool.length];
}

/** What each employee actually does, in plain words, for their page. */
export const HOW_THEY_BET: Record<string, string> = {
  sniper: "Dee lies in the grass until the last five minutes of each 15-minute window, then only takes the shot when bitcoin is so far from the line that she's 90%+ sure. Rare bets, mostly small wins, very little conversation.",
  nickel_picker: "Nick buys whichever side is already a heavy favorite (88–95¢) with at least 10 minutes to go. He wins most bets for a few cents each, the way he's saved every nickel since 1962, but one upset can wipe out a dozen wins.",
  longshot_fade: "When one side costs only 5–15¢, Bill buys the other side and tells you why the long shot never had a chance. Like Nick, he wins small and often, and loses big (and sulks) on the occasional surprise.",
  breakout: "When bitcoin has jumped or dropped sharply in the last 15 minutes, Betty paddles hard and bets it keeps going, but only if Kalshi's price hasn't caught up yet (still under 60¢). Training only for now: the waves haven't been kind.",
  early_favorite: "The moment a new 15-minute window opens, Edie (already on her third coffee) grabs the side that's a clear but not certain favorite (75–85¢), betting the early price is a little too cautious.",
  nickel_maker: "Nick's twin sister and the office's coupon queen. She picks the same heavy favorites, but instead of paying the asking price she offers a little less and waits up to two minutes for someone to sell. Cheaper, and no fee, but she misses some bets and tends to get filled when the price is slipping.",
  early_maker: "Edie's calm twin. Same early favorites, but she names a slightly lower price and knits while she waits for a seller. Kalshi charges no fee on a bid that someone else fills, so every win is worth a bit more, if she gets filled at all.",
  breakout_maker: "Betty's twin. When bitcoin makes a big move she bets it keeps going like Betty does, but from an inflatable flamingo: she posts a lower price and waits for the wave to come to her. Betty's bets are near 50¢, where Kalshi's fee is biggest, so Bonnie saves the most by not paying it. Training only for now.",
  longshot_buy: "Buys the cheap long shots Bill bets against, with a lucky toothpick. He's a yardstick on pretend money only: if Bill can't beat Lenny, Bill's idea doesn't work.",
  dart_monkey: "Bets at random. He's the yardstick everyone has to beat, on pretend money only: if a strategy can't do better than a monkey with darts, it isn't really a strategy.",
};
