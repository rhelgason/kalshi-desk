# Strategy scan, 2026-10-23

Question: is there any rule-based way to make money on Kalshi's 15-minute coin
markets, and which setup should run the Training pool? (Real money was paused
the same day: the nickels went 26/8 live, below their ~87% break-even.)

## Data

92 days of 15-minute markets (Jul 25 - Oct 23) for BTC, ETH, SOL, XRP, DOGE, BNB
and HYPE, 1-minute best bid/ask candles, plus Bitstamp 1-minute prices for
BTC/ETH/SOL; BTC back to Dec 2025. XRP/DOGE/BNB/HYPE start Aug 16.
`build.py` turns it into one row per market-minute (rows.pkl).

## Method (`scan.py`, `analyze.py`)

~4,750 strategy x coin combinations in 9 families: favorites and long shots by
price band and time left, Kalshi momentum/reversion, a spot-vs-strike pricing
model, spot momentum/reversion, bitcoin leading the other coins, early
breakouts, volume spikes, and big-jump fades. One bet per market, pay the ask
plus the 7% x P x (1-P) fee. Picked on TRAIN (Jul 25 - Sep 22), checked on
TEST (Sep 23 - Oct 22). Luck judged by the t-statistic of daily totals.
Every scan was also run with a 1-minute fill delay.

## Findings

- The markets are well priced. A 90-95c favorite wins ~92%, an 85-90c one
  ~86%: you get what you pay for, and the fee makes it slightly negative.
- Only 0.8% of rules cleared t > 2 in TRAIN and 0.4% in TEST, fewer than pure
  chance (~2%). Train-winners went on to make a median +0.3c per $1 in TEST.
- The "best" rules in TEST alone mostly lost in TRAIN: luck.
- The one family that held up: heavy favorites (92-99c) in the middle of the
  window. Checked like the bot trades (every 2 minutes, filled only if the
  next minute's price is still at or under the limit), on BTC/ETH/SOL/XRP/DOGE:
  TRAIN +0.66c per $1 (t 2.2), TEST +0.67c (t 1.6), and BTC Dec-Jul, never
  used to pick it: +1.07c over 1,943 bets (t 1.65, 5 of 8 months up).
  Small, consistent, but each test alone is short of proof.
- BNB and HYPE trade a few hundred to a thousand contracts a day: too thin for
  $10 bets, and they lost in both periods. Left out.
- Training's own live results over the same 30 days agree: Lucky the Pigeon
  (random long shots, the control group) was the top earner. That's luck.

## What changed

Steady Stella (`heavy_favorite`) became the Training pool's only member on
five coins (window cap 5%), and `python -m desk seed-season` replayed her over
the last 30 days through the bot's own code, with half a cent per contract
extra on SOL/XRP/DOGE for thin books: $1,000 -> $1,106 (2,435 bets, 93% won,
$135 in fees, worst day -$107, deepest dip 18%). The same replay on the 30
days before (the period she was picked on): +35%.
