# The long Stella backtest, 2026-10-24

Question: Steady Stella (92-99c favorites, 5-9 minutes left) was picked on Oct 23 from 4,700
rules over 92 days. Does she hold up over all the history Kalshi has, does a patient twin do
better, how big should the bets be, and how much real money should go in?

## Data

Every settled 15-minute market Kalshi has, with 1-minute best bid/ask candles:
BTC and ETH from 2025-12-10, SOL from 2026-01-08, all to 2026-10-24 (86,000 markets).
The live window comes from `fetch.py`, older markets from Kalshi's archive (`fetch_archive.py`,
one request per market: about 2 hours). XRP and DOGE only for the live window (Aug 18 on).

## Method

`sim.py` replays a rule over every market the way the hosted bot trades: a look every 2 minutes,
one bet per market, held to settlement.

- **Stella, next-minute fill**: the order fills at the next minute's ask if it's still at or under
  what she saw (what `desk seed-season` does). **Instant fill**: at the ask she saw. The bot sends
  its order seconds after looking, so the truth is between the two; instant is closer.
- **The twin (Steady Sadie)**: a bid one tick over the best bid (0.1c at these prices), left ~110
  seconds; filled if the best bid later drops below it (sellers went through her). Makers pay no
  fee on any of the five coin series (`fee_type: quadratic`).
- **`validate_tape.py`** checks that fill rule against Kalshi's real trade tape for 250 random
  markets: of 244 the candles call filled, sellers really traded through her price in 228 (93%),
  and the tape-confirmed fills made **+1.19c per $1 instead of +1.53c**. All twin numbers below
  that say "tape-adjusted" price every bet 0.35% higher to match.
- **Sizing** (`run_pool`): one compounding pool with the bot's guardrails (10% daily stop, half-size
  bets 25% below the high), 0.01-contract steps, Kalshi's taker fee **rounded up to the cent on
  every order**, never more than a quarter of what traded in the fill minute.

## Findings (full tables in REPORT.md and RECENT.md)

| BTC + ETH + SOL, Dec-Oct | per $1 bet | t | months up | bets a day |
|---|---|---|---|---|
| Stella, next-minute fill | +0.60c | 2.0 | 9/11 | 40 |
| Stella, instant fill | +0.58c | 3.8 | 9/11 | 90 |
| **Twin (Sadie)** | **+1.53c** (~+1.2c on the tape) | **9.7** | **11/11** | 89 |

- **The twin wins on every coin**: BTC +1.40c (t 6.5), ETH +1.54c (t 6.8), SOL +1.66c (t 7.3).
  She avoids the fee (0.33c at 95c) and the per-order rounding, buys a tenth of a cent under the
  bid instead of at the ask, and her bids fill often enough that she bets as much as instant Stella.
- **The months before the Oct 23 scan, which it never saw**: the twin made +1.85c per $1 (t 9.9),
  8 of 8 months up. Stella the taker: +0.65c (t 3.6, instant fills).
- **The edge is shrinking.** Twin per $1 by month: Jan 3.0c, Mar 2.3c, Apr 2.2c, Jun 1.9c, Jul 1.0c,
  Aug 1.0c, Sep 1.6c, Oct 0.4c (24 days). The last 60 days, tape-adjusted: +0.75c.
- **Stella is a bad fit for a $100 pool**: at 1% her $1 bets pay a full cent of fee each (the
  rounding), about her whole edge. Over the 10 months at $100 and 1%, the instant-fill replay
  loses half the pool, and the friendlier next-minute one makes +26% where exact fees would have
  made +64%. Sadie has no fee to round.
- **The rule grid** (280 nearby rules, picked on Dec-May, judged on May-Oct): the first half's
  15 best were all resting-bid versions of this family, and every one made money in the second
  half (+0.56c to +1.34c per $1, t 4 to 6, all 11 months up). Paying the ask never came close.
  68 of 280 rules cleared t > 2 in both halves (they overlap, so that's not 68 separate proofs,
  but luck alone would give almost none).
- **XRP and DOGE** (Aug 18 - Oct 24 only): twin +1.90c and +1.53c per $1 (t 4.4, 3.7). Promising,
  thinner books, too little history: Training only.

## Bet size and how much real money

From RECENT.md: 30-day outcomes resampled from the last 60 days only, tape-adjusted twin.

| Pool | Bet | Chance of a losing month | Bad month (1 in 20) | Typical month | If the edge halves again: typical / bad |
|---|---|---|---|---|---|
| $100 | 1% ($1) | 9% | -5% | +24% (+$24) | +7% / -16% |
| $250 | 1% ($2.50) | 8% | -3% | +24% (+$59) | +7% / -17% |
| $500 | 1% | 7% | -3% | +23% (+$114) | +7% / -16% |
| $1,000 | 2% | 9% | -10% | +52% | +12% / -28% |

**Recommendation: $250 on Sadie alone, 1% bets (Associate), BTC/ETH/SOL. Raise it to $1,000 after a
two-week trial if the live numbers match.**

- 1% is the right size. 2% roughly doubles both the gain and the bad months; with an edge that has
  halved twice this year and real fills not yet seen, that's the wrong trade. 0.5% is fine too, just slower.
- $250 rather than $100: no fees means small bets aren't penalized any more, so $100 would also work.
  But $2.50 bets give a clearer read on fills, and a bad month at $250 costs about $8 (or about $43
  if the edge halves again). That's a cheap price for the answer.
- **The trial's pass mark**, after about two weeks (~1,000 real fills): most posted bids fill (the
  backtest says nearly all; under ~70% means the candle rule is too kind), and the live profit is at
  least +0.4c per $1. Pass: go to $1,000 at 1%. Below zero after ~1,500 fills: stop and go back to Training.
- More than about $5,000 would start to run into how many sellers come through in two minutes
  (median ~1,400 contracts on the tape, but 1 in 10 bids saw under 90).

## Going live

1. Deploy the bot (`npx vercel deploy --prod` from the repo root) so it has the new roster.
2. Top the Kalshi account up to the starting amount, then
   `python -m desk live-check --config desk.real.yaml --fund`.
3. `python -m desk new-season --config desk.real.yaml --pool 250 --level heavy_maker=Associate --why "Sadie alone, from the 10-month backtest"`
4. Resume real trading on the dashboard (the kill switch).

Until step 3, the real book keeps last season's accounts for the retired staff, so the safety check
will keep it halted. It's already paused, so nothing trades by accident.

Training picks up Sadie, Coco and Sid on its next run (they join the current pool with no money of
their own, like any new hire). Their paper bids are filled from Kalshi's real trade tape, which
checks the twin's fill rule live, for free.

## Checking the fees Kalshi actually charged

The real book has the fee Kalshi charged on every order. In Supabase's SQL editor:

```sql
select count(*) as orders, round(avg(filled)::numeric, 2) as avg_contracts,
       sum(fees) as fees_paid, round(sum(0.07 * filled * price * (1 - price))::numeric, 4) as formula
from real.orders where kind = 'taker' and filled > 0;
```

If `fees_paid` is well above `formula`, Kalshi rounds up per order, as `desk/kalshi/fees.py` assumes.

## Rerunning

```bash
python fetch.py KXBTC15M data/ && python fetch_archive.py KXBTC15M data/   # and KXETH15M, KXSOL15M
SERIES=KXBTC15M,KXETH15M,KXSOL15M python analyze.py data/ out/              # ~40 minutes
python validate_tape.py data/ out/ 250                                      # live window only
python recent.py out/bets_twin_1.csv.gz 60
python quick.py data/ KXXRP15M,KXDOGE15M
```
