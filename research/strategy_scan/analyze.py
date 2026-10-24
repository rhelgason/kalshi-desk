import sys, numpy as np, pandas as pd
S = sys.argv[1]
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200); pd.set_option("display.max_colwidth", 48)
a = pd.read_pickle(f"{S}/scan_d0.pkl"); b = pd.read_pickle(f"{S}/scan_d1.pkl")
m = a.merge(b[["name", "coins", "train_t", "test_t", "train_roi", "test_roi"]], on=["name", "coins"], suffixes=("", "_d1"))
m = m[(m.train_n >= 60) & (m.test_n >= 30)]
print(len(m), "strategies with enough bets in both periods")
print(f"train t>2: {(m.train_t>2).mean():.1%}   test t>2: {(m.test_t>2).mean():.1%}   (pure chance ~2.3% each, less with fees)")
print("rank correlation train ROI vs test ROI:", round(m.train_roi.rank().corr(m.test_roi.rank()), 3))
print("\nBy family: share with positive ROI (train / test), median ROI per $ (train / test)")
print(m.groupby("family").agg(n=("name", "size"), pos_train=("train_roi", lambda s: (s > 0).mean()),
      pos_test=("test_roi", lambda s: (s > 0).mean()), med_train=("train_roi", "median"), med_test=("test_roi", "median")).round(3))
w = m[(m.train_t >= 2) & (m.train_t_d1 >= 1.5) & (m.train_n >= 100)]
print(f"\nTRAIN WINNERS (train t>=2, still t>=1.5 a minute late, 100+ bets): {len(w)}")
print(f"  of these, positive in TEST: {(w.test_roi>0).mean():.0%}; test t>2: {(w.test_t>2).mean():.0%}; median test ROI {w.test_roi.median():+.3f}")
cols = ["name", "coins", "train_n", "train_win", "train_px", "train_roi", "train_t", "train_t_d1", "test_n", "test_win", "test_roi", "test_t", "test_t_d1", "test_sum"]
print(w.sort_values("train_t", ascending=False)[cols].head(60).round(3).to_string())
print("\nHINDSIGHT: best in TEST alone (what you'd pick if you cheated)")
print(m.sort_values("test_t", ascending=False)[cols].head(25).round(3).to_string())
