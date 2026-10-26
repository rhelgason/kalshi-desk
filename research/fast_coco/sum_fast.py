"""Summarize replay_fast.py: per $1, fill rate, halves, coins, pulls, and a compounding $87.63 bankroll.
    python sum_fast.py RESULTS.json [SPLIT_DATE]"""
import json, math, statistics as st, sys
from collections import defaultdict
from datetime import datetime, timezone

R = json.load(open(sys.argv[1]))
R.sort(key=lambda r: r["close"])
split = sys.argv[2] if len(sys.argv) > 2 else None
day = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")
if not split:
    split = day(R[len(R) // 2]["close"])
bots = [k for k in R[0] if isinstance(R[0][k], dict)]
days = len({day(r["close"]) for r in R})


def pnl(x, result):
    return (x["ct"] if x["side"] == result else 0.0) - x["inv"]


def stats(rows, b):
    rets, inv, tot, filled = [], 0.0, 0.0, 0
    for r in rows:
        x = r[b]
        if x["inv"] > 0:
            p = pnl(x, r["result"]); rets.append(p / x["inv"]); inv += x["inv"]; tot += p; filled += 1
    if not rets:
        return None
    se = st.pstdev(rets) / math.sqrt(len(rets)) if len(rets) > 1 else 1
    return {"n": filled, "fill": filled / len(rows), "per1": tot / inv * 100, "t": st.mean(rets) / se,
            "lost": sum(1 for x in rets if x < 0) / len(rets) * 100, "per_market_c": tot / len(rows) * 100 / 10}


def line(name, s):
    if not s:
        return f"  {name:10} no bets"
    return (f"  {name:10} bets {s['n']:6d}  filled {s['fill']*100:5.1f}% of markets  lost {s['lost']:5.2f}%  "
            f"per$1 {s['per1']:+6.3f}c  t {s['t']:+5.2f}")


print(f"{len(R)} markets, {days} days, coins {sorted({r['coin'] for r in R})}; halves split at {split}\n")
for label, rows in (("ALL", R), (f"FIRST HALF (< {split})", [r for r in R if day(r["close"]) < split]),
                    (f"SECOND HALF (>= {split})", [r for r in R if day(r["close"]) >= split])):
    print(label)
    for b in bots:
        print(line(b, stats(rows, b)))
    print()

print("By coin (all days): twin vs the no-pull fast bot vs K1.0L2")
for coin in sorted({r["coin"] for r in R}):
    rows = [r for r in R if r["coin"] == coin]
    for b in ("twin", "none", "K1.0L2"):
        print(line(f"{coin} {b}", stats(rows, b)))

print("\nWhat pulling did (pulled bids the tape would have filled, settled anyway):")
for b in bots:
    if b in ("twin", "none"):
        continue
    gc = sum(r[b]["gcost"] for r in R); gp = sum((r[b]["gct"] if r[b]["gside"] == r["result"] else 0) - r[b]["gcost"]
                                              for r in R if r[b]["gcost"] > 0)
    pulls = sum(r[b]["pulls"] for r in R)
    print(f"  {b:8} pulls {pulls:6d}  would-have-filled ${gc:9.2f}  their P&L if kept {gp:+8.2f}  "
          f"({gp / gc * 100 if gc else 0:+.2f}c per $1)")

print("\nA $87.63 bankroll, 3% a bet, $10 cap (markets closing together share it), each half and all:")
for label, rows in (("all", R), ("first half", [r for r in R if day(r["close"]) < split]),
                    ("second half", [r for r in R if day(r["close"]) >= split])):
    out = []
    for b in bots:
        B = 87.63
        groups = defaultdict(list)
        for r in rows:
            groups[r["close"]].append(r)
        for t in sorted(groups):
            stake = min(0.03 * B, 10.0)
            delta = 0.0
            for r in groups[t]:
                x = r[b]
                if x["inv"] > 0:
                    frac = x["inv"] / 10.0
                    delta += frac * stake * (pnl(x, r["result"]) / x["inv"])
            B += delta
        out.append(f"{b} ${B:,.0f}")
    print(f"  {label:11} " + "  ".join(out))
