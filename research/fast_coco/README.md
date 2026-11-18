# Fast Coco: what an always-on server adds (2026-10-25)

A second-by-second replay of Closing Time Coco's rules on 61 days (Aug 25 - Oct 25, 2026) of ETH, SOL, XRP and DOGE
15-minute markets: 22,737 markets, Kalshi's real trade tape for each market's last 6 minutes, Binance 1-second prices.

| Version | Bets | Lost | Per $1 | $87.63 after 61 days (3% bets, $10 cap) |
|---|---|---|---|---|
| Always-on bid, follows the price (any pull setting, joining or improving) | ~16,400 | 4.2% | +0.13c | ~$88 |
| Today's Coco: a 110 s bid at each 2-minute look (no server) | 8,148 | 2.6% | +0.55c | $278 |
| **Coco + pull the bid on a 1-sigma coin move within 2 s (the server)** | 6,741 | 2.4% | **+0.86c** | **$402** |

The pull setting was picked on the first half (+0.78c -> +1.21c) and held on the second (+0.33c -> +0.54c); it
helped on every coin. An always-on bid is the one that gets hit just before the price turns. Full output: RESULTS.txt.

Limits: fills are estimated from the tape (through our price = filled, at it = 30% queue share), the book between
minute quotes is inferred from trades, and the coin price is Binance's (the live bot uses Coinbase). The edge
shrank from the first month to the second, as everywhere else.

```bash
python tape.py 61 6 data/tape60 KXSOL15M KXDOGE15M KXXRP15M KXETH15M   # ~2 h; resumable (salvage.py fixes a torn file)
python replay_fast.py data/tape60 data/binance1s data/history-full.db out.json SOL DOGE XRP ETH
python sum_fast.py out.json
```
Binance files: https://data.binance.vision/data/spot/daily/klines/<COIN>USDT/1s/<COIN>USDT-1s-<YYYY-MM-DD>.zip

## The final minute with the official index (2026-10-26)

Kalshi settles each 15-minute coin market on the average of the last 60 one-second values of CF Benchmarks' index.
Kalshi passes that index through to any API key: live (`cfbenchmarks_value`, with the running final-minute average;
`cfbenchmarks_value_5hz`) and history (`/cfbenchmarks/history/values`, back to at least Dec 2025; DOGE history has only
4 decimals, too coarse). `index_history.py` downloads it (it reproduces official settle and strike values to the cent);
`buzzer.py` tests bidding in the final minute when the index odds beat the best bid; `buzzer_taker.py` tests taking.

Aug 25 - Oct 25, ETH/SOL/XRP, harsh fills (a sweep through our price fills us in full):
- Without the index (Binance), naive final-seconds bids lose 2-7c per $1. All makers together earn +2-7c there, so the
  money goes to informed makers who cancel in time.
- With the index, reacting in 0.2 s: ETH +0.9 to +1.9c, SOL -0.8 to -6c, XRP -0.04 to -4c; all three -0.3 to -4.4c,
  ~25 of 62 days up. Reacting in 1 s is worse everywhere. The more the index disagrees with the price, the more a bid
  loses: the sellers who hit it know more. Taking the ask when the index says it's cheap: -0.8 to +0.1c after fees.
- Verdict: the index is table stakes for the final minute, not an edge; others already trade on it, faster.

## Where the maker edge is (2026-10-26 overnight)

`maker_grid.py` replays every naive maker rule (time slice x price band) on the full 15-minute trade tape (`tape.py 62 15`,
Aug 25 - Oct 25, ETH/SOL/XRP/DOGE): rest a bid AT the best bid of the side in the band, re-post as it moves, pull when it
leaves the band; harsh fills (a trade through our price fills us in full). `maker_bets.py` + `sizing.py` turn one rule into
per-bet results and compound them at different bet sizes with a per-market cap.

- The edge peaks with **6-10 minutes left** on 85-99c favorites (+1.1 to +1.8c per $1, positive in both months) and fades
  toward the close (2-5 minutes: +0.2 to +0.7c). Coco's slot (94-99c, 2-5 min) is the weakest: +0.10c, 6 of 10 weeks up.
- **Sadie's slot (94-99c, 5-10 min): +1.08c, t 3.9, 9 of 10 weeks up, every coin positive.** 6-10 min: +1.20c, t 4.0.
- 99c+ bids: +0.20c, t 2.9, ~0.3% lost: a thin second edge that runs alongside.
- Sizing ($10 cap): 6-10 min + 99c rule at 1% bets: $100 -> $314 in 62 days (worst day -5%); at 3%: $1,034 (worst -17%).
- Joining the best bid beats a tick above it; following the price earns the same per $1 as the 2-minute cron but fills
  ~1.8x as often; $10 bids fill fully 92-94% of the time.
