"""The final-minute test with the OFFICIAL index (index_history.py), against Kalshi's real trade tape (tape.py).

Kalshi settles on the average of the last 60 one-second index values. During that minute part of the average is
fixed; the rest is the current index plus noise. From what was known LAT seconds earlier we compute the odds; we
keep a resting bid at the best bid (the last price a seller hit on that side) only while the odds beat it by EDGE.
Fills are harsh: a trade AT our price gives QUEUE of it, a trade THROUGH it fills us in full. $10 a market.
    python buzzer.py TAPE_DIR INDEX_DIR [--calibrate]"""
import gzip, json, math, os, sys
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone

TAPE, IDX = sys.argv[1], sys.argv[2]
CAL = "--calibrate" in sys.argv
CAP, QUEUE, LAT = 10.0, 0.3, float(os.environ.get("LAT", "1.0"))
SWEEP = os.environ.get("SWEEP", "full")   # "share": a trade through our price fills only QUEUE of it too
COINS_ALL = {"ETH": "ETHUSD_RTI", "SOL": "SOLUSD_RTI", "XRP": "XRPUSD_RTI"}
COINS = {c: COINS_ALL[c] for c in os.environ.get("COINS", "ETH,SOL,XRP").split(",")}
Phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))


def load_index(name):
    v = {}
    with gzip.open(os.path.join(IDX, f"{name}.jsonl.gz"), "rt") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            v.update({int(k): x for k, x in d["v"].items()})
    return v


def odds(v, close, known_at, sig):
    """P(yes) from what the index said up to second `known_at` (exclusive)."""
    k = max(0, min(60, known_at - (close - 60)))
    fixed = [v.get(s) for s in range(close - 60, close - 60 + k)]
    now = v.get(known_at - 1)
    strike = [v.get(s) for s in range(close - 960, close - 900)]
    if now is None or None in fixed or None in strike:
        return None
    strike = sum(strike) / 60
    r = 60 - k
    proj = (sum(fixed) + now * r) / 60
    if r == 0:
        return 1.0 if proj >= strike else 0.0
    sd = sig * math.sqrt(r * (r + 1) * (2 * r + 1) / 6) / 60     # the unfixed part of the average, relative
    if known_at < close - 60:                                     # before the window: drift until it opens too
        sd = math.sqrt(sd ** 2 + sig ** 2 * (close - 60 - known_at) )
    return Phi(math.log(proj / strike) / max(sd, 1e-9))


EDGES = (0.0, 0.01, 0.02, 0.04)
WINS = (60, 30)
res = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0, 0]))
cal = defaultdict(lambda: [0.0, 0.0, 0.0])
for coin, name in COINS.items():
    v = load_index(name)
    lo_t, hi_t = min(v), max(v)
    with gzip.open(os.path.join(TAPE, f"KX{coin}15M.jsonl.gz"), "rt") as f:
        for line in f:
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            close = m["close"]
            if not (lo_t + 2000 < close < hi_t):
                continue
            r1 = [math.log(v[s] / v[s - 1]) for s in range(close - 660, close - 60) if v.get(s) and v.get(s - 1)]
            if len(r1) < 300:
                continue
            sig = max((sum(x * x for x in r1) / len(r1)) ** 0.5, 1e-6)
            day = datetime.fromtimestamp(close - 7 * 3600, timezone.utc).strftime("%Y-%m-%d")
            trades = m["t"]
            times = [t[0] for t in trades]
            best = {"yes": [], "no": []}   # (time, price) each time a seller hit that side = that side's best bid
            for t, yp, n, taker in trades:
                side, p = (("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp))
                best[side].append((t, p))
            bt = {s: [x[0] for x in best[s]] for s in best}
            cache = {}

            def fair_at(t):
                ka = int(math.floor(t - LAT))
                if ka not in cache:
                    cache[ka] = odds(v, close, ka, sig)
                return cache[ka]

            for t, yp, n, taker in trades:
                left = close - t
                if not (0 < left <= 60):
                    continue
                py = fair_at(t)
                if py is None:
                    continue
                side, p = (("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp))
                fair = py if side == "yes" else 1 - py
                if CAL and p >= 0.5:
                    b = (min(int((fair - p) * 100 // 2), 5) if fair >= p else max(int((fair - p) * 100 // 2), -6),
                         "0-30s" if left <= 30 else "30-60s")
                    c = cal[b]; c[0] += n * ((side == m["result"]) - p); c[1] += n * p; c[2] += 1
            if CAL:
                continue
            for edge in EDGES:
                for win in WINS:
                    spent = got = 0.0; held = None
                    for t, yp, n, taker in trades:
                        left = close - t
                        if not (0 < left <= win) or spent >= CAP:
                            continue
                        side, p = (("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp))
                        if held and side != held:
                            continue
                        i = bisect_right(bt[side], t - LAT) - 1   # the best bid we could see LAT seconds ago
                        if i < 0:
                            continue
                        bid = best[side][i][1]
                        py = fair_at(t)
                        if py is None or not (0.5 <= bid <= 0.995):
                            continue
                        fair = py if side == "yes" else 1 - py
                        if fair - bid < edge:
                            continue
                        q = (n if SWEEP == "full" else n * QUEUE) if p < bid - 1e-9 else n * QUEUE if abs(p - bid) < 1e-9 else 0
                        q = min(q, (CAP - spent) / bid)
                        if q >= 0.01:
                            spent += q * bid; got += q; held = side
                    if spent > 0:
                        pnl = (got if held == m["result"] else 0) - spent
                        a = res[(edge, win)][day]; a[0] += pnl; a[1] += spent; a[2] += 1; a[3] += pnl < 0
    print(coin, "done", file=sys.stderr, flush=True)

if CAL:
    print("Trades on the favorite side in the final minute: what buyers made per $1, by (official-index odds - price)")
    for tl in ("30-60s", "0-30s"):
        for b in sorted(k for k in cal if k[1] == tl):
            c = cal[b]
            print(f"  {tl} odds-price {b[0]*2:+3d}..{b[0]*2+2:+3d}c: {c[0]/c[1]*100:+6.2f}c per $1 ({c[2]:7.0f} trades)")
for key in sorted(res):
    days = res[key]; ds = sorted(days); half = ds[len(ds) // 2]
    tot = [sum(days[d][i] for d in ds) for i in range(4)]
    h = [sum(days[d][0] for d in ds if (d < half) == f) / max(1e-9, sum(days[d][1] for d in ds if (d < half) == f)) * 100 for f in (True, False)]
    l7 = sum(days[d][0] for d in ds[-7:]) / max(1e-9, sum(days[d][1] for d in ds[-7:])) * 100
    print(f"edge {key[0]*100:2.0f}c last {key[1]}s: {tot[2]:5d} bets ({tot[2]/len(ds):3.0f}/day) lost {tot[3]/tot[2]*100:4.1f}% "
          f"{tot[0]/tot[1]*100:+5.2f}c per $1 | halves {h[0]:+.2f} / {h[1]:+.2f} | last 7 days {l7:+.2f} | "
          f"{sum(1 for d in ds if days[d][0] > 0)}/{len(ds)} days up | ${tot[0]/len(ds):+.2f}/day at $10")
