# Hosting Kalshi Desk for free (no credit card)

```
 Supabase (free)                                   Vercel (free, two projects)
 ┌──────────────────────────────┐   every 2 min    ┌──────────────────────────────┐
 │ pg_cron ── net.http_post ────┼─────────────────▶│ kalshi-desk-bot  /api/tick    │
 │                              │                  │   runs one desk tick, then    │
 │ Postgres: ledger, status,    │◀─────────────────┼── saves state & trades back   │
 │ saved bot state, backtests   │                  └──────────────────────────────┘
 │                              │                  ┌──────────────────────────────┐
 │                              │◀─────────────────┼── kalshi-desk (web/) reads it │
 └──────────────────────────────┘                  └──────────────────────────────┘
```

Nothing runs on your computer. Neither free plan has a card on file, so
neither can bill you; going over a limit pauses things instead.

## Pieces

| Piece | Where | Notes |
|---|---|---|
| Ledger + state | Supabase Postgres | `DATABASE_URL` in `.env` (session pooler, port 5432) for local commands |
| Bot | Vercel project `kalshi-desk-bot` (repo root, `api/tick.py` → `desk/cloud_app.py`) | env: `DATABASE_URL` (transaction pooler, port 6543), `TICK_SECRET` |
| Scheduler | Supabase `cron.job` `kalshi-desk-tick`, every 2 min | secret lives in Supabase Vault as `kalshi_tick_secret` |
| Cleanup | Supabase `cron.job` `kalshi-desk-cleanup`, daily | trims `cron.job_run_details` |
| Dashboard | Vercel project `kalshi-desk` (`web/`) | env: `DATABASE_URL` (port 6543), optional `DASHBOARD_PASSWORD` |

## Free-plan budgets

- **Vercel Active CPU: 4 hours/month**, shared by both projects. A warm bot run
  uses ~0.15 s of CPU, a cold start ~1.4 s, heavier runs (broad scan every
  10 min) more. `desk/cloud.py` tracks CPU used this month and skips runs if
  the month is on pace to pass 3 hours, so the dashboard never gets paused.
- **Supabase: 500 MB database, 5 GB egress/month.** The bot keeps its state in
  one small row and computes accuracy inside Postgres.

## Common tasks

```bash
# Deploy code changes to the bot (from the repo root) or the dashboard (from web/)
npx vercel deploy --prod

# Pause / resume the bot (run in Supabase's SQL editor)
select cron.alter_job((select jobid from cron.job where jobname = 'kalshi-desk-tick'), active := false);
select cron.alter_job((select jobid from cron.job where jobname = 'kalshi-desk-tick'), active := true);

# Did recent runs succeed?
select status_code, left(content, 200), created from net._http_response order by created desc limit 10;
```

Local commands (`python -m desk report`, `accuracy`, `backtest`) read the same
Supabase database through `.env`. Don't also run `python -m desk paper` locally
while the cloud bot is active, or two bots will trade into one ledger.

## Alternative: a VM

`setup.sh` + `kalshi-desk.service` still work on any Ubuntu server (e.g. a
$4-5/month VPS) if you ever want 15-second ticks without free-plan limits.
Pause the cloud job first.
