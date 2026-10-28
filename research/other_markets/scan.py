"""Who makes money on Kalshi, market by market? (2026-10-27)

Every trade has a taker (who paid the price on offer) and a maker (whose resting order was hit). From the sampled
tape (sample_tape.py) and how each market settled, this adds up what each side earned per $1, after Kalshi's fees,
by series group x the price of the side they ended up holding x time left before trading stopped. A maker row is
roughly what a patient bot earns by resting bids at that price (if it gets filled like the average maker).
Each trade counts up to CAP contracts so a few whales don't decide a cell. Standard errors are clustered by market.
    python research/other_markets/scan.py data/other [SERIES...]      env CAP (200), MINMKTS (30)"""
import gzip, json, math, os, sys
from collections import defaultdict
from datetime import datetime, timezone

D = sys.argv[1]
ONLY = set(sys.argv[2:])
CAP, MINMKTS = float(os.environ.get("CAP", "200")), int(os.environ.get("MINMKTS", "30"))
GROUP = {"NFL/college football": ("KXNFLGAME", "KXNCAAFGAME"), "baseball": ("KXMLBGAME",), "basketball": ("KXNBAGAME",),
         "tennis": ("KXATPMATCH", "KXWTAMATCH", "KXATPCHALLENGERMATCH"),
         "weather (daily highs)": ("KXHIGHNY", "KXHIGHLAX", "KXHIGHCHI", "KXHIGHMIA", "KXHIGHAUS", "KXHIGHDEN"),
         "gold/oil/euro 15-min": ("KXGOLD15M", "KXWTI15M", "KXEURUSD15M"), "S&P/Nasdaq hourly": ("KXINXU", "KXNASDAQ100U"),
         "gas prices daily": ("KXAAAGASD",), "Trump mentions": ("KXTRUMPMENTION",), "Trump approval": ("KXTRUMPAPPROVE",),
         "Rotten Tomatoes": ("KXRT",)}
BANDS = [(0, .10), (.10, .30), (.30, .50), (.50, .70), (.70, .85), (.85, .92), (.92, .97), (.97, 1.0)]
TIMES = [(86400, 1e12, ">1 day"), (6 * 3600, 86400, "6h-1d"), (3600, 6 * 3600, "1-6h"), (900, 3600, "15m-1h"), (0, 900, "<15m")]
band = lambda p: next(i for i, (a, b) in enumerate(BANDS) if a <= p < b or (b == 1.0 and p >= a))
when = lambda left: next(i for i, (a, b, _) in enumerate(TIMES) if a <= left < b)

# cell -> market -> [pnl, spent]; plus the market's date for halves
cells = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
mday = {}
for fn in sorted(os.listdir(D)):
    if not fn.endswith(".jsonl.gz"):
        continue
    s = fn.split(".")[0]
    if ONLY and s not in ONLY:
        continue
    grp = next((g for g, ss in GROUP.items() if s in ss), s)
    with gzip.open(os.path.join(D, fn), "rt") as fh:
        for line in fh:
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not m["t"]:
                continue
            last = max(t[0] for t in m["t"])
            mday[m["ticker"]] = last
            mult = m.get("fee_mult") or 1
            maker_fee = "maker" in (m.get("fee_type") or "")
            for t, yp, n, taker, *_ in m["t"]:
                n = min(n, CAP)
                pt = yp if taker == "yes" else 1 - yp
                pm = 1 - pt
                ms = "no" if taker == "yes" else "yes"
                w = when(last - t)
                ft = 0.07 * mult * pt * (1 - pt)
                fm = 0.0175 * mult * pm * (1 - pm) if maker_fee else 0.0
                for role, side, p, fee in (("maker", ms, pm, fm), ("taker", taker, pt, ft)):
                    if not 0 < p < 1:
                        continue
                    c = cells[(grp, role, band(p), w)][m["ticker"]]
                    c[0] += n * ((side == m["result"]) - p - fee); c[1] += n * p


def summarize(markets):
    tk = sorted(markets, key=lambda k: mday[k])
    pnl = sum(markets[k][0] for k in tk); spent = sum(markets[k][1] for k in tk)
    if spent <= 0:
        return None
    r = pnl / spent
    se = math.sqrt(sum((markets[k][0] - r * markets[k][1]) ** 2 for k in tk)) / spent
    h = len(tk) // 2
    halves = [sum(markets[k][0] for k in part) / max(1e-9, sum(markets[k][1] for k in part)) for part in (tk[:h], tk[h:])]
    return r, se, len(tk), halves, spent


print("cents per $1 after fees (t = how many standard errors from zero, clustered by market). * = t > 2.5 and both halves > 0")
groups = sorted({k[0] for k in cells})
for g in groups:
    print(f"\n=== {g}")
    for role in ("maker", "taker"):
        rows = []
        for bi, (a, b) in enumerate(BANDS):
            for wi, (_, _, wl) in enumerate(TIMES):
                res = summarize(cells.get((g, role, bi, wi), {}))
                if not res or res[2] < MINMKTS:
                    continue
                r, se, nm, hv, spent = res
                t = r / se if se > 0 else 0
                star = "*" if t > 2.5 and min(hv) > 0 else " "
                rows.append(f"  {star} {role} {a*100:3.0f}-{b*100:3.0f}c {wl:>7}: {r*100:+6.2f}c (t {t:+5.1f}) halves "
                            f"{hv[0]*100:+6.2f}/{hv[1]*100:+6.2f}  {nm:4d} mkts ${spent:,.0f}")
        print("\n".join(rows))
