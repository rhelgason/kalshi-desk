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
  sniper: "The Sniper lies in the grass until the last five minutes of each 15-minute window, then takes the shot when bitcoin is far enough from the line that she's 80%+ sure. Training only: on replays her late shots have lost, so she's practicing before she gets real money.",
  nickel_picker: "Nick buys whichever side is already a heavy favorite (88–95¢) with at least 10 minutes to go. He wins most bets for a few cents each, the way he's saved every nickel since 1962, but one upset can wipe out a dozen wins.",
  heavy_favorite: "Stella waits until a 15-minute window is half over (5 to 9 minutes left), then buys whichever side is already a heavy favorite at 92–99¢, on bitcoin, ether, solana, XRP and dogecoin. Each win is a penny or two per dollar; a loss costs the whole bet, so she needs to win about 19 times in 20. Her rule was picked from 4,700 tested ones because it kept working on months it was never tuned on. The edge is small and could still be luck.",
  longshot_fade: "When one side costs only 5–15¢, the Wet Blanket buys the other side and tells you why the long shot never had a chance. Like Nick, he wins small and often, and loses big (and sulks) on the occasional surprise.",
  breakout: "When bitcoin has jumped or dropped 0.3%+ in the last 15 minutes, Wipeout paddles hard and bets it keeps going, but only if Kalshi's price hasn't caught up yet (still under 60¢). Bitcoin only, Training only for now: the waves haven't been kind.",
  early_favorite: "The moment a new 15-minute window opens, Edie (already on her third coffee) grabs the side that's a clear but not certain favorite (75–85¢), betting the early price is a little too cautious.",
  late_maker: "Coco works the last stretch of every 15-minute window: with 2 to 5 minutes left, she bids a tenth of a cent over the best bid on whichever side is a 94–99¢ favorite and waits for someone to sell. No fee when she's filled. She starts where Sadie stops, so they rarely bid at the same moment. In the 10-month backtest she held up in both halves and every month. Training only for now.",
  runner_up_maker: "Sid bets on the second tier of favorites: 85–92¢ with 5 to 13 minutes left, a resting bid a cent over the best bid. Wins less often than the 92¢+ crowd, but each win pays more. On probation: his rule looked good in the backtest, but it was picked after seeing all the data, so he practices on pretend money until his live record says otherwise.",
  heavy_maker: "Stella's twin. Same heavy favorites (92–99¢, 5 to 9 minutes left), but instead of paying the asking price she bids a tenth of a cent over the best bid and waits up to two minutes for someone to sell. Kalshi charges nothing when someone fills a waiting bid, and there's no per-order fee to round up, which on small bets costs Stella more than her whole edge. Retired Oct 31: her bets this season were handed to the five coin specialists, one coin each, who carry on with her rules.",
  maker_btc: "Barnaby works Sadie's rules on bitcoin only: with 5 to 9 minutes left in a 15-minute window, a bid a tenth of a cent over the best bid on a 92–99¢ favorite, skipped when the coin's own price says the favorite is shakier than its price. He takes Sadie's settings, so tuning Sadie tunes him too.",
  maker_eth: "Ethel haunts ether only, on Sadie's rules: with 5 to 9 minutes left in a 15-minute window, a bid a tenth of a cent over the best bid on a 92–99¢ favorite, skipped when the coin's own price says the favorite is shakier than its price. She takes Sadie's settings, so tuning Sadie tunes her too.",
  maker_sol: "Sunny basks on solana only, on Sadie's rules: with 5 to 9 minutes left in a 15-minute window, a bid a tenth of a cent over the best bid on a 92–99¢ favorite, skipped when the coin's own price says the favorite is shakier than its price. He takes Sadie's settings, so tuning Sadie tunes him too.",
  maker_xrp: "The Captain sails XRP only, on Sadie's rules: with 5 to 9 minutes left in a 15-minute window, a bid a tenth of a cent over the best bid on a 92–99¢ favorite, skipped when the coin's own price says the favorite is shakier than its price. She takes Sadie's settings, so tuning Sadie tunes her too.",
  maker_doge: "Mochi watches dogecoin only, on Sadie's rules: with 5 to 9 minutes left in a 15-minute window, a bid a tenth of a cent over the best bid on a 92–99¢ favorite, skipped when the coin's own price says the favorite is shakier than its price. He takes Sadie's settings, so tuning Sadie tunes him too.",
  maker_hype: "Hank runs Hyperliquid's HYPE only, on Sadie's rules: with 5 to 9 minutes left in a 15-minute window, a bid a tenth of a cent over the best bid on a 92–99¢ favorite, skipped when the coin's own price says the favorite is shakier than its price. He takes Sadie's settings, so tuning Sadie tunes him too. Hired Nov 2 on Training to see whether the edge carries over to Kalshi's thinner coins (each trades about half of dogecoin's volume).",
  maker_bnb: "Belle works BNB only, on Sadie's rules: with 5 to 9 minutes left in a 15-minute window, a bid a tenth of a cent over the best bid on a 92–99¢ favorite, skipped when the coin's own price says the favorite is shakier than its price. She takes Sadie's settings, so tuning Sadie tunes her too. Hired Nov 2 for one of Kalshi's thinner coins; passed the same 9-week trade-record test as the others and bets real money since that day.",
  maker_near: "Ned digs into NEAR only, on Sadie's rules: with 5 to 9 minutes left in a 15-minute window, a bid a tenth of a cent over the best bid on a 92–99¢ favorite, skipped when the coin's own price says the favorite is shakier than its price. He takes Sadie's settings, so tuning Sadie tunes him too. Hired Nov 2 for one of Kalshi's thinner coins; passed the same 9-week trade-record test as the others and bets real money since that day.",
  maker_zec: "Zed lurks on zcash only, on Sadie's rules: with 5 to 9 minutes left in a 15-minute window, a bid a tenth of a cent over the best bid on a 92–99¢ favorite, skipped when the coin's own price says the favorite is shakier than its price. He takes Sadie's settings, so tuning Sadie tunes him too. Hired Nov 2 for one of Kalshi's thinner coins; passed the same 9-week trade-record test as the others and bets real money since that day.",
  nickel_maker: "Nick's twin sister and the office's coupon queen. She picks the same heavy favorites, but instead of paying the asking price she offers a little less and waits up to two minutes for someone to sell. Cheaper, and no fee, but she misses some bets and tends to get filled when the price is slipping.",
  early_maker: "Edie's calm twin. Same early favorites, but she names a slightly lower price and knits while she waits for a seller. Kalshi charges no fee on a bid that someone else fills, so every win is worth a bit more, if she gets filled at all.",
  breakout_maker: "Wipeout's twin sister. When bitcoin makes a big move she bets it keeps going like Wipeout does, but from an inflatable flamingo: she posts a lower price and waits for the wave to come to her. Wipeout's bets are near 50¢, where Kalshi's fee is biggest, so Bonnie saves the most by not paying it. Training only for now.",
  weather_maker: "Wendell works Kalshi's daily high-temperature markets in six cities (New York, Los Angeles, Chicago, Miami, Austin, Denver). From midnight to 6 am city time on the day itself, he bids a cent over the best bid on whichever side of a temperature bracket is a 92–99.5¢ favorite, and waits for someone to sell. Weather charges no fee on a waiting bid. He never tries to forecast: free forecasts lost badly against Kalshi's prices. On two years of Kalshi's real trades, bids like his from midnight to 6 am made about 1.5¢ per $1, up in both years and all six cities, but there are only a few a day. On real money since Nov 3.",
  sports_closer: "Ziggy bets basketball, baseball and hockey games once they're all but decided: a side priced 97–99.5¢ gets a bid a cent over the best bid, one per game, until 2 hours after Kalshi expects the game to end. Basketball from 3 hours before that; baseball and hockey only from the last hour, because a year of Kalshi's real trades showed those two lose money earlier (late comebacks) and earn about +1.5¢ / +0.7¢ per $1 after. Football didn't pay, so he dropped it. Training only.",
  hourly_btc: "Hazel works Kalshi's hourly bitcoin markets (\"will bitcoin be above $87,000 at 3 pm?\"), a ladder of prices that each close on the hour. From 21 minutes to 5 minutes before the bell, she bids a tenth of a cent over the best bid on whichever side of a rung is a 92–99.5¢ favorite and waits for someone to sell, the same idea as the coin team's 15-minute bets. Makers pay no fee there. On a month of Kalshi's real trades, bids like hers made about 0.6¢ per $1, up in both halves of the month at every distance from the bell: about half what the coin team makes, so she's on trial. Each hour gets its own share of the pool's window cap, so she never crowds the coin team. Training only for now.",
  maker_gold: "Goldie works Kalshi's 15-minute gold markets on Sadie's rules: with 5 to 9 minutes left, a bid a tenth of a cent over the best bid on a 97¢+ favorite, waiting for someone to sell. On two months of Kalshi's real trades, bids like hers made about 1¢ per $1, steadiest on the surest favorites, but less reliably than the coins (one half of the period barely broke even). There's no free second-by-second gold price to double-check against, though a gold-backed token is being tested for one. Training only.",
  maker_wti: "Clyde works Kalshi's 15-minute oil (WTI) markets on Sadie's rules: with 5 to 9 minutes left, a bid a tenth of a cent over the best bid on a 97¢+ favorite. On two months of Kalshi's real trades, oil's surest favorites made about 1.7¢ per $1, up in both halves; all of oil's favorites together made about 0.9¢. No free second-by-second oil price exists to double-check his bets, so he bids on the market's word alone. Training only.",
  maker_silver: "Sterling works Kalshi's 15-minute silver markets on Sadie's rules: with 5 to 9 minutes left, a bid a tenth of a cent over the best bid on a 97¢+ favorite. On two months of Kalshi's real trades, silver's surest favorites made about 1¢ per $1, up in both halves; all of silver's favorites together made about 0.7¢. Like Clyde, he has no live price to double-check with. Training only.",
  longshot_buy: "Pecks at the cheap long shots the Wet Blanket bets against. He's a yardstick on pretend money only: if the Wet Blanket can't beat a pigeon, the idea doesn't work.",
  dart_monkey: "Bets at random. He's the yardstick everyone has to beat, on pretend money only: if a strategy can't do better than a monkey with darts, it isn't really a strategy.",
};
