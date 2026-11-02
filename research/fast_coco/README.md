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
