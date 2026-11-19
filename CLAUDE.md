# Kalshi Desk: notes for Claude

A Kalshi trading bot whose strategies are "employees" sharing one office pool. Two books run side by
side on every hosted run: **Training** (pretend money, `desk.yaml`) and the **real book** (real money
on Kalshi, `desk.real.yaml`). Hosting: Supabase Postgres, the dashboard on Vercel, the bot on the always-on server since 2026-11-16
(deploy/SERVER.md: systemd timer every 2 min; Vercel's free plan ran out), background jobs on GitHub Actions. Local commands read the same Supabase
database through `DATABASE_URL` in `.env` (session pooler, port 5432).

**Pushing to main deploys** (2026-11-03): both Vercel projects build production from GitHub, each only when its own
files change (deploy/README.md). Run any database change the new code needs BEFORE pushing.

Tests: `python -m pytest -q` (all offline); the what-if math: `node web/lib/whatif.test.ts`. Web type-check: `cd web && node_modules/.bin/tsc --noEmit -p .`

## The owner's #1 priority (2026-11-19, in their words: "make sure this is clear")

**Always choose whatever gives the highest likelihood of the highest portfolio value in the long run**: employee levels,
brakes, bet sizes, caps, hires, betting rules, anything. Decide with backtests and the prediction model (desk/forecast.py,
many futures, the same futures for each setup), never with gut feel or a bad streak, and even if it looks bad short-term.
The owner would rather avoid brakes and per-employee tuning such as bet caps, but the long-run money decides: keep them
only if the model and backtests show they make more.

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
  since the coin check. **11-01: 3% (window_cap 0.12) at the owner's go**, ahead of the ~300-bet plan; levels all Associate.
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
  code went out (database first, or her money would have dropped from the books). New hires join a pool with $0.
- **11-01: Bitcoin Bea on real money too** (bitcoin back in desk.real.yaml `crypto_series`) after her trade-tape test
  (research/fast_coco/btc_check.py: +2.11c per $1 with the coin check, halves +3.33 / +0.89, 8 of 11 weeks up).
- **11-02, Training experiments:** four thinner 15-minute coins get specialists on Sadie's rules (📣 Hype Hannah
  `maker_hype`, 🔔 Binance Belle `maker_bnb`, 🧭 Nearly Nadia `maker_near`, 🕶️ Zcash Zoe `maker_zec`; Kraken-only prices;
  real book `enabled: false`; trade tape downloading to data/tape_new). Wendy bids midnight-6 am only (two-year
  replay). Fiona's year of end-of-game trades: research/other_markets/sports_history.py -> fiona_years.py.
- **11-02: Nadia (NEAR), Belle (BNB) and Zoe (ZEC) on real money too** (owner's go) after passing the trade-tape test
  (+2.3c / +1.6c / +1.7c per $1, both halves); Hype Hannah stays Training-only. Real book: 8 coins, 3% bets,
  window cap 12% shared, max_orders_per_day 3200. Fast trial has a second, coin-checked pair (fast_check/twin_check). Wendy's two-year weather tape: research/other_markets/wx_history.py.
- **11-02: Ziggy (`sports_closer`) by league** after a year of game-end trades (research/other_markets/README.md): NBA from 3 h
  before Kalshi's expected end, MLB and NHL from 1 h before (both lost money earlier), to 2 h after; football dropped.
- **11-03: 🐸 Weather Wendell on real money** (owner's go; desk.real.yaml `other_series` = his six cities, mid-season hire
  with $0, starts as Intern = half-size bets). The settling allowance in reconcile is now 12 h (weather pays out slowly).
- **11-04: Wendell's first real night.** Two fixes: other markets are looked for 30 h ahead (config other_horizon_hours;
  a day's weather market is dated ~25 h after the city's midnight, so he missed the first hour), and Kalshi's target
  allocation never moved cash to shard 0, so runner.split_cash now transfers it (status `_shard_move`, at most every
  10 min; each run logs `shards` in real.runs). His first real bids went up 05:36 UTC.
