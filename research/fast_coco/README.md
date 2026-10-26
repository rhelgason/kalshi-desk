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
