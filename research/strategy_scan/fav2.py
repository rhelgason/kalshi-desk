import sys, math, numpy as np, pandas as pd
S = sys.argv[1]
df = pd.read_pickle(f"{S}/rows.pkl")
fee = lambda p: 0.07 * p * (1 - p) + 0.0005
def run(lo, hi, wl, wh, coins, start, end, minvol=0, step=2):
    d = df[(df.day >= start) & (df.day <= end) & (df.left > wl) & (df.left <= wh) & df.coin.isin(coins) & (df.vol >= minvol)]
    if step == 2: d = d[(d.t // 60) % 2 == 0]
    yes = (d.mid >= 0.5) & (d.ask >= lo) & (d.ask <= hi) & (d.spread <= 0.02)
    no = (d.mid < 0.5) & (1 - d.bid >= lo) & (1 - d.bid <= hi) & (d.spread <= 0.02)
    d = d[yes | no].copy(); d["side_yes"] = yes[yes | no]; d = d.drop_duplicates("ticker")
    px = np.where(d.side_yes, d.ask, 1 - d.bid); win = np.where(d.side_yes, d.y == 1, d.y == 0)
    d["roi"] = (win - px - fee(px)) / (px + fee(px))
    daily = d.groupby("day").roi.sum()
    return len(d), d.roi.mean(), daily.mean() / daily.std() * math.sqrt(len(daily))
print("median contracts traded per minute, by coin:", df[df.day >= "2026-09-23"].groupby("coin").vol.median().round(0).to_dict())
for coins in (["BTC"], ["ETH"], ["SOL"], ["XRP"], ["DOGE"], ["BTC", "ETH"], ["BTC", "ETH", "SOL", "XRP", "DOGE"]):
    for mv in (0, 20, 50):
        for lo, wl, wh in ((0.92, 5, 9), (0.90, 4, 8)):
            tr = run(lo, 0.99, wl, wh, coins, "2026-07-25", "2026-09-22", mv); te = run(lo, 0.99, wl, wh, coins, "2026-09-23", "2026-10-22", mv)
            print(f"{'+'.join(coins):22} vol>={mv:2} {lo}-0.99 left {wl}-{wh}: train n={tr[0]:5} roi {tr[1]:+.4f} t {tr[2]:5.2f} | test n={te[0]:5} roi {te[1]:+.4f} t {te[2]:5.2f}")
