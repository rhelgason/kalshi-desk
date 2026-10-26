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
