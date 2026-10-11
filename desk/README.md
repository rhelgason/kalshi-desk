# The Desk

A Kalshi-first trading engine where every strategy is an "employee" with its
own paper bankroll. They all watch the same live markets, place pretend bets
against the real orderbook (with real fees), and get paid when Kalshi settles
the market. The scoreboard shows who's actually good.

```bash
source .venv/bin/activate
python -m desk employees     # meet the staff
python -m desk scan          # one look at the market: what would each employee do?
python -m desk paper         # run the paper-trading loop (Ctrl+C to stop; resumes later)
python -m desk paper --record data/rec.jsonl.gz   # also save snapshots for backtests
python -m desk report        # scoreboard from the saved ledger
pytest tests/desk            # offline test suite
```

## The staff

| | Employee | Strategy | Can it lose? |
|---|---|---|---|
| 🧮 | Risk-Free Rick | Buys combos of strike contracts that pay $1 no matter what, for less than $1 | Only through execution or rule-reading mistakes |
| 🧩 | Sudoku Sue | Buys NO on every outcome of a "pick one" event when they cost less than the guaranteed payout | Same as Rick |
| 🎓 | The Professor | Prices BTC/ETH contracts with a volatility model and buys what looks cheap | Yes. Wins only if the model beats the market |
| 📐 | Vega Vinny | Reads volatility from Kalshi's own prices, bets on strikes out of line with their neighbors | Yes |
| 🎯 | The Sniper | Final 10 minutes only: near-certain outcomes still trading a few cents under $1 | Rarely, but big when it does |
| 🏄 | Momentum Mo | Pricing model that assumes the last 15 minutes' trend continues | Yes |
| 🪀 | Rubber Band Randy | Pricing model that assumes the last 5 minutes' move reverses | Yes (Mo and Randy can't both be right) |
| 🧊 | Buzzkill Bill | Bets against long shots (the favorite-longshot bias) | Yes. Many small wins, occasional big loss |
| 🎰 | Long Shot Lenny | Buys the long shots Bill bets against | Yes. Mostly small losses, occasional jackpot |
| 🪙 | Nickel Nick | Buys 92-97c near-sure things settling within 12 hours | Yes. Steady, until a surprise |
| 🐋 | Whale Watcher Walt | Follows unusually large trades | Yes |
| 🐒 | Dart Monkey Dan | Random bets | Yes. He's the benchmark: beat Dan or you're not skilled |

## Running itself: HR, autotuning, and the manager's office

The desk is meant to be hands-off. Three loops keep improving it:

- **Performance reviews** (inside the bot, every `review_days`): crown the
  Employee of the Week/Month with a bonus from the desk reserve, promote
  employees who beat the promotion threshold to bigger bet sizes (Intern 0.5x
  → Associate 1x → Senior 1.5x → VP 2x → Partner 3x), demote losers, and
  suspend repeat offenders. Rules live in the database and are editable on the
  site's **Handbook** page.
- **Autotuning** (GitHub Actions, `.github/workflows/jobs.yml`, every 3h):
  syncs settled markets into a permanent history store, backfills Kalshi's
  archive, and once a day retunes each eligible employee on the last
  `lookback_days` of history. A new setting is applied only if it made money
  in the unseen test period and beats the current setting there.
- **The manager** (you): log in on the site to suspend, fire, rehire, promote,
  give bonuses, edit any employee's settings, toggle autotune, change the desk
  rules, request a retune, or start a new season. Everything is logged in the
  office news.

Website changes are stored in the `employees` and `settings` tables and take
effect on the bot's next run (about 2 minutes). desk.yaml provides defaults;
website overrides win.

## How it fits together

```
desk/kalshi/      API client (auth, rate limits, retries), models, fee math
desk/feeds/       BTC/ETH spot (Kraken + Deribit) and volatility
desk/strategies/  the employees; each turns a Snapshot into TradeIntents
desk/paper/       paper accounts, broker (taker fills vs. real orderbooks, maker fills vs. the trade tape),
                  ledger (SQLite or Postgres), scoreboard, accuracy
desk/hr.py        roster, levels, performance reviews, awards
desk/autotune.py  search spaces + validated retuning
desk/jobs.py      background jobs (history sync, archive backfill, autotune, nightly backtest)
desk/backtest/    replay engine, tuning with train/test split, permanent history store
desk/cloud.py     one tick per serverless invocation (Vercel), state saved in Postgres
desk/runner.py    the loop: HR sync -> discover -> snapshot -> strategies -> fill -> settle -> review
```

Adding an employee: subclass `Strategy` in `desk/strategies/`, give it a
`key` and `persona`, implement `evaluate(snapshot, account)`, and register it
in `desk/strategies/__init__.py`.

## Real money

Nothing here places real orders. `KalshiClient` can, but only when you pass
`allow_trading=True` and have an API key in `.env`:

```
KALSHI_API_KEY_ID=...
KALSHI_PRIVATE_KEY_PATH=~/.kalshi/key.pem
```

`python -m desk whoami` checks the key with read-only calls. Try
`env: demo` (Kalshi's sandbox, fake money) before production.