- Replay vs live paper (Training Sadie on the real tape, Oct 23-25): same direction, replay ~1c per $1 too high. Expect
  real Sadie at roughly +0.3 to +1c per $1.
- Ruled out: two-sided market making (-0.3 to -6c), selling before the close (costs 0.1-1.9c), hour-of-day filters (noise).

## What the open-source Kalshi bots do (2026-10-27)

Read: ryanfrigo/kalshi-ai-trading-bot (its own live verdict: "NO MEASURED EDGE", n=55), hamad-khawaja, reedjacobp,
seanrobenalt ("it lost me $100"), DeweyMarco, kapelame, CloddsBot (nothing Kalshi-crypto specific). None publishes a
verified profit. Their ideas, against what we already tested: late favorites taken at the ask, the final 90 s with
momentum, two-sided market making, buy-both-sides arbitrage (the book never crosses) - all ruled out above. New to us:
"check the coin before betting" (certainty scalp, resolution rider, momentum/previous-result confirmation).

`sadie_filters.py` tests those as filters on cron Sadie: per bet, the coin's odds of her side winning (spot vs strike,
drift to the final minute, then the average), 30 s / 120 s momentum, the previous market's result, the other coins.
- Odds below her bid = the bids informed sellers hit. Skipping them (odds_margin 0): index + 10-min 1-second vol
  +1.15c -> +1.61c (halves +1.63/+1.59); an exchange's spot + 4 h vol (what the bot has), 4 coins: +1.23c -> +2.06c
  (+2.28/+1.82), about half the bets, the same dollars at $10 (more after a 1c live haircut). 15 one-minute candles
  for vol: no help. Bucket-by-bucket it's noisy; the aggregate held in 4 of 5 ways of measuring.
- Previous market settled her way: +1.63c vs +0.69c, both halves, but it halves the bets and total dollars. Not used.
- Momentum and the other coins: no usable pattern (the coins nearly always agree).
Live from 2026-10-27 ~22:40 UTC in both books (`heavy_maker: {odds_margin: 0.0}`).

## Bitcoin Bea's trade-tape test (2026-11-01)

`btc_check.py` replays Sadie's cron rules with the coin check on bitcoin's real trade tape (data/tape_btc, 6,352
markets, Aug 24 - Oct 31) next to the other four coins (data/tape62), $10 a market, harsh fills:

| With the coin check | Bets | Lost | Per $1 | Halves | Weeks up |
|---|---|---|---|---|---|
| BTC | 846 | 3.2% | +2.11c | +3.33 / +0.89 | 8 of 11 |
| ETH | 784 | 3.3% | +1.37c | +2.14 / +0.60 | 8 of 10 |
| SOL | 820 | 2.7% | +1.92c | +1.47 / +2.37 | 8 of 10 |
| XRP | 800 | 2.5% | +2.61c | +3.56 / +1.65 | 8 of 10 |
| DOGE | 779 | 2.4% | +2.33c | +2.01 / +2.63 | 9 of 10 |

