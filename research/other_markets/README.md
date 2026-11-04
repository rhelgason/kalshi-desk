# Other Kalshi markets: is there a better edge than crypto? (2026-10-27/28)

Curiosity research only, nothing here runs live. Question: does Sadie's idea (resting bids on favorites) or the
open-source bots' ideas (weather forecasts, sports) beat crypto Sadie's ~+1.2c per $1 anywhere else?

## Data
- `sample_tape.py`: settled markets from the last 60 days, up to 300 per series (one per game), sampled trade tape.
  22 series: 6 weather cities, NFL, college football, MLB, NBA, ATP/WTA/Challenger tennis, gold/oil/euro 15-min,
  S&P/Nasdaq hourly, gas prices, Trump mentions/approval, Rotten Tomatoes. Data in `data/other/` (gitignored).
- `refs.py`: each market's scheduled time (`expected_expiration_time`), set before trading, for a fair clock.
- `pregame.py`: every trade from 12 h to 4 h before that time for the sports markets (the sample misses pre-game).
- `forecasts.py`: Open-Meteo archived day-ahead forecasts for the 6 weather stations (free).

## The trap (why scan.py's table is wrong)
`scan.py` adds up what makers and takers earned by time before each market's LAST trade. That clock leaks the
result: losing brackets and losing teams stop trading early, and late trades happen after the game is decided. So
every group shows the same picture (+12c at 85-92c, +5.6c at 92-97c, +1.5c at 97-100c, t up to 100). It is just
"the winner was already known". Only the 15-minute and hourly series, which close at a fixed time, are clean there.

