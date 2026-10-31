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
