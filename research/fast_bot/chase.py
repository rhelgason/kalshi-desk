"""
A chaser bot on the real tape: when bitcoin moved lo..hi basis points over the
last 2 seconds, buy the matching side at the ask our order would meet `lat`
seconds later (rebuilt from the tape at sub-second precision). $stake a trade,
at most one trade per `cool` seconds per market, none in the last minute.
Scored at settlement and against Kalshi's mid 60s later.
"""
import bisect, math, sys
from tapelib import Spot, load_markets, taker_fee
from fast import quote_series

spot = Spot()
ms = [m for m in load_markets() if m["open"] - 960 > spot.lo and m["close"] < spot.hi]
days = len(ms) / 96


def run(lo, hi, lat, stake=20.0, cool=5, window=2, first=None, last=None):
    out = []
    for m in ms:
        if first is not None and not (first <= m["open"] < last):
            continue
        tr = m["trades"]
        times = [t for t, *_ in tr]
        yes_t = [t for t, s, *_ in tr if s == "yes"]; yes_p = [p for t, s, p, n in tr if s == "yes"]
        no_t = [t for t, s, *_ in tr if s == "no"]; no_p = [p for t, s, p, n in tr if s == "no"]
        q = m["q"] if "q" in m else quote_series(m)
        m["q"] = q
        nxt = 0
        for s in range(int(m["open"]) + 5, int(m["close"]) - 60):
            if s < nxt:
                continue
            a, b = spot.at(s - window), spot.at(s)
            if not a:
                continue
            move = math.log(b / a) * 1e4
            if not (lo <= abs(move) < hi):
                continue
            when = s + lat
            if move > 0:
                i = bisect.bisect_right(yes_t, when) - 1
                if i < 0 or when - yes_t[i] > 3:
                    continue
                side, price = "yes", yes_p[i]
            else:
                i = bisect.bisect_right(no_t, when) - 1
                if i < 0 or when - no_t[i] > 3:
                    continue
                side, price = "no", 1 - no_p[i]
            if not (0.05 <= price <= 0.95):
                continue
            n = math.floor(stake / price)
            fee = taker_fee(price, n)
            later = q.get(s + 60)
            if not later:
                continue
            mid = sum(later) / 2
            val = mid if side == "yes" else 1 - mid
            won = m["yes"] if side == "yes" else 1 - m["yes"]
            out.append((m["ticker"], n * (val - price) - fee, n * (won - price) - fee, fee, n))
            nxt = s + cool
    return out


def show(name, r):
    if not r:
        print(name, "none"); return
    mk = sum(x[1] for x in r); st = sum(x[2] for x in r)
    by = {}
    for x in r:
        by[x[0]] = by.get(x[0], 0) + x[2]
    v = list(by.values()); mu = sum(v) / len(v)
    se = (sum((y - mu) ** 2 for y in v) / max(1, len(v) - 1)) ** 0.5 * math.sqrt(len(v))
    print(f"{name:38s} {len(r) / days:5.0f} trades/day  60s mark ${mk / days:+7.2f}/day "
          f"({mk / sum(x[4] for x in r) * 100:+.2f}c/contract)  settled ${st / days:+7.2f}/day (±{se / days:.0f})")


print(f"{len(ms)} markets, {days:.1f} days")
for lo, hi in ((1, 3), (1, 2), (2, 3), (3, 99)):
    for lat in (0.0, 0.25, 0.5, 1.0, 2.0):
        show(f"move {lo}-{hi}bp, order lands {lat:.2f}s", run(lo, hi, lat))
    print()
