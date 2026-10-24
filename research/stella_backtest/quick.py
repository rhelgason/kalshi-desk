"""Stella and the twin on whatever is in a data folder, by coin (no grid, no sizing): python quick.py data/ KXXRP15M,KXDOGE15M"""
import sys
import pandas as pd
from sim import Rule, bets, load, per_dollar, tstat

ms = load(sys.argv[1], sys.argv[2].split(","))
for label, r in (("Stella", Rule()), ("Stella instant", Rule(mode="taker0")), ("Twin +1", Rule(mode="maker"))):
    df = bets(ms, r)
    maker = r.mode == "maker"
    f = 0 if maker else 0.07 * df.price * (1 - df.price)
    roi = (df.won.astype(float) - df.price - f) / (df.price + f)
    for coin, g in df.groupby("coin"):
        rr = roi[g.index]
        print(f"{label:15s} {coin:5s} bets {len(g):5d} won {g.won.mean()*100:5.1f}% price {g.price.mean():.3f} "
              f"{rr.mean()*100:+.2f}c/$1 t {tstat(g, rr):+.2f}  by month " +
              " ".join(f"{m}:{v*100:+.2f}" for m, v in rr.groupby(g.month).mean().items()))
