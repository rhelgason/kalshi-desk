import sys, math, numpy as np, pandas as pd
S = sys.argv[1]
df = pd.read_pickle(f"{S}/rows.pkl")
fee = lambda p: 0.07 * p * (1 - p) + 0.0005
g = df.groupby("ticker", sort=False)
df["ask_n"], df["bid_n"] = g.ask.shift(-1), g.bid.shift(-1)
d = df[(df.coin == "BTC") & (df.day < "2026-07-25") & (df.left > 5) & (df.left <= 9) & ((df.t // 60) % 2 == 0) & (df.spread <= 0.02)]
yes = (d.ask >= 0.92) & (d.ask <= 0.99); no = (1 - d.bid >= 0.92) & (1 - d.bid <= 0.99)
d = d[yes | no].copy(); d["sy"] = yes[yes | no]; d = d.drop_duplicates("ticker")
lim = np.where(d.sy, d.ask, 1 - d.bid); nxt = np.where(d.sy, d.ask_n, 1 - d.bid_n)
ok = nxt <= lim + 1e-9          # fills only if the next minute's price is still at or under the limit
d = d[ok]; px = nxt[ok]
win = np.where(d.sy, d.y == 1, d.y == 0)
d["roi"] = (win - px - fee(px)) / (px + fee(px)); d["win"] = win
daily = d.groupby("day").roi.sum()
print(f"BTC Dec 10 - Jul 24 (never used to pick the rule): {len(d)} bets, win {d.win.mean():.3f}, {100*d.roi.mean():+.2f}c per $1, daily t {daily.mean()/daily.std()*math.sqrt(len(daily)):.2f}")
m = d.groupby(d.day.str[:7]).agg(n=("roi", "size"), roi=("roi", "mean"))
print("   " + "  ".join(f"{k}: {100*r.roi:+.2f}c" for k, r in m.iterrows()))
print(f"   months positive: {(m.roi > 0).sum()} of {len(m)}; $ on $10 bets: {10*d.roi.sum():+.0f}")
