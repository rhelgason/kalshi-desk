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

## Where we left off (2026-10-26)

- **Season 7, both books: Steady Sadie (`heavy_maker`) alone.** Stella, Coco and Sid are benched (`enabled: false`;
  Sadie still reads Stella's settings, hr.TWINS). Real money RESUMED 2026-10-26 ~09:35 UTC from $74.44 at **1% bets**
  (real.settings pool.bet_pct 0.01, window_cap 0.04). **10-30: raised to 2% (window_cap 0.08)** after +3.3c per $1 on 95 real bets
  since the coin check; plan: 3% at ~300 real bets if still above zero.
  Training season 7 is seeded from Dec 10, 2025 ($1,000 -> $6,109 in the 1-minute replay, $10 cap) and live since.
  Season 7 on the real book was started on the server (this Mac has no Kalshi key): see deploy/SERVER.md.
- **The finding (research/fast_coco/README.md):** resting bids on 92-99c favorites with 5-9 minutes left, replayed on
  Kalshi's real trade tape (Aug 25 - Oct 25, ETH/SOL/XRP/DOGE) in the bot's 2-minute looks: +1.23c per $1, t 3.8,
  9 of 10 weeks and every coin up. Rechecked 10-26: +0.94c with no share of the queue at our price, +1.24c with a
  3-second delay. Live paper agreed (Oct 25-26: Sadie +2.0c per $1 on 136 bets, Coco -3.8c on 184). Coco's 2-5
  minutes is the weakest stretch (real season 6: -$13 in a day). Ruled out: the final minute even with the official
  index, two-sided market making, selling early, hour filters, Kalshi maker rewards (not on crypto).
- **10-27: Sadie checks the coin before bidding** (`odds_margin: 0.0`, both books): she skips a bid when spot vs strike
  and 4 h vol give her side worse odds than her bid. Backtest +1.23c -> +2.06c per $1, half the bets (README section
  "What the open-source Kalshi bots do"). The feed now prices all 5 coins. Expect about half as many bets as before.
- **10-28: two Training-only hires outside the coins** (research/other_markets/README.md; the real book has them
  `enabled: false` and `other_series: []`): 🌤️ Weather Wendy (`weather_maker`, daily-high favorites 92-99.5c, midnight
  to 11 am city time, replayed +3.8c per $1) and 🏁 Final Whistle Fiona (`sports_closer`, game winners at 97-99.5c from
  3 h before Kalshi's expected end to 2 h after, +1.2-1.7c). Their markets come from desk.yaml `other_series` (one
  events call per series each run); `Strategy.scope` keeps the coin staff off those markets and them off the coins.
- **10-31: Sadie's bets split into five coin specialists, mid-season on both books** (no new season, so the real
  book's season-7 chart carries on): 🐝 Bitcoin Bea `maker_btc`, 🦢 Ether Esther `maker_eth`, ☀️ Solar Sally `maker_sol`,
  🌊 Ripple Rita `maker_xrp`, 🐕 Dogecoin Dot `maker_doge` (desk/strategies/bitcoin.py `CoinSpecialist`). They take
  Sadie's settings through hr.TWINS (specialist -> Sadie -> Stella), so tune Sadie, not them. **Later on 10-31 Sadie
  retired** (`enabled: false`, both books): deploy/dissolve_sadie_2026-10-31.py first moved her season-7 bets to the
  specialist for each coin, split her starting money evenly between them and rebuilt their value history, then the
  code went out (database first, or her money would have dropped from the books). New hires join a pool with $0. Bea is Training only (`enabled: false` on the real book) until bitcoin's
  trade-tape test (data/tape_btc) says otherwise. Wendy's two-year weather tape: research/other_markets/wx_history.py.
- **Fast Sadie trial** on the server (desk/fast.py, from 2026-10-26 07:12 UTC): always-on bid vs a 2-minute cron twin,
  pretend money from $87.63 each. `python -m desk fast-report`. So far it fills more, not better per $1.

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
