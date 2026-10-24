"""
Scan thousands of rule-based strategies over the stored 15-minute crypto markets.

Every strategy: at most one bet per market, the first minute its rule fires; pays the
ask (taker) plus Kalshi's 7% x P x (1-P) fee; a $1 contract pays $1 if right.
Periods: TRAIN = the 60 days before the test, TEST = the last 30 days.
Scores are per dollar staked; luck is judged on daily totals (bets in the same window
win or lose together), as a t-statistic.
"""
import sys, math, itertools, time
import numpy as np, pandas as pd

S = sys.argv[1]
DELAY = int(sys.argv[2]) if len(sys.argv) > 2 else 0  # 1 = fill at the next minute's quote
df = pd.read_pickle(f"{S}/rows.pkl")
TEST_START, TEST_END = "2026-09-23", "2026-10-22"
TRAIN_START = "2026-07-25"
df = df[(df.day >= TRAIN_START) & (df.day <= TEST_END)].reset_index(drop=True)
df["period"] = np.where(df.day >= TEST_START, "test", "train")

g = df.groupby("ticker", sort=False)
if DELAY:
    df["ask_f"], df["bid_f"] = g.ask.shift(-DELAY), g.bid.shift(-DELAY)
else:
    df["ask_f"], df["bid_f"] = df.ask, df.bid
df = df[df.ask_f.notna()].reset_index(drop=True)

cost_yes = df.ask_f.values
cost_no = 1 - df.bid_f.values
fee = lambda p: 0.07 * p * (1 - p) + 0.0005  # + rounding to the cent on a ~20-contract order
left = df.left.values
coin = df.coin.values
y = df.y.values
WIN = {"late": (0.5, 5), "mid": (5, 10), "early": (10, 14.6), "any": (0.5, 14.6)}
FINE = [(0.5, 2), (2, 4), (4, 6), (6, 8), (8, 10), (10, 12), (12, 14.6)]

def inwin(w): return (left > w[0]) & (left <= w[1])