Bitcoin passes the bar set before the test (clearly above zero, most weeks up, both halves up) and sits in the middle
of the pack, so dropping it on 10-25 was about the old strategies, not Sadie's. Caveats: its second half is thin
(+0.89c, like ETH's), one bad week (Oct 1: -4.3c), and its 97-99c bets lose (-0.45c) while 92-97c carry it.

## How big to bet, and bigger bets when surer? (2026-11-02)

`sizing.py` on the 4,029 bets btc_check.py replayed (5 coins, coin check on, `OUT=data/sadie_rows.json`):
- **Sureness doesn't pick winners.** Per $1 is about +2c whether the coin check's odds beat our price by 0-1c
  (+1.95c) or 5c+ (+2.07c); bets it calls 99.9%+ still lose 1.9% of the time. So scaling bets by sureness, or Kelly
  from the coin odds, ends about where flat betting does (3% flat $641 from $80; sureness-scaled $667-673).
- **Kelly** from the replay says ~67% of the pool a bet, which only means the edge is very steady; it ignores that
  the 2c is an estimate, that several coins' bets share a window, and that fills run out. Pool replays from $80
  (bets never bigger than the replay filled): 1% $170, 2% $353, 3% $641 (worst drop 13%), 5% $823 (22%), 8% $891.
  Past ~3% the gain flattens because a market only fills ~$10 at our price: the limit is liquidity, not nerve.

## Four thinner coins (2026-11-02)

Same test as Bitcoin Bea's (`btc_check.py`), tape in data/tape_new (Sep 3 - Nov 2), coin
check on Binance 1-second prices (HYPE's only from Sep 24):

| With the coin check | Bets | Lost | Per $1 | Halves | Weeks up |
|---|---|---|---|---|---|
| NEAR | 680 | 2.1% | **+2.29c** | +1.85 / +2.72 | 7 of 9 |
| BNB | 750 | 2.7% | +1.56c | +1.73 / +1.40 | 7 of 9 |
| HYPE | 481 | 4.2% | +0.50c | +1.21 / -0.19 | 3 of 6 |
| ZEC | 617 | 2.6% | +1.67c | +2.38 / +0.97 | 6 of 9 |

NEAR is as good as the main five; BNB and ZEC close behind; all three pass the bar (above zero, both halves, most
weeks up). ZEC's first 3 weeks alone read +0.37c: a few hundred bets can't tell +0.5c from +2c (one lost bet is
~-100c against ~+4c wins, so the error on 500 bets is about +-1c). HYPE fails on its own data (+0.36c +- 0.96c,
second half down, loses 4.2% vs ~2.5% elsewhere), but that is still within luck of the others; it stays on Training.
The coin check matters even more here (BNB +0.53c -> +1.56c, NEAR +0.97c -> +2.29c, ZEC +0.64c -> +1.67c).

## Hourly bitcoin ladders (2026-11-03, `hourly_check.py`)

Kalshi's hourly "bitcoin above $X at 3 pm" markets (KXBTCD, ~30 traded strikes an hour, no maker fee) on Sadie's
rules, on the final 30 minutes of every strike within 1.2% of the coin (`tape.py` with NEAR=0.012), Oct 4 - Nov 3,
harsh fills, $10 a market. Every strike: **+0.5 to +0.7c per $1** at every distance from the close (2-29 min), both
halves up everywhere, t 2-3, 20-24 of 31 days up. The coin check doesn't help here (it does on the 15-minute coins).
One bet an hour at 5-9 min with the check: +1.55c (t 3.9) on 695 bets, but its neighbours are +0.2 to +1.0c.
Real but about half the 15-minute coins' edge: 🐿️ Hourly Hazel (`hourly_btc`) bets it on Training from 11-03,
5-21 min left, 92-99.5c, every strike (the pool's window cap, per hour, limits how many).

## Hourly ladders for the other coins (2026-11-12): no Hazel for them

Hazel's test (`hourly_check.py`, every strike within 1% of the coin, harsh fills, $10 a market) on the other coins'
hourly "above $X" ladders, Oct 22 - Nov 12 (`tape.py 21 22 data/tape_hourly2 KXETHD KXSOLD ...`, NEAR=0.01).
Every strike, no coin check:

| Coin | Bets, 5-21 min left | c per $1 by window (5-9 / 9-15 / 15-21 min) | Verdict |
|---|---|---|---|
| ETH | 2,191 | -0.70 / -0.05 / -1.31 | no edge, plenty of data |
| SOL | 886 | -2.38 / -2.82 / -2.69 | loses, both halves |
| XRP | 187 | -4.53 / -2.97 / -3.92 | loses |
| HYPE | 51 | -12.5 / -10.0 / +5.7 | loses (too thin anyway) |
| DOGE | 59 | -3.54 / +3.05 / +3.00 | too few bets to tell (1 loss) |
| BNB | 155 | -3.75 / +0.54 / -5.19 | too few bets to tell |
| NEAR, ZEC | 0 | no settled traded markets in 3 weeks | nothing to bet |

The coin check doesn't rescue ETH or SOL (it makes both worse at 5-9 min). For scale, bitcoin's own ladder on the same
test over the overlap (Oct 22 - Nov 3): +0.68 / +0.57 / +0.93c on ~1,700-2,000 bets a window, so the test isn't
just harsh. Hazel's edge is bitcoin's: its ladder is the busy one, with sellers who dip below fair often enough to
pay for the occasional loss; the others are either fairly priced (ETH) or move too much for 92-99c bids (SOL, XRP).
Recheck DOGE and BNB in a month or two if their ladders get busier.

(Also fixed here: the Binance loaders sized their price arrays by the number of files, so a missing day cut off the
newest prices; earlier results only lost their last few days, no prices shifted.)

## Hazel's wider window, bitcoin ranges, the S&P hourly ladder (2026-11-12)

`tape.py` into data/tape_hourly3, then `hourly_check.py` (harsh fills, queue 0.3, $10 a market):

- **Bitcoin hourly ladder (KXBTCD), Nov 3-12**, every distance up: 2-5 min +0.84c, 5-9 +0.95, 9-15 +1.37,
  15-21 +1.38, 21-29 +1.20c per $1, and every price band up in both periods (Oct 4 - Nov 3 too). Hazel now bids
  from 29 to 2 minutes before the hour (was 21 to 5), both books.
- **Bitcoin hourly ranges (KXBTC, "between $X and $Y"), Oct 23 - Nov 12:** 2-5 min -3.21c, 5-9 -5.05, 9-15 -1.56,
  15-21 -2.65, 21-29 -0.27. A range can be lost from either side: no.
- **S&P 500 hourly ladder (KXINXU), Oct 23 - Nov 12:** every distance loses (2-5 min -5.1c, 5-9 -1.5, 9-15 -3.3,
  15-21 -15.0, 21-29 -18.4). The index moves on news during market hours and its sellers aren't careless: no.
- **Nasdaq-100 hourly ladder (KXNASDAQ100U), same dates:** worse, -11c to -45c per $1 at every distance, with
  13-51% of 92c+ favorites losing (cause not checked; possibly thin trading, where a bid fills mostly just before the price falls). No.

## Commodities: gold, oil, silver (2026-11-09)

Kalshi's 15-minute commodity markets on Sadie's rules, two months of their trades (Sep 10 - Nov 9; `tape.py 60 15
data/tape_cmdty KXGOLD15M KXWTI15M KXSILVER15M`, then `cmdty_check.py`). 5-9 minutes left, no price check:

| Market | Bets | c per $1 | halves | t | 97c+ favorites |
|---|---|---|---|---|---|
| Gold | 860 | +1.05 | +1.82 / +0.27 | 1.1 | +0.90 (-0.38 / +2.17) |
| Oil (WTI) | 891 | +0.89 | +1.96 / -0.18 | 2.9 | +1.73 (+1.15 / +2.31) |
| Silver | 834 | +0.68 | -0.29 / +1.64 | 1.4 | +1.02 (+0.92 / +1.12) |

All positive, none as steady as the coins were before their coin check (+1.23c, t 3.8, both halves). The 97c+ band is
the steadiest, so Goldie, Clyde and Sterling went on Training with `min_price: 0.97`.

**A gold check with PAXG (gold_check.py) made it worse:** the bids it kept made +0.19c per $1, the ones it skipped
+1.99c. Binance's gold token is probably too far behind Kalshi's gold reference to say anything. No check for gold;
oil and silver have no free second-by-second price at all.

## The capacity hunt: more markets to grow into (2026-11-17)

The prediction model (desk/forecast.py) says the office stops growing around $470 a day because each market runs out
of sellers at our price, so the next growth comes from more markets, not better rules. Replays with
`research/forecast/library.py` (CHECK=0 LO=..., no free price feed for these; harsh fills, queue 0.3, 5-9 min left,
any bid size):

| Market | Trades per window vs SOL | 97c+: c per $1 (bets) | halves | fresh Nov 7-17 | at $320 bids |
|---|---|---|---|---|---|
| Natural gas | 0.27x | +2.55 (139) | +2.59 / +2.52 | (in the same tape) | +2.48 |
| Oil (WTI) | 1.1x | +1.07 (277) | +1.80 / +0.64 | +2.22 (49) | +1.31 |
| Silver | 0.75x | +1.43 (288) | +1.35 / +1.45 | -1.50 (56) | +1.32 |
| Gold | 4.7x | +0.28 (280) | +0.69 / -0.17 | +2.06 (75) | +0.42 |
| Copper | 0.15x | +0.43 (335) | +2.02 / -1.14 | | +0.50 |

At 92c+ natural gas is +1.14c (706 bets, +1.67 / +0.61). 🐉 Bertie the Dragon (`maker_natgas`, 97c+) joins Training.
Oil is the steadiest of the existing three across every period; silver's fresh 10 days are one loss. Copper: no.
Not yet tradable: Kalshi lists ADA, BCH and TON 15-minute series with no markets (recheck). Hourly ladders for the
other coins already failed (above). Currencies, rates and indexes trade 2-30% of SOL's volume: thin.
