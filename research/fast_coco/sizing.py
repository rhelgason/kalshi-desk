"""Compound a maker rule's per-market results (maker_bets.py) at different bet sizes, from $100.
Markets that close at the same moment share the bankroll (each gets FRACTION of it), so correlated losses hit together.
Each bet's return per $1 is taken from the $10 replay (fills smaller than $10 scale down: the bet is
FRACTION x bankroll x spent/10). Prints the end bankroll, worst day, deepest drawdown, and per half.
    python sizing.py BETS.json [BETS2.json ...]   (several files = rules run side by side, each with its own share)"""
import json, os, sys
from collections import defaultdict
from datetime import datetime, timezone

files = sys.argv[1:]
MAXBET = float(os.environ.get("MAXBET", "inf"))   # dollars per market: the book only holds so much
rows = []
for i, f in enumerate(files):
    for r in json.load(open(f)):
        r["rule"] = i; rows.append(r)
by = defaultdict(list)
for r in rows:
    by[r["close"]].append(r)
times = sorted(by)
day = lambda t: datetime.fromtimestamp(t - 7 * 3600, timezone.utc).strftime("%Y-%m-%d")
days = sorted({day(t) for t in times})
half = days[len(days) // 2]
print(f"{len(rows)} bets over {len(days)} days ({days[0]} .. {days[-1]}), {len(rows)/len(days):.0f} a day")
for frac in (0.01, 0.03, 0.05, 0.10, 0.20, 0.30):
    res = {}
    for label, sel in (("all", lambda d: True), ("1st half", lambda d: d < half), ("2nd half", lambda d: d >= half),
                       ("last 7d", lambda d: d >= days[-7])):
        B, peak, dd, worst, dayB, cur = 100.0, 100.0, 0.0, 0.0, 100.0, None
        for t in times:
            d = day(t)
            if not sel(d):
                continue
            if d != cur:
                if cur is not None:
                    worst = min(worst, B / dayB - 1) if dayB > 0 else -1
                cur, dayB = d, B
            stake = min(frac * B, MAXBET)
            B += sum(stake * r["spent"] / 10 * (r["pnl"] / r["spent"]) for r in by[t])
            B = max(B, 0.0)
            peak = max(peak, B); dd = min(dd, B / peak - 1)
        worst = min(worst, B / dayB - 1) if dayB > 0 else -1
        res[label] = (B, worst, dd)
    a = res["all"]
    print(f"  {frac*100:4.0f}% a bet: $100 -> ${a[0]:>10,.0f}  worst day {a[1]*100:+5.1f}%  deepest drop {a[2]*100:+5.1f}% | "
          f"1st half ${res['1st half'][0]:,.0f}, 2nd half ${res['2nd half'][0]:,.0f}, last 7 days ${res['last 7d'][0]:,.0f}")