- **11-04: pauses, again.** The owner would rather trade through differences that fix themselves: the safety check now
  waits 15 checks (30 minutes, runner.MISMATCH_CHECKS) and turns trading back on by itself once the books agree (only
  its own pauses; the manager's and the $40 daily-loss stop stay). The site's "trading paused" under the balance was
  shown on any one-check difference while nothing was paused: now it says trading carries on.
- **11-03: pauses.** The safety check now halts only when the SAME market differs from Kalshi on 3 checks in a row
  (runner.MISMATCH_CHECKS): fills and payouts reach Kalshi and us seconds apart, and three different one-check races
  in a row had halted trading. Paused? The home page shows a banner with ▶️ Resume (manager login), phone-friendly.
  Kalshi pays for orders from the market's shard only (coins 2, weather 0): desk.real.yaml `shards` has the bot keep
  the cash split (before it, all 1,409 of Wendell's first bids were refused for "insufficient balance").
- **11-03: edge hunt.** 🐿️ Hourly Hazel (`hourly_btc`, desk/strategies/other_markets.py) on Training: Sadie's bids on
  bitcoin's hourly ladders (KXBTCD in desk.yaml `other_series`), 5-21 min left; a month of trades +0.6c per $1
  (research/fast_coco/README.md). Real book `enabled: false`. More weather cities: no edge (research/other_markets/README.md);
  Wendell keeps all six (every city up in both years at midnight-6 am).
- **11-05: season 8 on the real book at $300** (owner deposited $206.18 onto $93.82; season 7 ended +$19.36 from $74.44).
  Same 9 employees, 3% bets ($9), window cap 12%, order cap 25% of the pool, daily-loss halt 20%. The chart starts at
  $300; the old "keep season 7's chart" rule is over. Wendell's temporary `end_hour: 0` (no bets the night before) was removed.
- **11-09: moving an employee to real money needs no new season** (`python -m desk hire KEY --config desk.real.yaml`,
  or 💵 Move to real money on a Training employee page, manager login). hr.hire adds them to the real policy's
  `hired` list, which beats the yaml's `enabled: false`; the runner adds their markets to the book's lists
  (runner._add_staff_markets) and they join with $0 as an Intern. A coin specialist also needs their coin in
  desk.real.yaml `crypto_symbols`. Firing still wins. 🐿️ Hourly Hazel was the first (11-09).
- **11-09: the real book runs its own weekly reviews** (`auto_hr: true`; the owner wants an office that runs itself):
  award, promotions, demotions, and for Interns strikes, where 2 bad reviews in a row bench them for a week (a week
  that isn't bad wipes their strikes). Before this the real book only gave the award.
- **11-09: the books repair themselves from Kalshi.** On any difference, LiveBroker.repair reads Kalshi's fills list
  (every shard), books fills on our finished bids that we missed (matched by order id, so never twice), settles
  them and looks again; only timing differences are left to wait out. Claude may also fix real-book records directly.
- **11-09: money in or out mid-season needs nothing from anyone.** Deposit or withdraw on Kalshi; once Kalshi's cash
  stays off from ours by the same amount for 5 checks (~10 min) with every position agreeing (runner.CASH_CHECKS,
  money_in_or_out), the bot shares it across the pool by what each member holds, as transfers with reason
  deposit/withdrawal (capital, not profit; the pool's day and high move with it), and logs a `money` event. The
  charts mark it (web MoneyMarks). Shards rebalance when one falls under 3/4 of its share (was half).
- **11-09: friends' offices** (desk/offices.py, deploy/SERVER.md): up to ~3 friends, each with their own Kalshi account
  and key, run on the server (`kalshi-offices` service, every 2 min, 30 s after the owner) in schemas `office_<name>`.
  Same staff and rules as the real book (playbook synced every 10 min: hires, firings, settings, bet size); own pool,
  levels, reviews, awards, pause button; no phone pings. They decide on the owner's clock (Desk.lag) and join a family
  bid instead of topping it (Desk.family), so they never get ahead of the owner. Website: passkey logins, 400-day
  sessions (lib/session.ts), invites from the cockpit's Invite a Friend card (manager; /offices redirects there since 11-17), sign-up at /join/<token>; a friend sees only their office.
  Kalshi keys are locked to the server's key (/etc/kalshi-desk-offices.pem; public half in web/lib/vault.ts).
  Tables: deploy/friends.sql. Manager actions refuse office books (app/actions.ts managedBook).
- **11-16: website speed.** Training's season is ~40,000 bets (5 MB, over Next's 2 MB cache limit), so pages no
  longer read every bet: after each run the bot writes the season by day (status row `_page`, one row per employee per
  day, added up inside Postgres; Ledger.publish_page_summary) and pages take single bets only for the latest two weeks
  (web/lib/season.ts betWindow; past days cached for hours, today's after each report) and daily rows before that. The
  bot then calls /api/warm (desk/cloud.py warm_site; `DESK_WARM_URL=off` stops it). Never pass whole-season bets to a page.
  Don't call `revalidatePath` just to refresh the screen: in Next 15 it marks every cached database read stale
  (unstable_cache's implicit path tags), which made every book switch slow until 11-17. Use revalidateTag(bookTag) for data.
- **11-17: four themes on one shared look** (web/app/themes): base.css is Studio's styling for every page and shared
  piece; studio/office/desktop/terminal.css only set colours, type, corner sizes (`--r-pill/xl/lg/md/sm`) and a few
  decorations, each in dark and light. New pieces: style them in base.css with `var(--r-*)` corners, never a theme file.
  Everyone was reset to dark Studio (cookie/pref names `skin`/`shade`); a signed-in person's pick follows them to every device.
- **Fast Sadie trial** on the server (desk/fast.py, from 2026-10-26 07:12 UTC): always-on bid vs a 2-minute cron twin,
  pretend money from $87.63 each. `python -m desk fast-report`. So far it fills more, not better per $1.

- **11-02: the cast got a makeover** (names, portraits, bios, quips only; keys, books and settings unchanged). Older notes
  above use the old names: `maker_btc` Bea -> 🦫 Bitcoin Barnaby (beaver), `maker_eth` Esther -> 👻 Ethereal Ethel (ghost),
  `maker_sol` Sally -> 🦎 Sunny Salazar (iguana), `maker_xrp` Rita -> 🐙 Captain Ripley (octopus), `maker_doge` Dot -> 🐕
  Mochi the Doge, `maker_hype` Hannah -> 🐹 Hyper Hank (hamster), `maker_bnb` -> 🐝 Bumble Belle (bee), `maker_near` Nadia
  -> 👓 Nearsighted Ned (mole), `maker_zec` Zoe -> 🦝 Zed the Raccoon, `weather_maker` Wendy -> 🐸 Weather Wendell (frog),
  `sports_closer` Fiona -> 🦓 Ziggy the Zebra. The office floor page is gone. The weekly award (and the bonus pot) now
  goes to the best profit per $1 bet (shrunk for small samples, hr.PeriodStats.award_score), not the most dollars.
  The phone widget shows the website's headline (lib/portfolio.ts `headline`: Kalshi's own balance on real money).

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
- **11-17: the window cap is shared by closing moment** (desk/paper/pool.py event_of): every 15-minute coin window
  and hourly ladder that closes at the same time counts against one 16% cap ("close 26NOV171100"). It was per coin,
  and an 8 AM PT dip took $198 (20%) in one instant and tripped the real book's 20% hard stop. Season replay: -3%
  profit, worst moment halved. Same day: a fresh-process bug had capped real orders at $40 since 11-14 (runner check_guard).
- **11-17: five coin specialists to VP** on the real book and both offices (DOGE, SOL, NEAR, ETH, BNB): a replay of every
  book (research in session; sizing grid of bet % x window cap) showed coin specialists earn the most per $1 in both real
  and Training, and the cap makes the share between employees matter more than bet size. Kept 4% bets and the 16% cap:
  in-sample "bet more" always wins on 2-3 weeks of 97% win rates, which is the overbetting trap.
- **11-17: the bot's daily-loss halt is daily** (guard.check_loss gets the pool's day): it lifts itself when the new
  day starts, and a manager's resume the same day sticks (before, the next run re-halted, and the halt waited for a
  person even after midnight). The pool's 15% daily stop still holds new bets until midnight either way.
- **11-17: the new-user experience (NUX).** New friends get prefs.nux = "setup" at joinStart; the home page sends them
  to /welcome (JoinFlow: welcome + passkey, Kalshi account (have one / create one), making an API key, pasting it
  with live checks in lib/keycheck.ts; connectKalshi sets nux "money": an optional deposit step with the balance
  Kalshi reported; Start the tour sets nux "0"); then components/Tour.tsx (mounted in the layout)
  spotlights one thing per step, saving the step in prefs.nux until "done". Existing users have no nux. The manager's
  👀 Preview as a new friend (cockpit, Invite card) runs it all on pretend data (a made-up key, a $0/$50 pretend balance; /welcome?preview=1, localStorage), and
  its tour shows the manager's home as a day-one office (cookie nux_fresh, lib/fresh.ts). The tour ends when they tap a
  theme. The tour quotes a 6-month estimate computed on the cockpit (a hidden .working-estimate on "Is it working?":
  every office's profit per $ per day so far, full pace, no compounding) for the viewer's money (their office, or
  prefs.kalshi_balance before it opens) or $100. **Update it when the prediction model (ebb, flow, taper) is built.**
  The preview cookie holds the pretend balance and gives the manager a friend's header, cockpit, rules and empty pages.
  Tour targets are CSS selectors (.money-hero, .team li a, .employee-chart, .cockpit-main, .menu > summary, menu links,
  [data-tour=pause], .theme-tiles): renaming those classes breaks the tour.
- **11-17: free-plan housekeeping.** Database was 481 of 500 MB: Ledger.prune_logs (every 6 h) keeps runs 7 days,
  decisions and market tape 14, equity thinned to hourly after 14, closed-market history 30 (RETENTION); the first
  trim was archived to /home/desk/archive/2026-11-17 on the server (deploy/archive_logs.py) -> 338 MB. Kalshi 429s
  (~16k a day, 360 skipped market lists): the client slows down after a 429 and honours Retry-After, a failed list
  keeps the windows already known, windows are looked up every 4 min. Downloads: /api/warm skips when nobody has
  been on the site for 20 min (public.status '_seen'), and the saved coin-price history is compact.
- **11-17: the prediction model** (desk/forecast.py; `python -m desk forecast`; server timer kalshi-forecast daily 3:20 am PT,
  ~4 min per office at low priority -> each real-money office's status `_forecast`). A replay library of every coin
  window on Kalshi's trade tape (desk/forecast_library.json.gz from research/forecast/library.py: live rule + coin check,
  what a bid of ANY size fills and makes), sampled whole days so coins lose together. Edges = tape blended with real
  bets (300-bet prior) plus a 0.6c "the market changes" doubt; family offices share each window and grow together;
  window cap, daily stop, brake, weekly reviews. Bids above `tested` (the family's biggest real bids that filled, >= $60)
  get an uncertain extra fill penalty: almost all future growth is in untested sizes. Hourly Hazel and Wendell have no
  tape library (assumed size limits, marked). Self-check: started at $300 on 11-05 the real value on 11-17 sat at the
  58-65th percentile. Bad-day guard research (same session): skipping bids after fast coin moves didn't change the
  worst days; skipping crowded moments halved profit; the shared window cap is the tool. Cockpit card "Where It's
  Heading" (components/ForecastCard.tsx, manager only, the real book's fan at 1/3/6 months); options B-D were set aside.
  Later 11-17: Training's paper bets count half a real bet in each edge; promotions need the confidence gate; the
  owner's row carries `newcomer` (a new friend's office from $50-$5,000, made monotonic) and every row a daily `log`
  of 7/30-day predictions (grade the model from it after a week). The NUX "Is it working?" estimate now reads the
  model (lib/forecast.ts sixMonths: own office's 6-month p50, else the newcomer table; old pace math only before the
  model's first run).
- **11-17: bet caps from the model** (Forecaster.caps -> status `_bet_caps` per real-money office, nightly): per employee,
  the family bid where one more dollar stops adding profit, times the office's share of the family's money; runner.size
  never bets above it (only trims). First caps ~$230 owner-side for BNB/NEAR/ZEC, ~$800-925 for the rest; Hazel and
  Wendell uncapped (assumed limits have no turning point). Replay: at a $37k pool ~$389/day capped vs ~$287 uncapped.
- **Capacity hunt (11-17):** hourly ladders for other coins already failed (11-12 notes). Kalshi lists ADA/BCH/TON 15-min
  series with no markets yet (recheck). Gold's 15-min windows trade ~4.7x SOL's; oil/silver ~SOL. Replay library at
  97c+ (research/forecast/cmdty_0.97.json.gz, Sep 10-Nov 9, no coin check): silver +1.43c (halves +1.35/+1.45), oil
  +1.07c (+1.8/+0.64), gold +0.28c; oil and silver hold their edge to ~$1-2k bids.
- **11-19: 🦭 Crude Clyde (`maker_wti`, oil) and 🐉 Bertie (`maker_natgas`, natural gas) on real money** (owner's go; all three
  offices via the playbook). The prediction model with oil and gas in its library (1,000 futures x 3 seeds, same futures per
  setup): 6-month middle guess ~$51k as now vs ~$59k with both (+16%), same bad case. desk.real.yaml pins them at 97c+
  (else they'd inherit the coin team's 92c); commodities need no price feed (`needs_feed = False`, no coin check). Shard 2.
  Same day, after two losing days (-$318), the model compared office setups: as now beat benching or capping Hourly
  Hazel (-40% / -30% at 6 months) and a $35 bet cap (-77%); the model's own caps beat none. Decide setups with the model.
- **11-19: Hourly Hazel's replay library** (research/forecast/hazel_library.py, 45 days of KXBTCD trades, every strike, any
  bid size: +0.7c per $1 to ~$40 a strike, zero near $1,000) replaced her assumed limits, which had her betting a third of
  what she really does. Her Training bets no longer count in her edge (forecast.PAPER_SKIP: paper +1.65c vs real +0.87c).
  With it: keep Hazel as is (benching -65%, a $15 cap -55% at 6 months; her level makes no difference, the window cap
  binds). Gold and silver stay on Training (no gain, worse bad case). The friends' offices' low self-check percentiles
  (Judson 0.5th, Colin 11th) are NOT a friend penalty: their whole history is Nov 16-19, the worst days, and per $1 they
  did better than the owner on them. The model still leans optimistic overall (owner at the 27th percentile): grade the
  `_forecast.log` from ~11-24. Open: the model's caps for Hazel are tighter than its own simulation likes (uncapped +30%).
- **11-19: slump brake and the pool's 15% daily stop OFF** (owner's go; real.settings pool brake_drawdown/brake_factor/
  daily_stop = 1.0, synced to the offices). The model, with futures starting from the office's real high (Book.peak):
  no gain from either (removing both +3% at 1 month, a hair more at 6). The 20% daily-loss halt (desk.real.yaml live
  max_daily_loss_pct) stays, for bugs, not market luck. Same day: bad days don't cluster in the trade history (no streak
  term in the model), and the Nov 16-19 slump wasn't the friends: real Hazel matched her replay on the same markets
  (-2.0c vs -1.2c), coins matched Training on the same markets; the markets themselves lost, within luck.
- A weather day can sit unsettled for days on Kalshi's side (NY Nov 13, 2026: "closed", no result, Kalshi's deadline
  Nov 20, while every other city and day paid next morning ~7 am PT). Not a bug: settle_check asks Kalshi about every
  held ticker each run, listed or not, and books it the moment a result appears; Riding Now shows them as "settling".
- `seed-season` refuses a live book: the real book's history is Kalshi's.
