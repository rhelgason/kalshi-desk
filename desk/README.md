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

Since 2026-10-24 the desk trades only the heavy-favorite family on 15-minute coin markets:
the one kind of rule a 10-month backtest found a real edge in (research/stella_backtest).

| | Employee | Strategy | Books |
|---|---|---|---|
| 🐌 | Steady Sadie | 92-99c favorites, 5-9 minutes left, a resting bid a tick over the best bid (no fee) | Real money (BTC/ETH/SOL) and Training |
| 🐜 | Steady Stella | Sadie's picks, paying the ask: the yardstick that shows what the patience is worth | Training |
| 🦉 | Closing Time Coco | 94-99c favorites, 2-5 minutes left, resting bids | Training |
| 🥈 | Silver Medal Sid | 85-92c favorites, 5-13 minutes left, resting bids (probation) | Training |
| 🐦 | Lucky the Pigeon | Buys long shots | Training (control group) |
| 🐒 | Dart Monkey Dan | Random bets | Training (control group): beat Dan or you're not skilled |

Retired, code kept for old seasons: Risk-Free Rick, Sudoku Sue, the Professor, Vega Vinny,
Momentum Mo, Rubber Band Randy, Whale Watcher Walt, Front-Runner Fran, Spread Sam, and on
2026-10-24 the Sniper, Nickel Nick, the Wet Blanket, Wipeout, Early Bird Edie and the
twins Nora, Ellie and Bonnie.

## Running itself: HR, autotuning, and the manager's office

The desk is meant to be hands-off. Three loops keep improving it:

- **Performance reviews** (inside the bot, every `review_days`): crown the
  Employee of the Week/Month (no cash bonus: the office pool is one pot), promote
  employees who beat the promotion threshold, with at least 30 bets of evidence, to bigger bet sizes (Intern 0.5x
  → Associate 1x → Senior 1.5x → VP 2x → Partner 2x), demote losers, and
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
desk/journal.py   one summary per run (the `runs` table), since the host's logs last under an hour
```

## Checking on the bot

`python -m desk log --hours 6` reads the run journal: every run's time, the
pool, and per employee how many ideas they had, bets and bids they placed,
maker fills, payouts, and why ideas didn't become bets ("window cap full",
"no liquidity at limit price", ...), plus any warnings and errors. Add
`--all` for each run in detail, or `--employee nickel_maker` for one person.
Every attempted bet, posted bid and how each bid ended (filled, expired,
pulled by the daily stop) is also in the `decisions` table.

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
