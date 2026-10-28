"""Sadie's idea on the daily-high weather markets, on a fixed clock (2026-10-27).

The scan (scan.py) measured time back from each market's LAST trade, which leaks the outcome in weather (dead
brackets stop trading early). Here the clock is the same for every bracket of a day: at local hour LOOK on the
day (or the evening before), take the side whose last traded price is in LO..HI, rest a bid there (the last
price that side traded at), and let trades until local hour STOP fill it with maker_bets.py's harsh rules
(a trade through our price fills in full, a trade at it gives QUEUE of it). $CAP per market, held to settle.
Weather markets charge makers no fee. Sampled tape: busy slices are incomplete, so fills are undercounted.
    python research/other_markets/wx_maker.py data/other        env QUEUE (0.3), CAP (10)"""
import gzip, json, math, os, sys
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

D = sys.argv[1]
QUEUE, CAP, LAT = float(os.environ.get("QUEUE", "0.3")), float(os.environ.get("CAP", "10")), 1.0
TZ = {"KXHIGHNY": "America/New_York", "KXHIGHLAX": "America/Los_Angeles", "KXHIGHCHI": "America/Chicago",
      "KXHIGHMIA": "America/New_York", "KXHIGHAUS": "America/Chicago", "KXHIGHDEN": "America/Denver"}
MON = {m: i for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}

markets = []
for s in TZ:
    with gzip.open(os.path.join(D, f"{s}.jsonl.gz"), "rt") as fh:
        for line in fh:
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            code = m["event"].split("-")[1]
            m["day"] = (2000 + int(code[:2]), MON[code[2:5]], int(code[5:7])); m["s"] = s
            markets.append(m)


def run(look, stop, lo, hi):
    """look/stop: local hours on the day (negative = the evening before, e.g. -6 = 18:00 the day before)."""
    out = []
    for m in markets:
        tz = ZoneInfo(TZ[m["s"]])
        base = datetime(*m["day"], tzinfo=tz).timestamp()
        t_look, t_stop = base + look * 3600, base + stop * 3600
        best = {"yes": None, "no": None}
        for t, yp, n, taker, *_ in m["t"]:
            if t >= t_look:
                break
            side, p = (("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp))
            best[side] = (p, t)
        pick = [(s, v[0]) for s, v in best.items() if v and lo <= v[0] < hi and t_look - v[1] < 3 * 3600]
        if not pick:
            continue
        side, price = pick[0]
        spent = got = 0.0
        for t, yp, n, taker, *_ in m["t"]:
            if t < t_look + LAT:
                continue
            if t > t_stop or spent >= CAP:
                break
            s2, p = (("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp))
            if s2 != side:
                continue
            q = n if p < price - 1e-9 else n * QUEUE if abs(p - price) < 1e-9 else 0
            q = min(q, (CAP - spent) / price)
            if q >= 0.01:
                spent += q * price; got += q
        if spent > 0:
            out.append({"s": m["s"], "day": m["day"], "spent": spent, "pnl": (got if m["result"] == side else 0) - spent})
    return out


def show(label, rows):
    if not rows:
        return
    days = sorted({r["day"] for r in rows}); half = days[len(days) // 2]
    c = lambda rs: sum(r["pnl"] for r in rs) / max(1e-9, sum(r["spent"] for r in rs)) * 100
    byday = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        byday[r["day"]][0] += r["pnl"]; byday[r["day"]][1] += r["spent"]
    v = [a / b for a, b in byday.values()]
    mu = sum(v) / len(v); sd = (sum((x - mu) ** 2 for x in v) / max(1, len(v) - 1)) ** 0.5
    t = mu / sd * math.sqrt(len(v)) if sd else 0
    lost = sum(r["pnl"] < 0 for r in rows) / len(rows) * 100
    cities = " ".join(f"{s[6:]} {c([r for r in rows if r['s'] == s]):+.0f}" for s in TZ if any(r["s"] == s for r in rows))
    print(f"  {label:34s} {len(rows):4d} bets lost {lost:4.1f}%  {c(rows):+6.2f}c per $1 | halves "
          f"{c([r for r in rows if r['day'] < half]):+6.2f}/{c([r for r in rows if r['day'] >= half]):+6.2f} | "
          f"days up {sum(x > 0 for x in v)}/{len(v)} t {t:+.1f} | ${sum(r['pnl'] for r in rows)/len(days):+.2f}/day | {cities}")


print("Resting bids on weather favorites, fixed local clock, harsh fills, $10 cap")
for look, stop in ((-6, 0), (0, 8), (8, 11), (10, 13), (12, 15), (14, 17)):
    lab = lambda h: f"{h % 24:02d}:00{' prev' if h < 0 else ''}"
    print(f"bid at {lab(look)}, fills until {lab(stop)}:")
    for lo, hi in ((0.50, 0.70), (0.70, 0.85), (0.85, 0.92), (0.92, 0.97), (0.97, 0.995)):
        show(f"{lo*100:.0f}-{hi*100:.0f}c", run(look, stop, lo, hi))