## Fair-clock results (`fixed_clock.py`, `pregame.py`, `wx_maker.py`)
Resting bid at the side's last trade price, harsh fills (through our price = filled, at our price = 30%), $10 cap,
held to settle, after maker fees (sports charge makers ~0.0175 x p(1-p); weather/coins/commodities don't).

| Market | Result |
|---|---|
| Weather favorites 92-97c, bid overnight / morning | **+3.7 to +4.8c per $1, t 4-5, both halves up**, but ~3 bets a day (~$1/day at $10) |
| Weather 97-100c, any time | +0.9 to +1.2c, almost never loses, ~$1-1.7/day |
| Weather forecast model vs price (the weather bots' idea, `wx.py`) | **-15 to -50c per $1**: the market knows more than free forecasts |
| Sports pre-game (NFL/NCAAF/MLB/NBA/tennis), 30-92c | noise, -11c to +4c, nothing significant: priced off sharp sportsbooks |
| Sports pre-game 92-99c | +5c on 40 bets, 0 lost (expected ~2): too few to tell |
| Sports in-game 97-100c (game basically over) | +1.2 to +1.7c, 0 lost, ~$0.2-0.5/day: tiny |
| Tennis in-game 85-97c | +6 to +10c on ~30 bets in two cells, neighbours noise: likely multiple testing |
| Gold/oil/euro 15-min | one good cell (92-97c at 7-9 min: +5.8c, 57 bets), neighbours -1 to +2c: not better than crypto |
| S&P/Nasdaq hourly, Trump mentions | too thin to replay |
| Trump approval | negative |
| Rotten Tomatoes, gas 97-100c | +1.3 to +1.5c, 0 lost, very few bets (only 9 days of RT markets) |

## Verdict
Nothing clearly beats crypto Sadie except **weather favorites at 92-97c overnight/morning** (~3-4x the cents per $1,
but few bets, so similar or smaller dollars per day at a $10 cap). ~60 cells were tested, so a couple of "good" ones
are expected by luck; the weather overnight row survived two different clocks (wx_maker.py local hours and
fixed_clock.py scheduled time) and both halves. If it is ever tried: Training first, $10 cap, about 3 bets a day.
Sports: no edge found pre-game, and makers pay a fee there. Matches the "Makers and Takers" paper (Burgi, Deng &
Whelan): favourites are slightly underpriced in every Kalshi category, by about 1-5c, never by enough to get rich.

## Wendy on two years of weather (2026-10-31)

`wx_history.py` downloads every trade from 18:00 the evening before to 13:00 on the day, city time, for every
daily-high market in the six cities since Nov 2024 (Kalshi's /historical endpoints hold markets settled before its
cutoff; ~25,700 markets). `wx_years.py` replays Wendy as the bot runs her: 2-minute looks from midnight to 11 am,
110 s bids at the side's last price, harsh fills, $10 a market.

- All: 12,507 bets, **+0.83c per $1, t 3.7**, 3.3% lost. Far below the 60-day +3.8c: that window was a good one.
- Year to Oct 2025: +0.21c (t 0.8), losing Nov 2024 - Mar 2025. Year to Oct 2026: +1.24c (t 5.2), every season up.
- Every season positive over both years (winter weakest, +0.67c t 0.6). Prices: 95-97c best (+1.21c, t 2.8).
- Cities: Chicago +1.99c (t 5.9) and Miami +1.53c (t 4.1) up in both years; LA +0.61c up in both; New York, Austin
  and Denver about zero (lost in the first year, up in the second).
- Verdict: a real edge about Sadie's size, not 3-4x it, and it was zero a year ago. Training only for now; the
  candidate rule for real money would be Chicago + Miami (+LA), each up in both years on its own.

## Wendy's best hours (2026-11-02)

Same two-year replay (`wx_years.py`, START/END in city hours on the day; negative = the evening before):

| Hours | Bets | Per $1 | t | Notes |
|---|---|---|---|---|
| 6 pm - midnight (evening before) | 7,259 | +0.40c | 0.9 | NY and Austin lose |
| **midnight - 6 am** | 7,794 | **+1.48c** | **5.4** | both years up (+1.12c, +1.61c), every season, every city up in both years |
| 6 am - 11 am | 11,511 | +0.64c | 2.6 | Denver and Austin about zero |
| midnight - 11 am (what she ran) | 12,507 | +0.83c | 3.7 | |
| midnight - 4 am / 2 am - 8 am | 6,931 / 8,308 | +1.51c / +1.08c | 4.7 / 2.8 | the edge fades after ~6 am |

Training's Wendy now stops at 6 am city time (desk.yaml `end_hour: 6`). Four windows were tried, so a little luck is
in the winner, but t 5.4 with every city up in both years is far beyond what four tries would hand out by chance.

## Fiona/Ziggy on a year of games (2026-11-02, `sports_history.py` -> `fiona_years.py`)

Every game Kalshi listed Nov 2025 - Nov 2026 in NFL, college football, NBA, MLB and NHL, one winner market per game,
every trade from 3.5 h before Kalshi's expected end to 2 h after (downloaded on the server). Her rules (97-99.5c,
3 h before to 2 h after, 2-minute looks, harsh fills, $10 a game, after the sports fee): 6,587 bets, +0.74c per $1,
t 6.4, both halves up. Split by league and by when the bet filled:

| League | 3 h to 1 h before the end | last hour | after the end | whole league |
|---|---|---|---|---|
| NBA | +2.14c (467) | +1.00c (868) | +1.54c (18) | +1.40c |
| MLB | -0.59c (579) | +1.48c (1,448, t 10) | +1.45c (335) | +0.96c |
| NHL | -1.24c (244) | +0.72c (1,106) | +1.03c (62) | +0.40c |
| NFL | +2.14c (69) | -0.66c (134) | +0.34c (98) | +0.30c |
| college football | +0.42c (386) | -0.40c (335) | -0.11c (438) | -0.02c |

Baseball and hockey lose money while the comeback is still possible and pay once the last hour starts; football
never paid enough to matter. Training's Ziggy now bets NBA from 3 h before, MLB and NHL from 1 h before (to 2 h after
for all), no football (`FinalWhistleFiona.HOURS_BEFORE`). That pick was made from this same year, so expect less than
the table: roughly +1.2c per $1 on the leagues kept.

## More weather cities (2026-11-03, `wx_history.py` / `wx_years.py` with `MORE`)

The daily highs Kalshi added in 2026 (one year of trades each) on Wendell's rules (midnight-6 am, 92-99.5c, harsh
fills, $10 a market). First nine cities together: 4,718 bets, **-0.16c per $1** (t -0.4), while Wendell's own six
made +1.6c over the same year. Atlanta +0.9c, Houston +0.9c, Oklahoma City +1.2c (all t < 1), San Antonio 0,
Philadelphia -0.3c, New Orleans -0.2c, Minneapolis -0.2c, Boston -1.0c, DC -2.2c. Picking the three that were up
out of nine would be luck-fitting: no new cities. (Phoenix, Las Vegas, San Diego, Seattle, San Francisco and the
daily lows in Wendell's cities still downloading.)
