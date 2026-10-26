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

- **Real money is PAUSED** (long pause, 2026-10-26) at $74.44: season 6 ran Closing Time Coco (`late_maker`) alone on
  ETH/SOL/XRP/DOGE for one day (30 bets, 6 lost, -$13.19). Resume only when the owner asks.
- **The finding (2026-10-26, research/fast_coco/README.md):** every naive maker rule replayed on Kalshi's real trade
  tape with harsh fills (`maker_grid.py`). The edge is resting bids on 94-99c favorites with **5-10 minutes left**
  (Steady Sadie's slot): +1.3c per $1 in October on all four coins, every week positive; the 5-6 minute slice was
  positive in all 9 weeks from Aug 25. Coco's 2-5 minutes was the weakest stretch. 99c+ bids are a thin but steady
  second edge (+0.3c, ~0.3% lost). Sizing: Sadie's rule + 99c rule at 3% bets, $10 cap: $100 -> $531 in 27 days,
  worst day -11.5% (sizing.py). Ruled out: the final minute even with the official index (others are faster),
  two-sided market making, selling before the close, Kalshi maker rewards (not on crypto).
- **Fast Sadie trial** on the server (desk/fast.py, deploy/SERVER.md, from 2026-10-26 07:12 UTC): a bid always at the
  favorite's best bid in Sadie's slot (follows the price, pulls on coin jumps) against a 2-minute cron twin, pretend
  money from $87.63 each. `python -m desk fast-report`. The replay says following earns the same per $1 as the cron
  but fills ~1.8x as often. The server has its own Kalshi key ("Server", /etc/kalshi-desk.key), used for reads.
- **Next for real money (owner's go):** a new real season with Sadie (`heavy_maker`) instead of Coco on the four coins.
- **Training** season 6 is the backfill from Dec 10, 2025 (seeded through Oct 24; live paper since).

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
