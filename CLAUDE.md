# Kalshi Desk: notes for Claude

A Kalshi trading bot whose strategies are "employees" sharing one office pool. Two books run side by
side on every hosted run: **Training** (pretend money, `desk.yaml`) and the **real book** (real money
on Kalshi, `desk.real.yaml`). Hosting: Supabase Postgres + pg_cron, the bot and dashboard on Vercel,
background jobs on GitHub Actions (see deploy/README.md). Local commands read the same Supabase
database through `DATABASE_URL` in `.env` (session pooler, port 5432).

Tests: `python -m pytest -q` (all offline). Web type-check: `cd web && node_modules/.bin/tsc --noEmit -p .`

## Links (nothing secret here; secrets live in `.env`, Vercel, and the server's /etc/kalshi-desk.env)

| What | Where |
|---|---|
| Dashboard (Training + real book; open, no login) | https://kalshi-desk-nu.vercel.app |
| Admin page (needs ADMIN_PASSWORD) | https://kalshi-desk-nu.vercel.app/admin |
| Hosted bot (Vercel project `kalshi-desk-bot`, ticked by pg_cron every 2 min) | https://kalshi-desk-bot.vercel.app |
| Vercel projects | https://vercel.com/helgasonryan/kalshi-desk-bot and https://vercel.com/helgasonryan/kalshi-desk |
| Supabase project `gxcyhwbytzxsxkwfoejq` (us-west-2) | https://supabase.com/dashboard/project/gxcyhwbytzxsxkwfoejq |
| Database host (session pooler, port 5432) | aws-1-us-west-2.pooler.supabase.com (user postgres.gxcyhwbytzxsxkwfoejq; password only in DATABASE_URL) |
| Always-on server (DigitalOcean NYC3, $6/mo) | 104.131.18.118, see deploy/SERVER.md |
| GitHub | https://github.com/rhelgason/kalshi-desk (private) |

Sessions without `.env` (Claude Code on the web or phone): set DATABASE_URL in the cloud environment's
settings, never in the repo. Schemas: `public` = Training, `real` = real money, `fast` = the server's trial.

## Where we left off (2026-10-25)

- **Real money is ON** (season 6, from $87.63): Closing Time Coco (`late_maker`) alone on ETH/SOL/XRP/DOGE,
  3% of the pool a bet ($10 cap), window_cap 3%, daily_stop 15% (real.settings). No bitcoin: it lost in Sep and Oct.
  Why: resting bids on 94-99c favorites in the last 5 minutes made +0.46c per $1 from Aug 18 on (t ~5.7).
  The edge shrinks month to month and a single week swings +/-0.5c (Oct 18-25 was about zero).
- **Training** season 6 is the backfill from Dec 10, 2025 ($1,000 -> ~$18k at $10 bets).
- **Fast Coco trial** on the server (desk/fast.py, deploy/SERVER.md): Coco's own 2-minute schedule, plus pulling a
  waiting bid when the coin jumps (61-day replay: +0.86c per $1 vs +0.55c, research/fast_coco), against a twin that
  behaves like the cron Coco, both on pretend money from $87.63. An always-on bid did far worse (+0.13c).
  `python -m desk fast-report` says month by month whether the $6 server pays for itself. After ~2 weeks, if
  Fast Coco wins, move the real money to the server (steps at the end of deploy/SERVER.md; the owner copies the
  Kalshi key over themselves).
- Projections given to the owner (expected value, edge halving every 3 months): without the server
  $118 / $182 / $262 / $344 at 1 / 3 / 6 / 12 months; with it $161 / $388 / $635 / $799.

## Things worth knowing

- **Sadie's edge lives in brief dips.** A resting bid fills when a seller hits it for a moment. If fills only
  counted when the price stayed below the bid at the minute's close, the edge would be -1.8c per $1, not
  +1.5c. So real fill behaviour is the main risk, and Training's paper bids are filled from Kalshi's real
  trade tape (`PaperBroker.match`): watch Sadie's Training fill rate against the backtest.
- Kalshi's taker fee is rounded up to the cent per order (desk/kalshi/fees.py): it eats small taker bets
  (1c per $1 on a $1 bet). Makers pay nothing on the coin series (`fee_type: quadratic`).
- Bets are in 0.01-contract steps; the minimum bet is $0.25.
- Don't switch a pool member off in `desk.real.yaml` mid-season: their money drops from our books, Kalshi
  still has it, and the safety check halts trading. Real-book roster changes go with a new season.
- `seed-season` refuses a live book: the real book's history is Kalshi's.
