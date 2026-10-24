"""
30-day outcomes from RECENT days only (the edge has been shrinking), for the twin as the
trade tape suggests (+0.35% on every price) and if her edge halves again (+0.85%).

    python recent.py out/bets_twin_1.csv.gz [days=60]
"""
import sys
import numpy as np
import pandas as pd
from sim import rows_of, run_pool

df = pd.read_csv(sys.argv[1])
days = int(sys.argv[2]) if len(sys.argv) > 2 else 60
recent = df[df.day >= sorted(df.day.unique())[-days]].copy()
rng = np.random.default_rng(3)
out = []
for label, bump in (("tape-adjusted", 1.0035), ("edge halves again", 1.0085)):
    d = recent.copy()
    d["price"] = (d.price * bump).clip(upper=0.999)
    edge = ((d.won.astype(float) - d.price) / d.price).mean() * 100
    by_day = [rows_of(g) for _, g in d.groupby("day")]
    for start, pct in [(100, 0.01), (250, 0.01), (500, 0.005), (500, 0.01), (1000, 0.01), (1000, 0.02), (2500, 0.01)]:
        ends, dds = [], []
        for _ in range(2000):
            sample = []
            for i, k in enumerate(rng.choice(len(by_day), 30)):
                rows = by_day[k]
                shift = i * 86400 - rows[0][0] + 1_800_000_000
                sample += [(t + shift, c + shift, p, w, v, f"d{i:02d}") for t, c, p, w, v, _ in rows]
            r = run_pool(sample, start, pct=pct, maker=True)
            ends.append(r["ret"]); dds.append(r["max_dd"])
        e = np.array(ends)
        out.append({"twin": label, "edge c/$1": round(edge, 2), "start": start, "bet": f"{pct*100:g}%",
                    "chance of a losing month": f"{(e < 0).mean()*100:.0f}%", "bad month (5%)": f"{np.percentile(e, 5)*100:.1f}%",
                    "typical": f"{np.median(e)*100:.1f}%", "good month (95%)": f"{np.percentile(e, 95)*100:.1f}%",
                    "typical $": round(np.median(e) * start), "typical worst dip": f"{np.median(dds)*100:.0f}%"})
print(f"last {days} days: {recent.day.min()} to {recent.day.max()}, {len(recent)} bets")
print(pd.DataFrame(out).to_markdown(index=False))
