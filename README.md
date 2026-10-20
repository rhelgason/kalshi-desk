# Kalshi Desk

A small "trading desk" for Kalshi's 15-minute crypto markets. Every strategy is an
employee with a name, a portrait and a job title; they share one office pool, get
weekly reviews, promotions, an Employee of the Week and a bonus pot, and the ones
that don't earn their keep get benched.

Two books run side by side, every 2 minutes:

- **Live**: real money on Kalshi, a hand-picked roster, hard safety limits
  (daily stop, daily loss limit, books checked against Kalshi every run, phone
  alerts if anything pauses).
- **Training**: pretend money, the whole staff, automatic reviews and autotuning.
  New ideas prove themselves here before they touch real money.

## Where things live

| Path | What |
|---|---|
| `desk/` | The engine: employees (`desk/strategies`), the pool, HR, backtests, the real-money guard. See [desk/README.md](desk/README.md) |
| `desk.yaml`, `desk.real.yaml` | Training and Live settings |
| `web/` | The dashboard (Next.js on Vercel): Live, Training and the Office |
| `widget/`, `web/public/widget` | The iPhone home-screen widget (Scriptable) |
| `tests/desk` | The test suite |
| `research/` | One-off studies behind the employees' settings |

Hosting: Supabase Postgres (pg_cron calls the bot every 2 minutes), Vercel for the
bot (`kalshi-desk-bot`, deployed from this folder) and the dashboard (`kalshi-desk`,
deployed from `web/`). Notifications go through Pushover.

```bash
.venv/bin/python -m pytest -q          # tests
.venv/bin/python -m desk employees     # meet the staff
.venv/bin/python -m desk tune nickel_picker --days 30 --set min_price=0.85,0.88
```

## Credits

Started as a fork of [ImMike/polymarket-arbitrage](https://github.com/ImMike/polymarket-arbitrage)
(MIT; see [LICENSE](LICENSE)). `core/`, `polymarket_client/`, `kalshi_client/`,
`dashboard/` and `run_with_dashboard.py` are left over from it.
