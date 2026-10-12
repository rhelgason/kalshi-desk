# Monthly performance review: how to run one

The desk records enough to judge every employee after the fact. A review
should end with a concrete proposal for each employee (keep / retune / bench /
retire) and any new hires, with the evidence for each.

## 1. Get the report

    python -m desk review --days 30 --out data/reviews/$(date +%F).md

It covers, per employee: bets, win rate, profit, profit per $ bet, fees,
skill-or-luck (t-stat), fill reality (price paid vs. seen, depth), attempted
bets that didn't fill and why, and breakdowns by price paid, minutes left,
side, time of day and bitcoin's 15-minute move. Also the settings in force
(from each bet's context), HR changes and autotune runs.

## 2. Where the raw data lives (Postgres, DATABASE_URL)

| table | what | key columns |
|---|---|---|
| fills | every paper bet | `context` JSON: prices, sizes, secs_left, strike, spot, vols, momentum, settings, level |
| settlements | payouts | strategy, ticker, yes_value, pnl |
| decisions | every attempted bet | outcome ("filled", "no liquidity at limit price", "insufficient cash ..."), context |
| market_tape | each bot run's quote per watched market | secs_left, yes_bid/ask, sizes, strike, spot |
| market_history | settled markets + 1-minute candles (background job) | series, close_ts, data |
| price_history | 1-minute BTC prices, DVOL | symbol, day |
| events | HR, admin, tune, season, `roster` snapshots (every 3h: status, level, settings) | kind, strategy, detail |
| tuning_runs | autotune results | strategy, summary |
| backtests | nightly backtests of the current lineup | summary |

All bets since Season 3 (2026-10-12) are 15-minute bitcoin markets (KXBTC15M).

## 3. Questions to answer

- Did anyone beat both yardsticks (Dart Monkey Dan, Long Shot Lenny) by a margin
  that isn't luck (t > 2, 100+ settled bets)?
- Is an edge concentrated in one slice (price band, minutes left, hour)? If so,
  narrow the employee to it and backtest the narrowed version (train/test).
- Are fills realistic? Large slippage or thin depth means real money would do worse.
- Do backtests still agree with live results? (`backtests` table / `python -m desk backtest`.)
- New employee ideas: study market_tape + market_history for patterns, then
  `python -m desk tune <key> --set ...` with the 2/3 train, 1/3 test split. Only
  hire what holds up in BOTH periods.

## 4. Season 3 starting lineup and why (2026-10-12)

Studied ~4 months of KXBTC15M. Kalshi's prices are close to fair; a textbook
spot-vs-strike model lost at every threshold; momentum-fading lost. Small,
repeatable leans: favorites (75-95c) with ~10 minutes left, and strong 15-minute
moves early in a window. Lineup: The Sniper, Nickel Nick, Buzzkill Bill,
Breakout Betty (new, probation), Early Bird Edie (new, probation), plus
yardsticks Long Shot Lenny and Dart Monkey Dan.
