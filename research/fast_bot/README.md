# Patient twins and the fast bot (Oct 12, 2026)

Two questions about 15-minute bitcoin markets (KXBTC15M):

1. Do our employees do better if they post a bid and wait (maker) instead of
   paying the ask (taker)?
2. Could an always-on "fast bot" that reacts to bitcoin moves in real time make
   more than the ~$5-7/month a server costs?

## Facts that shaped both answers

- KXBTC15M's fee type is plain `quadratic`: **takers pay 0.07·P·(1−P), makers
  pay nothing** (`GET /series/KXBTC15M`).
- Price ladder is `tapered_deci_cent`: 0.1¢ steps under 10¢ and over 90¢,
  1¢ steps between.
- These markets are huge: ~30,000-45,000 trades and ~2 million contracts per
  15-minute window.
- Kalshi's public trade-history endpoint allows roughly one page per second, so
  a full tape takes hours; minute candles take a few requests.

## 1. Patient twins (maker versions of Nick, Edie, Betty)

`twins_candles.py`: 55 days (5,215 markets), looks every 2 minutes like the
live bot, $10 a bet, hold to settlement. A twin's bid at (best bid + 1 tick,
never at the ask) counts as filled if the best bid later traded *below* it
within 110 seconds (sellers went through us).
`twins.py` replays the real tape (95 markets) to check that rule: real fills
were at least as frequent (95-100% vs 85-88%), so the candle rule is cautious.

| Employee | Taker, per $1 | Patient twin, per $1 |
|---|---|---|
| Early Bird Edie | +1.25¢ (1,216 bets) | +1.58¢ (1,031 bets) |
| Nickel Nick | +3.60¢ (195) | +3.83¢ (167) |
| Breakout Betty | −0.19¢ (702) | +3.17¢ (654), noisy: −3¢ then +12¢ by half |

Twins get filled ~85% of the time, win a little less often (they get filled
when the price is slipping), but pay less and no fee. The saving is biggest
for Betty, whose bets sit near 50¢ where the taker fee peaks (1.75¢).

Hired as Nickel Nora, Early Bird Ellie and Breakout Bonnie (interns).

## 2. The fast bot

Data: Kalshi trade tape (microsecond timestamps, 210 markets ≈ 2.2 days) and
Binance BTCUSDT trades (millisecond timestamps). An "event" is bitcoin moving
1+ basis points (0.01%) within half a second. Profit is per contract, after
the taker fee, at the price someone *actually paid* on our side at or after
the moment our order would land, scored against Kalshi's mid 60 seconds later.

**How fast Kalshi reprices** (mid shift in the move's direction, 1bp+ moves):
+0.6¢ after 50 ms, +3¢ after 100 ms, +4.4¢ after 250 ms, then little more.

**Chaser profit by when the order lands after the Binance print** (`subsec.py`):

| Lands after | 1bp+ (~900/day) | 2bp+ (~170/day) | 3bp+ (~45/day) |
|---|---|---|---|
| 0 ms | +2.0¢ | +3.7¢ | +6.8¢ |
| 50 ms | +1.3¢ | +2.6¢ | +4.5¢ |
| 70 ms | +0.2¢ | +0.9¢ | +1.9¢ |
| 100 ms | −0.4¢ | −0.1¢ | +0.6¢ |
| 300 ms | −0.9¢ | −0.6¢ | +0.4¢ |
| 1 s | −1.2¢ | −0.9¢ | +0.3¢ |

In dollars, taking a quarter of what traded at that price (max 100 contracts
per event), trading every 1bp+ move: about **+$23k/month at 50 ms, roughly
break-even at 70-80 ms, about −$2k/month at 100 ms** (90% ranges are ±$10k).

**How fast we could be**: Binance runs in Tokyo. Its trades reach this Mac
~71 ms after they happen (Coinbase ~60 ms); Kalshi is 15-30 ms further.
So a bot here, or on a cheap US server, lands **~90-105 ms after the move**:
just past break-even. The traders earning this money land in under ~60 ms,
which means better routes or signals than the public feeds.

With 1-second prices (`fast.py`, `chase.py`) every version loses: by the time
a 1-second bar shows a move, Kalshi has already priced it.

**Verdict**: the speed edge is real but belongs to whoever is fastest, and
it's gone 30-40 ms before we could arrive. A $5-7/month server would not buy
that speed. Expected profit at our speed: about zero to negative.

## Rerunning

Scripts expect their data next to them (not committed): `tape/` from
`fetch_tape.py DAYS tape`, `candles.json.gz` from `fetch_candles.py 55
candles.json.gz`, Binance 1s/1m klines in `binance/` and `binance1m/`, and
aggTrades CSVs in `agg/` (from data.binance.vision).
`recorder.py OUT HOURS` records the live book, tape and Coinbase ticks.

## Follow-up: could money buy the speed?

Binance is in Tokyo, so the Binance-timed table above can never be reached
from the US: light in fiber needs ~55 ms just to cross the Pacific, and real
routes take ~70 ms. The Binance-timed curve is flat until ~30 ms (≈ +$40k/month
at our sizing), which is the theoretical "most possible gain", but no US
trader gets there.

So the same study was rerun timed against **Coinbase** (US-based, AWS us-east-1;
646,000 trades, Oct 10-12). The test asked who trades first after a 3bp+
Coinbase move, at the price actually paid:

| Lands after the Coinbase print | 0 ms | 5 ms | 10 ms | 20 ms | 50 ms | 100 ms |
|---|---|---|---|---|---|---|
| Profit per contract | +1.4¢ | +1.0¢ | +0.5¢ | −0.2¢ | −0.8¢ | −1.0¢ |

Kalshi already moves +0.7¢ in the first 50 ms after a 1bp Coinbase move: the
professionals react within single-digit milliseconds. Size-weighted dollar
totals at 20 ms look positive (+$3k/month for 3bp+) but come from a few
high-volume events, with a 90% range of −$1.5k to +$7k, and one of the three
days was flat.

What landing within ~10 ms of a Coinbase print would take: servers in the same
data centre as Coinbase (us-east-1) and Kalshi (location unpublished; one
vendor's latency tests suggest Chicago, ~10-15 ms from Virginia), Kalshi's
institutional FIX connection over AWS PrivateLink (by application to
institutional@kalshi.com), and compiled, tuned code. A server in the right
region costs ~$50-150/month and lands ~15-30 ms after the print: at or past
break-even.

Caveats: 2.3 days, mostly a weekend; exchange clocks can differ by a few ms,
which matters at this scale; fills assume a quarter of what traded at that
price.
