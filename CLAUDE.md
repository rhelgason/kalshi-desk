# Kalshi Desk: notes for Claude

A Kalshi trading bot whose strategies are "employees" sharing one office pool. Two books run side by
side on every hosted run: **Training** (pretend money, `desk.yaml`) and the **real book** (real money
on Kalshi, `desk.real.yaml`). Hosting: Supabase Postgres + pg_cron, the bot and dashboard on Vercel,
background jobs on GitHub Actions (see deploy/README.md). Local commands read the same Supabase
database through `DATABASE_URL` in `.env` (session pooler, port 5432).

Tests: `python -m pytest -q` (all offline). Web type-check: `cd web && node_modules/.bin/tsc --noEmit -p .`

## Where we left off (2026-10-24)

A 10-month backtest (research/stella_backtest/README.md, REPORT.md, RECENT.md) found one real edge:
92-99c favorites on 15-minute coin markets, bought with a **resting bid** instead of paying the ask.
The roster was rebuilt around it and pushed:

- Real book: **Steady Sadie** (`heavy_maker`) alone on BTC/ETH/SOL. Next season's pool $250 at 1% bets.
- Training: Stella (`heavy_favorite`, pays the ask: the yardstick), Sadie, Closing Time Coco (`late_maker`),
  Silver Medal Sid (`runner_up_maker`, probation), plus Lucky and Dan (control group).
- Retired to ALUMNI: the Sniper, Nick, the Wet Blanket, Wipeout, Edie, Nora, Ellie, Bonnie.

The owner **has deployed the bot** to Vercel with this roster. Two jobs remain, below. Do them in order,
and ask the owner before anything that moves money or writes a season.

### 1. Start the real-money season (not done yet)

The real book is halted (paused) and still holds last season's accounts for the retired staff, so its
safety check keeps it halted until a new season starts. Nothing trades until step 1d.

a. Owner tops up the Kalshi account so the balance is **$250** (it was about $87 after the first season).
b. `python -m desk live-check --config desk.real.yaml --fund`
   Needs `KALSHI_API_KEY_ID` and `KALSHI_PRIVATE_KEY_PATH` (or `KALSHI_PRIVATE_KEY`) in `.env`. It prints
   the balance and moves the cash to the crypto shard. Optional: add `--order` to place and cancel one tiny
   resting bid, which proves post-only orders work on this account before Sadie relies on them.
c. `python -m desk new-season --config desk.real.yaml --pool 250 --level heavy_maker=Associate --why "Sadie alone, from the 10-month backtest"`
   (Associate = 1% of the pool per bet. Check the printed roster says only heavy_maker.)
d. Owner resumes real trading on the dashboard (the kill switch on the real book's Safety card).
e. Within an hour, check the real book on the dashboard: Sadie's bids appear in `real.orders` with
   kind `maker`; fills arrive as "maker fill" rows; fees are 0.

**The trial** (two weeks, ~1,000 real fills). Pass: most posted bids fill within their two minutes (under
~70% means the backtest's fill rule is too kind) and profit is at least +0.4c per $1 bet. Then raise the
pool to $1,000 (another `new-season --pool 1000`, or a deposit) at 1%. Below zero after ~1,500 fills: halt
and go back to Training. Useful queries:

```sql
-- fill rate and edge for Sadie's real bids
select count(*) filter (where kind = 'maker') as bids, sum(filled) filter (where kind = 'maker') as contracts
from real.orders where ts > now() - interval '14 days';
select count(*) as bets, round(sum(pnl)::numeric, 2) as pnl from real.settlements where season = (select max(season) from real.settlements);
```

### 2. Backfill Training on the dashboard from Dec 10, 2025 (not done yet)

The owner wants the Training view to show the whole backtest: $1,000 put in on 2025-12-10, run by the
current Training staff, to today. **None of this is in the database yet**: the backtest ran in a cloud
session that couldn't reach it. `desk seed-season` does it through the bot's own code (strategy, pool
sizing, broker), and was extended to replay resting bids from each minute's bid low/ask high.

a. Download the history (about 2 hours; resumable, finished months are kept):
   ```bash
   cd research/stella_backtest
   for s in KXBTC15M KXETH15M KXSOL15M KXXRP15M KXDOGE15M; do python fetch.py $s data/; done
   for s in KXBTC15M KXETH15M KXSOL15M; do python fetch_archive.py $s data/ & done; wait
   python to_store.py data/ ../../data/history-full.db
   cd ../..
   ```
   (XRP/DOGE archives can be added the same way; Training trades them, from Aug 16 on.)
b. Dry run (about 2 minutes; writes nothing):
   `python -m desk seed-season --days 318 --history data/history-full.db --max-bet 10`
   Expect roughly **$1,000 -> $18,000**: Sid +$7.3k, Sadie +$5.1k, Coco +$3.7k, Stella +$1.0k, worst day
   about -$530, 238 of 316 days up (the cloud dry run on 2026-10-24). Pick `--days` so the start is Dec 10.
c. Tell the owner, before applying:
   - The `--max-bet 10` cap matters. Uncapped, 1% bets compound to $1,000 -> $292,000, which no market
     could fill. $10 matches the real book's order cap.
   - It's the optimistic version: the real trade tape says resting-bid fills earn ~25% less than this
     rule, and the edge has shrunk (about 0.4c per $1 so far in October vs 2-3c early in the year).
   - It writes ~130,000 fills plus settlements and hourly equity into Supabase (maybe 80-100 MB of the
     free plan's 500 MB). Check usage first; `--days 120` is a lighter option.
   - After seeding, Training's live paper bets are 1% of an ~$18,000 pool (~$180 each, no cap live).
     It's pretend money, but the dashboard's dollars will look big next to the real book.
   - It starts a new Training season (the current one stays in the history).
d. With the owner's yes: same command plus `--apply --why "Backtest from Dec 10, \$10 bets"`. It takes the
   bot's lease, so retry if a run is in progress.
e. Check the dashboard's Training view and the phone widget show the season starting Dec 10.

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