results = []
def evaluate(name, fam, mask_yes, mask_no, extra=None):
    """mask_yes/mask_no: rows where the rule says buy YES / NO. First firing per market wins."""
    for cs in ["ALL", "BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "HYPE"]:
        cm = np.ones(len(df), bool) if cs == "ALL" else coin == cs
        my, mn = mask_yes & cm, mask_no & cm & ~mask_yes
        sel = np.flatnonzero(my | mn)
        if len(sel) < 30: continue
        sub = df.iloc[sel][["ticker", "day", "period", "coin"]].copy()
        side_yes = my[sel]
        px = np.where(side_yes, cost_yes[sel], cost_no[sel])
        ok = (px > 0.01) & (px < 0.99)
        sub = sub[ok]; side_yes = side_yes[ok]; px = px[ok]
        first = ~sub.ticker.duplicated().values
        sub = sub[first]; side_yes = side_yes[first]; px = px[first]
        win = np.where(side_yes, y[sub.index.values] == 1, y[sub.index.values] == 0)
        f = fee(px)
        sub["roi"] = (win - px - f) / (px + f)
        sub["win"] = win; sub["px"] = px
        row = {"name": name, "family": fam, "coins": cs, **(extra or {})}
        for per in ("train", "test"):
            s = sub[sub.period == per]
            n = len(s)
            row[f"{per}_n"] = n
            if n == 0:
                row.update({f"{per}_roi": np.nan, f"{per}_t": np.nan, f"{per}_win": np.nan, f"{per}_px": np.nan,
                            f"{per}_days": 0, f"{per}_perday": 0}); continue
            daily = s.groupby("day").roi.sum()
            days = 60 if per == "train" else 30
            dv = daily.reindex(sorted(set(daily.index)), fill_value=0)
            sd = dv.std(ddof=1) if len(dv) > 1 else np.nan
            row[f"{per}_roi"] = s.roi.mean()
            row[f"{per}_t"] = dv.mean() / sd * math.sqrt(len(dv)) if sd and sd > 0 else np.nan
            row[f"{per}_win"] = s.win.mean()
            row[f"{per}_px"] = s.px.mean()
            row[f"{per}_days"] = len(dv)
            row[f"{per}_perday"] = n / days
            row[f"{per}_sum"] = s.roi.sum()   # $ profit if every bet were $1
        results.append(row)

t0 = time.time()
mid = df.mid.values
fav_yes = mid >= 0.5
# F1 favorites and F2 long shots by price band and time left
for w in FINE + [WIN["late"], WIN["mid"], WIN["early"]]:
    iw = inwin(w)
    for lo, hi in [(a, a + d) for a in np.arange(0.5, 0.96, 0.05) for d in (0.05, 0.10) if a + d <= 1.0001]:
        evaluate(f"fav {lo:.2f}-{hi:.2f} left {w}", "favorite",
                 iw & fav_yes & (cost_yes >= lo) & (cost_yes < hi), iw & ~fav_yes & (cost_no >= lo) & (cost_no < hi),
                 {"lo": lo, "hi": hi, "w": str(w)})
    for lo, hi in [(0.02, 0.06), (0.06, 0.12), (0.12, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5)]:
        evaluate(f"longshot {lo:.2f}-{hi:.2f} left {w}", "longshot",
                 iw & ~fav_yes & (cost_yes >= lo) & (cost_yes < hi), iw & fav_yes & (cost_no >= lo) & (cost_no < hi),
                 {"lo": lo, "hi": hi, "w": str(w)})
print("F1/F2", len(results), f"{time.time()-t0:.0f}s")

# F3 Kalshi price momentum / reversion
band = lambda c: (c >= 0.1) & (c <= 0.9)
for k in (1, 2, 3, 5):
    dm = df[f"dmid{k}"].values
    for d in (0.03, 0.05, 0.08, 0.12, 0.2):
        for wn in ("late", "mid", "early", "any"):
            iw = inwin(WIN[wn])
            evaluate(f"kmom k{k} d{d} {wn}", "kalshi_momentum", iw & (dm >= d) & band(cost_yes), iw & (dm <= -d) & band(cost_no),
                     {"k": k, "d": d, "w": wn})
            evaluate(f"krev k{k} d{d} {wn}", "kalshi_reversion", iw & (dm <= -d) & band(cost_yes), iw & (dm >= d) & band(cost_no),
                     {"k": k, "d": d, "w": wn})
print("F3", len(results), f"{time.time()-t0:.0f}s")

# F4 model edge (spot vs strike, realized vol), F8 early breakout by z
from math import erf
verf = np.vectorize(erf)
zz = df.z.values
for s in (0.7, 1.0, 1.4):
    model = np.where(np.isnan(zz), np.nan, 0.5 * (1 + verf(np.nan_to_num(zz) / s / math.sqrt(2))))
    for e in (0.02, 0.04, 0.06, 0.08, 0.12, 0.16):
        ey = model - cost_yes - fee(cost_yes)
        en = (1 - model) - cost_no - fee(cost_no)
        for wn in ("late", "mid", "early", "any"):
            iw = inwin(WIN[wn])
            evaluate(f"model s{s} e{e} {wn}", "model_edge", iw & (ey >= e) & band(cost_yes), iw & (en >= e) & band(cost_no),
                     {"s": s, "e": e, "w": wn})
for q in (0.5, 1.0, 1.5, 2.0):
    for cap in (0.7, 0.8, 0.9):
        for wn in ("early", "mid"):
            iw = inwin(WIN[wn])
            evaluate(f"zbreak q{q} cap{cap} {wn}", "z_breakout", iw & (zz >= q) & (cost_yes <= cap), iw & (zz <= -q) & (cost_no <= cap),
                     {"q": q, "cap": cap, "w": wn})
print("F4/F8", len(results), f"{time.time()-t0:.0f}s")

# F5 spot momentum / reversion in sigma units
sd1 = df.sd1.values
for k in (1, 3, 5):
    zr = df[f"sret{k}"].values / (sd1 * math.sqrt(k))
    for q in (1.0, 1.5, 2.0, 3.0):
        for wn in ("late", "mid", "early", "any"):
            iw = inwin(WIN[wn])
            evaluate(f"smom k{k} q{q} {wn}", "spot_momentum", iw & (zr >= q) & band(cost_yes), iw & (zr <= -q) & band(cost_no),
                     {"k": k, "q": q, "w": wn})
            evaluate(f"srev k{k} q{q} {wn}", "spot_reversion", iw & (zr <= -q) & band(cost_yes), iw & (zr >= q) & band(cost_no),
                     {"k": k, "q": q, "w": wn})
print("F5", len(results), f"{time.time()-t0:.0f}s")

# F6 bitcoin leads the other coins
notbtc = coin != "BTC"
for k in (1, 2, 3):
    bd = df[f"btc_d{k}"].values
    own = df[f"dmid{k}"].values
    for d in (0.05, 0.08, 0.12, 0.2):
        for lag in (0.5, 0.25):
            for wn in ("late", "mid", "early", "any"):
                iw = inwin(WIN[wn]) & notbtc
                evaluate(f"btclead k{k} d{d} lag{lag} {wn}", "btc_leads",
                         iw & (bd >= d) & (own < d * lag) & band(cost_yes), iw & (bd <= -d) & (own > -d * lag) & band(cost_no),
                         {"k": k, "d": d, "lag": lag, "w": wn})
print("F6", len(results), f"{time.time()-t0:.0f}s")

# F9 volume spikes (relative to that coin's typical minute), follow or fade; F7 big one-minute jumps faded
vq = df.groupby("coin").vol_prev.transform(lambda v: v.rank(pct=True)).values
d1 = df.dmid1.values
for p in (0.9, 0.97):
    for wn in ("late", "mid", "early"):
        iw = inwin(WIN[wn]) & (vq >= p)
        evaluate(f"volspike p{p} follow {wn}", "volume_follow", iw & (d1 > 0) & band(cost_yes), iw & (d1 < 0) & band(cost_no), {"p": p, "w": wn})
        evaluate(f"volspike p{p} fade {wn}", "volume_fade", iw & (d1 < 0) & band(cost_yes), iw & (d1 > 0) & band(cost_no), {"p": p, "w": wn})
for d in (0.15, 0.25, 0.35):
    for wn in ("late", "mid", "early"):
        iw = inwin(WIN[wn])
        evaluate(f"jumpfade d{d} {wn}", "jump_fade", iw & (d1 <= -d) & band(cost_yes), iw & (d1 >= d) & band(cost_no), {"d": d, "w": wn})
print("F7/F9", len(results), f"{time.time()-t0:.0f}s")

out = pd.DataFrame(results)
out.to_pickle(f"{S}/scan_d{DELAY}.pkl")
print(len(out), "strategy x coin combinations evaluated")
