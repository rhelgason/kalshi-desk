# Taker version: when someone lifted the ask on a side, would we (with the index LAT s earlier) have wanted it too?
import sys, os, math, gzip, json
from collections import defaultdict
sys.argv = [sys.argv[0], sys.argv[1], sys.argv[2], "--calibrate"]
src = open("research/fast_coco/buzzer.py").read().split("EDGES = ")[0]
exec(src)
fee = lambda p: math.ceil(0.07 * p * (1 - p) * 100) / 100   # per contract, rounded up per 1-contract order (harsh)
out = defaultdict(lambda: [0.0, 0.0, 0])
for coin, name in COINS.items():
    v = load_index(name); lo_t, hi_t = min(v), max(v)
    with gzip.open(os.path.join(TAPE, f"KX{coin}15M.jsonl.gz"), "rt") as f:
        for line in f:
            try: m = json.loads(line)
            except json.JSONDecodeError: continue
            close = m["close"]
            if not (lo_t + 2000 < close < hi_t): continue
            r1 = [math.log(v[s] / v[s - 1]) for s in range(close - 660, close - 60) if v.get(s) and v.get(s - 1)]
            if len(r1) < 300: continue
            sig = max((sum(x * x for x in r1) / len(r1)) ** 0.5, 1e-6)
            seen = set()
            for t, yp, n, taker in m["t"]:
                left = close - t
                if not (0 < left <= 60): continue
                side, p = (taker, yp if taker == "yes" else round(1 - yp, 4))   # taker bought `side` at p
                if not (0.5 <= p <= 0.99): continue
                py = odds(v, close, int(math.floor(t - LAT)), sig)
                if py is None: continue
                fair = py if side == "yes" else 1 - py
                for e in (0.02, 0.04, 0.08):
                    if fair - p >= e and (e, m["ticker"]) not in seen:
                        seen.add((e, m["ticker"]))   # one $10 buy per market at the first chance
                        q = 10 / p
                        o = out[(e, "0-30s" if left <= 30 else "30-60s")]
                        o[0] += q * ((side == m["result"]) - p - fee(p)); o[1] += 10; o[2] += 1
for k in sorted(out):
    a = out[k]; print(f"take when odds beat the ask by {k[0]*100:.0f}c+, {k[1]}: {a[2]:5d} bets, {a[0]/a[1]*100:+6.2f}c per $1 after fees")
