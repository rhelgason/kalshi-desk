"""Do free weather forecasts beat Kalshi's daily-high markets? The weather bots' idea, backtested (2026-10-27).

Model: the day's high ~ Normal(yesterday's model forecast + city bias, city spread), bias and spread fitted on the
FIRST half of the days only (from which bracket won), so the second half is a clean test. At a decision time
(local clock hour HOUR on the day, or the evening before), for every bracket: the market price = the last trade
before then; buy a side when model odds - price > EDGE, paying the price + SLIP and Kalshi's taker fee; hold to the
settle. $1 of contracts per bet.
    python research/other_markets/wx.py data/other data/other_wx/forecasts.json     env HOUR (10), SLIP (0.01)"""
import gzip, json, math, os, statistics as st, sys
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

D, FC = sys.argv[1], json.load(open(sys.argv[2]))
SLIP = float(os.environ.get("SLIP", "0.01"))
TZ = {"KXHIGHNY": "America/New_York", "KXHIGHLAX": "America/Los_Angeles", "KXHIGHCHI": "America/Chicago",
      "KXHIGHMIA": "America/New_York", "KXHIGHAUS": "America/Chicago", "KXHIGHDEN": "America/Denver"}
MON = {m: i for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}
Phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))
CACHE = os.path.join(os.path.dirname(sys.argv[2]), "strikes.json")
strikes = json.load(open(CACHE)) if os.path.exists(CACHE) else {}


def event_strikes(ev):
    if ev not in strikes:
        ms = httpx.get("https://api.elections.kalshi.com/trade-api/v2/markets", params={"event_ticker": ev, "limit": 100},
                       timeout=30).json().get("markets", [])
        strikes[ev] = {m["ticker"]: [m.get("strike_type"), m.get("floor_strike"), m.get("cap_strike"), m.get("result")] for m in ms}
    return strikes[ev]


def interval(stype, lo, hi):
    """The whole-degree highs that make YES true, as a real interval with half-degree edges."""
    if stype == "between":
        return lo - 0.5, hi + 0.5
    if stype == "greater":
        return lo + 0.5, math.inf
    if stype == "less":
        return -math.inf, hi - 0.5
    return None


events = defaultdict(dict)   # (series, day) -> ticker -> market (with its tape)
for s in TZ:
    p = os.path.join(D, f"{s}.jsonl.gz")
    if not os.path.exists(p):
        continue
    with gzip.open(p, "rt") as fh:
        for line in fh:
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            code = m["event"].split("-")[1]                    # 26OCT12
            day = f"20{code[:2]}-{MON[code[2:5]]:02d}-{code[5:7]}"
            events[(s, day)][m["ticker"]] = m

# The actual high, from which bracket won (all of the event's brackets, from the API)
actual = {}
for (s, day) in list(events):
    ev = next(iter(events[(s, day)].values()))["event"]
    for tk, (stype, lo, hi, res) in event_strikes(ev).items():
        if res == "yes" and stype == "between":
            actual[(s, day)] = (lo + hi) / 2
json.dump(strikes, open(CACHE, "w"))

days = sorted({d for _, d in events})
half = days[len(days) // 2]
fit = {}
for s in TZ:
    err = [actual[(s, d)] - FC[s][d]["d1"] for (ss, d) in actual if ss == s and d < half and d in FC[s]]
    if len(err) > 10:
        fit[s] = (st.mean(err), max(st.pstdev(err), 1.0))
        print(f"{s}: forecast misses by {fit[s][0]:+.1f}F on average, spread {fit[s][1]:.1f}F ({len(err)} days, 1st half)")


def run(hour, edge, prev_evening=False):
    res = defaultdict(lambda: [0.0, 0.0, 0])   # half -> pnl, spent, bets
    for (s, day), mk in events.items():
        if s not in fit or day not in FC[s]:
            continue
        tz = ZoneInfo(TZ[s])
        y, mo, dd = map(int, day.split("-"))
        when = datetime(y, mo, dd, hour, tzinfo=tz).timestamp() - (86400 if prev_evening else 0)
        fc = FC[s][day]["d2" if prev_evening else "d1"]
        bias, sd = fit[s]
        if prev_evening:
            sd *= 1.25
        info = event_strikes(next(iter(mk.values()))["event"])
        for tk, m in mk.items():
            stype, lo, hi, _ = info.get(tk, [None] * 4)
            iv = interval(stype, lo, hi)
            before = [t for t in m["t"] if t[0] < when]
            if not iv or not before:
                continue
            last = before[-1][1]
            if when - before[-1][0] > 3 * 3600:      # nobody has traded it for hours: no real price
                continue
            py = Phi((iv[1] - fc - bias) / sd) - Phi((iv[0] - fc - bias) / sd)
            for side, odds, price in (("yes", py, last), ("no", 1 - py, 1 - last)):
                pay = price + SLIP
                if not 0.02 <= pay <= 0.98 or odds - pay < edge:
                    continue
                n = 1 / pay                               # $1 of contracts; the fee as if orders were big (no cent rounding)
                pnl = n * ((m["result"] == side) - pay - 0.07 * pay * (1 - pay))
                r = res["2nd" if day >= half else "1st"]
                r[0] += pnl; r[1] += 1; r[2] += 1
    return res


print(f"\nTaker bets ($1 each) when model odds beat the last trade + {SLIP*100:.0f}c by EDGE; 2nd half = out of sample")
for prev, hours in ((False, (8, 10, 12)), (True, (18,))):
    for hour in hours:
        for edge in (0.05, 0.10, 0.20):
            r = run(hour, edge, prev)
            cells = " | ".join(f"{h}: {r[h][2]:4d} bets {r[h][0]/max(1,r[h][1])*100:+6.1f}c per $1" for h in ("1st", "2nd"))
            print(f"  {'evening before' if prev else 'on the day'} {hour:02d}:00, edge {edge*100:2.0f}c: {cells}")
