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
  heavy_favorite: {
    up: ["Another penny in the jar.", "Ninety-two cents or I don't play.", "Small, steady, logged.", "Five coins, five pennies. Lovely."],
    down: ["One upset. Thirty pennies gone. Recounting.", "That's what the jar is for.", "Noted in the ledger. Moving on."],
    idle: ["Nothing at 92 cents yet.", "Waiting for the middle of the window.", "Jar's ready."],
  },
  late_maker: {
    up: ["Last call, and somebody sold. Hoo.", "Two minutes left, a tenth of a cent under. Lovely.", "The night shift pays.", "Never paid retail after dark."],
    down: ["One last-minute surprise. There's always one.", "Hoo-boy. That one turned at the buzzer.", "Back to my tea. Next window."],
    idle: ["Too early. Wake me at five minutes.", "Bid's out. Lights are low.", "Nothing worth staying up for yet."],
  },
  runner_up_maker: {
    up: ["Second favorite, first place. For once.", "Not the sure thing. Still a win.", "I'll take silver. I'll take it every time.", "Bronze is for quitters."],
    down: ["Second again. I'm used to it.", "Close. Always close.", "That's what happens when it's only 88 cents sure."],
    idle: ["Nothing in the 85-92 range. Stretching.", "Waiting in the runner-up lane.", "Polishing the medal."],
  },
  heavy_maker: {
    up: ["Somebody always sells. I just wait.", "A tenth of a cent under, and no fee. Lovely.", "Slow and steady fills the jar.", "Didn't even have to get up."],
    down: ["They sold me that one for a reason. Noted.", "The snail and I will think about this.", "Even patient pennies get squashed."],
    idle: ["Bid's out. Kettle's on.", "Nobody's selling yet. That's fine.", "Waiting for the middle of the window."],
  },
  maker_btc: {
    up: ["Another coin on the dam.", "Gnawed right through that sell order.", "Busy river, steady dam."],
    down: ["A leak in the dam. Patching.", "Bitcoin washed that one downstream.", "Timber! That one fell the wrong way."],
    idle: ["Hard hat on, bid out.", "Waiting for something to float by.", "No bitcoin favorite yet. Chewing a stick."],
  },
  maker_eth: {
    up: ["Ooooo… filled.", "I drifted through the order book and came back richer.", "Boo. Pennies."],
    down: ["Even ghosts get spooked.", "Ether turned at the last second. Most unrestful.", "Rattling my chains about that one."],
    idle: ["Haunting the middle of the window.", "Bid's out. I have all eternity.", "No ether favorite yet. Floating."],
  },
  maker_sol: {
    up: ["Warm favorite, quick tongue.", "Sun's out, pennies in.", "Basked. Bid. Paid."],
    down: ["Clouded over. Shedding this one.", "Cold-blooded about it. Mostly.", "Solana got burned. So did my tail."],
    idle: ["Basking until five minutes in.", "On the radiator, bid ready.", "No sunny favorites yet."],
  },
  maker_xrp: {
    up: ["The tide came in, like always.", "All eight arms, all paid.", "Steady as she goes."],
    down: ["Rogue wave. Man the pumps.", "Inked that one. Badly.", "XRP pulled the tide out early."],
    idle: ["Watching the tide from the bridge.", "Bid's at the waterline.", "No XRP favorite yet. Puffing the pipe."],
  },
  maker_doge: {
    up: ["Such win. Very penny.", "Much patience. Wow.", "Good boy got a treat."],
    down: ["No treat this time. Very sad.", "Doge chased own tail. Regret.", "Such loss. Much ouch."],
    idle: ["Sitting. Staying. Side-eyeing.", "Waiting for treat to come to me.", "No dogecoin favorite yet. Wow."],
  },
  maker_hype: {
    up: ["CHEEKS FULL!", "Four espressos, four fills!", "Believe the hype!"],
    down: ["Fell off the wheel.", "Okay, that was overhyped.", "Need another espresso."],
    idle: ["Running laps until a favorite shows.", "Wheel's spinning, bid's sitting.", "No HYPE favorite yet."],
  },
  maker_bnb: {
    up: ["Bzz. Honey.", "A tenth of a cent, a drop of honey.", "Back to the hive with that one."],
    down: ["Stung. Happens.", "That flower was plastic.", "Bad batch of nectar."],
    idle: ["Buzzing around the window.", "Hive's quiet. Bid's out.", "No BNB favorite yet."],
  },
  maker_near: {
    up: ["Didn't see it coming, but it paid.", "Right in front of my nose. Lovely.", "Nearly certain, fully paid."],
    down: ["Should've worn the other glasses.", "Dug into the wrong tunnel.", "A near miss. Literally."],
    idle: ["Squinting at the order book.", "It's around here somewhere.", "No NEAR favorite yet."],
  },
  maker_zec: {
    up: ["No comment.", "Shielded profit.", "Didn't see me, did you?"],
    down: ["Off the record: ouch.", "Bad dumpster tonight.", "Pretend you didn't see that."],
    idle: ["Lurking behind the exchange.", "Mask on, bid ready.", "No zcash favorite yet."],
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
  weather_maker: {
    up: ["Called it before the flies woke up.", "Ribbit. Pennies.", "Six skies, one frog, a few cents.", "Didn't forecast a thing. Didn't need to."],
    down: ["The sky had other plans.", "One degree. One whole degree.", "Wet in all the wrong ways."],
    idle: ["Climbing the ladder in my jar. Waiting for midnight.", "No favorites worth a croak this morning.", "Watching six skies."],
  },
  sports_closer: {
    up: ["Game over. Whistle blown. Penny pocketed.", "No comeback on my watch.", "Final whistle, final answer.", "That's the game."],
    down: ["Missed the call. It happens to the best.", "Ninety-eight cents sure. Yellow card for me.", "Should've gone to overtime."],
    idle: ["No game's decided yet.", "Waiting for the fourth quarter.", "Checking the scoreboard. Stripes ironed."],
  },
  hourly_btc: {
    up: ["Acorn stashed before the bell.", "Tick, tock, pocketed.", "Bong! Another hour, another nut.", "Down the tower and back up, richer."],
    down: ["The bell rang the wrong way.", "Dropped that acorn.", "Bitcoin climbed faster than I did."],
    idle: ["Waiting for the minute hand.", "Nothing sure enough this hour.", "Winding the watch."],
  },
  maker_gold: {
    up: ["Shiny! Into the nest.", "Gold at 97 cents? Mine.", "Another glittery one for the collection."],
    down: ["Fool's gold. Squawk.", "That one tarnished.", "Dropped it on the way home."],
    idle: ["Nothing shiny enough yet.", "Watching for a glint.", "Polishing the nest."],
  },
  maker_wti: {
    up: ["Struck oil. Modestly.", "Barrel in, barrel out, penny pocketed.", "Steady pressure. Good well."],
    down: ["Dry hole.", "Spilled that one. Mopping up.", "Crude awakening."],
    idle: ["Rig's quiet.", "No gusher yet. Sipping coffee on the platform.", "Checking the gauges."],
  },
  maker_silver: {
    up: ["Splendid. Sterling, even.", "A polished little win.", "Silver lining, as promised."],
    down: ["Tarnished. How vulgar.", "I shall polish my pride.", "A rare misstep for a fox."],
    idle: ["Polishing the spoons.", "Nothing worth a silver fox's attention.", "Adjusting the waistcoat."],
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
  // One or two plain sentences each (11-16): what they bet on, when, and why it should work
  maker_btc: "Bets on bitcoin only. With 5–9 minutes left in each 15-minute window, he offers to buy whichever side is a 92–99¢ favorite and waits for a seller, skipping it when bitcoin's own price says the favorite is shakier than it looks.",
  maker_eth: "Bets on ether only. With 5–9 minutes left in each 15-minute window, she offers to buy whichever side is a 92–99¢ favorite and waits for a seller, skipping it when ether's own price says the favorite is shakier than it looks.",
  maker_sol: "Bets on solana only. With 5–9 minutes left in each 15-minute window, he offers to buy whichever side is a 92–99¢ favorite and waits for a seller, skipping it when solana's own price says the favorite is shakier than it looks.",
  maker_xrp: "Bets on XRP only. With 5–9 minutes left in each 15-minute window, she offers to buy whichever side is a 92–99¢ favorite and waits for a seller, skipping it when XRP's own price says the favorite is shakier than it looks.",
  maker_doge: "Bets on dogecoin only. With 5–9 minutes left in each 15-minute window, he offers to buy whichever side is a 92–99¢ favorite and waits for a seller, skipping it when dogecoin's own price says the favorite is shakier than it looks.",
  maker_bnb: "Bets on BNB only. With 5–9 minutes left in each 15-minute window, she offers to buy whichever side is a 92–99¢ favorite and waits for a seller, skipping it when BNB's own price says the favorite is shakier than it looks.",
  maker_near: "Bets on NEAR only. With 5–9 minutes left in each 15-minute window, he offers to buy whichever side is a 92–99¢ favorite and waits for a seller, skipping it when NEAR's own price says the favorite is shakier than it looks.",
  maker_zec: "Bets on zcash only. With 5–9 minutes left in each 15-minute window, he offers to buy whichever side is a 92–99¢ favorite and waits for a seller, skipping it when zcash's own price says the favorite is shakier than it looks.",
  maker_hype: "Bets on HYPE only. With 5–9 minutes left in each 15-minute window, he offers to buy whichever side is a 92–99¢ favorite and waits for a seller, skipping it when HYPE's own price says the favorite is shakier than it looks. Training only: HYPE trades thinly, so it's still being tested.",
  hourly_btc: "Bets on bitcoin's hourly markets (\"above $87,000 at 3 pm?\"). In the last half hour before each bell, she offers to buy the 92–99.5¢ favorite on each price rung and waits for a seller. Several rungs often win or lose together.",
  weather_maker: "Bets on the day's high temperature in six cities. Between midnight and 6 am local time he offers to buy the 92–99.5¢ favorite and waits for a seller. He doesn't forecast; two years of Kalshi's trades say the favorites are slightly underpriced at that hour.",
  sports_closer: "Bets on basketball, baseball and hockey games that are all but decided, buying the 97–99.5¢ side near the end. Training only.",
  heavy_maker: "Retired Oct 31. Her bets on 92–99¢ coin favorites were split between the eight coin specialists, who still use her rules.",
  heavy_favorite: "Buys coin favorites at 92–99¢ with 5–9 minutes left, paying the asking price. Benched: the fees ate the edge.",
  late_maker: "Offers to buy 94–99¢ coin favorites in the last 2–5 minutes. Benched: that stretch lost money.",
  runner_up_maker: "Offers to buy 85–92¢ coin favorites with 5–13 minutes left. Benched until there's more proof.",
  nickel_picker: "Buys 88–95¢ favorites with 10+ minutes left: wins small and often, loses big now and then. Training only.",
  nickel_maker: "Like Nick, but offers a little less and waits for a seller. Training only.",
  longshot_fade: "Bets against long shots priced 5–15¢. Training only.",
  breakout: "Bets that a big bitcoin move keeps going, before Kalshi's price catches up. Training only.",
  breakout_maker: "Like Wipeout, but offers a lower price and waits. Training only.",
  early_favorite: "Buys 75–85¢ favorites the moment a 15-minute window opens. Training only.",
  early_maker: "Like Edie, but offers a lower price and waits. Training only.",
  sniper: "Bets in the last five minutes when bitcoin is far from the line. Training only.",
  maker_gold: "Gold's 15-minute markets on the coin team's rules, 97¢+ favorites only. Training only.",
  maker_wti: "Oil's 15-minute markets on the coin team's rules, 97¢+ favorites only. Training only.",
  maker_silver: "Silver's 15-minute markets on the coin team's rules, 97¢+ favorites only. Training only.",
  longshot_buy: "Buys cheap long shots at random: the yardstick the long-shot strategies must beat. Pretend money only.",
  dart_monkey: "Bets at random: the yardstick every strategy must beat. Pretend money only.",
};
