"""
Millisecond view: after bitcoin moves on Binance, how fast does Kalshi reprice,
and can a bot that sees the move L milliseconds later still profit?
"""
import bisect, csv, glob, math, sys
from tapelib import load_markets

bt, bp = [], []
if "--coinbase" in sys.argv:
    with open("cb/btcusd.csv") as f:
        for row in csv.reader(f):
            bt.append(float(row[0])); bp.append(float(row[1]))
else:
    for path in sorted(glob.glob("agg/*.csv")):
        with open(path) as f:
            for row in csv.reader(f):
                bt.append(int(row[5]) / 1e6); bp.append(float(row[1]))
lo, hi = bt[0], bt[-1]


def px(t):
    i = bisect.bisect_right(bt, t) - 1
    return bp[i] if i >= 0 else None


ms = [m for m in load_markets() if m["open"] > lo + 5 and m["close"] < hi]
print(len(ms), "markets on the Binance day")
D = (0.0, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60)
LAT = (0.0, 0.005, 0.01, 0.02, 0.03, 0.05, 0.07, 0.1, 0.15, 0.3)
EV = {}
for theta in (1.0, 2.0, 3.0):
    shift = {d: [] for d in D}
    pnl = {L: [] for L in LAT}
    events = 0
    for m in ms:
        tr = m["trades"]
        yt = [t for t, s, p, n in tr if s == "yes"]; yp = [p for t, s, p, n in tr if s == "yes"]
        nt = [t for t, s, p, n in tr if s == "no"]; np_ = [p for t, s, p, n in tr if s == "no"]
        ys = [n for t, s, p, n in tr if s == "yes"]; ns = [n for t, s, p, n in tr if s == "no"]

        def quote(x):
            i = bisect.bisect_right(yt, x) - 1; j = bisect.bisect_right(nt, x) - 1
            if i < 0 or j < 0 or x - yt[i] > 5 or x - nt[j] > 5:
                return None
            return np_[j], yp[i]

        i0 = bisect.bisect_left(bt, m["open"] + 5); i1 = bisect.bisect_left(bt, m["close"] - 70)
        last = 0
        for k in range(i0, i1):
            e = bt[k]
            if e - last < 2:
                continue
            p0 = px(e - 0.5)
            mv = math.log(bp[k] / p0) * 1e4
            if abs(mv) < theta:
                continue
            last = e
            q0 = quote(e)
            if not q0 or not (0.1 <= sum(q0) / 2 <= 0.9):
                continue
            sgn = 1 if mv > 0 else -1
            rows = [quote(e + d) for d in D]
            end = quote(e + 60)
            if None in rows or not end:
                continue
            events += 1
            for d, r in zip(D, rows):
                shift[d].append(sgn * (sum(r) / 2 - sum(q0) / 2) * 100)
            val = sum(end) / 2 if sgn > 0 else 1 - sum(end) / 2
            ts_, ps_ = (yt, yp) if sgn > 0 else (nt, np_)
            sizes_ = ys if sgn > 0 else ns
            for L in LAT:
                # the price someone actually paid on our side, first trade at or after we'd arrive
                i = bisect.bisect_left(ts_, e + L)
                if i >= len(ts_) or ts_[i] - (e + L) > 0.5:
                    continue
                price = ps_[i] if sgn > 0 else 1 - ps_[i]
                # contracts that traded at that price or better in the next 200ms
                vol = 0.0
                j = i
                while j < len(ts_) and ts_[j] <= ts_[i] + 0.2:
                    pj = ps_[j] if sgn > 0 else 1 - ps_[j]
                    if pj <= price + 1e-9:
                        vol += sizes_[j]
                    j += 1
                pnl[L].append(((val - price - 0.07 * price * (1 - price)) * 100, vol, m["ticker"]))
    EV[theta] = pnl
    print(f"\nbitcoin moved {theta:.0f}bp+ within 0.5s: {events} times in {len(ms)} markets ({events / len(ms) * 96:.0f}/day)")
    print("  Kalshi mid shift (cents, in the move's direction):",
          "  ".join(f"{d:g}s:{sum(v) / len(v):+.2f}" for d, v in shift.items() if v))
    print("  chaser profit per contract after fee, at the price actually paid on arrival:")
    for L, v in pnl.items():
        if v:
            vols = sorted(x[1] for x in v)
            print(f"    {L * 1000:5.0f}ms: {sum(x[0] for x in v) / len(v):+.2f}c  (n={len(v)}, "
                  f"median {vols[len(vols) // 2]:.0f} contracts traded at that price within 200ms)")


# ---- dollars per month for a bot that lands L ms after the Binance print ----
import random
def monthly(theta, L, share=0.25, cap=100):
    """Our fills: a quarter of what traded at that price in the next 200ms, at most 100 contracts."""
    rows = EV[theta][L]
    per_mkt = {}
    for edge, vol, tk in rows:
        n = min(cap, share * vol)
        per_mkt[tk] = per_mkt.get(tk, 0) + edge / 100 * n
    keys = list(per_mkt)
    vals = [per_mkt[k] for k in keys] + [0.0] * (len(ms) - len(keys))
    days = len(ms) / 96
    est = sum(vals) / days * 30
    boots = []
    rnd = random.Random(1)
    for _ in range(400):
        b = [vals[rnd.randrange(len(vals))] for _ in vals]
        boots.append(sum(b) / days * 30)
    boots.sort()
    return est, boots[20], boots[380]

print("\n$ per month (90% range), trading every move of at least X basis points:")
for L in (0.0, 0.005, 0.01, 0.02, 0.03, 0.05, 0.1):
    cells = []
    for theta in (1.0, 2.0, 3.0):
        e, a, b = monthly(theta, L)
        cells.append(f"{theta:.0f}bp+: ${e:+7.0f} (${a:+.0f} to ${b:+.0f})")
    print(f"  lands {L * 1000:4.0f}ms after Binance:  " + "   ".join(cells))

if "--by-day" in sys.argv:
    print("\nby day ($ per day, lands 20ms after the print):")
    for theta in (2.0, 3.0):
        days_ = {}
        for edge, vol, tk in EV[theta][0.02]:
            day = tk.split("-")[1][:7]
            days_[day] = days_.get(day, 0) + edge / 100 * min(100, 0.25 * vol)
        print(f"  {theta:.0f}bp+:", "  ".join(f"{d}: ${v:+.0f}" for d, v in sorted(days_.items())))
