"""How big should Sadie's rules bet, and should surer bets be bigger? (2026-11-02)

Uses every bet btc_check.py replayed (OUT=data/sadie_rows.json: 5 coins, Aug 24 - Oct 31, trade tape, harsh fills),
keeping the ones the coin check allows. Two questions:
  1. Does the coin check's "how sure" (its odds minus our price) say which bets earn more per $1?
  2. Pool replays from $80, in time order: each bet is a share of the pool (never more than the replay filled at that
     market, so bigger bets can't fill liquidity that wasn't there), all bets closing together share a window cap.
     Flat sizes vs bets scaled by sureness vs Kelly.
    python research/fast_coco/sizing.py data/sadie_rows.json"""
import json, math, sys
from collections import defaultdict

rows = [r for r in json.load(open(sys.argv[1])) if r["odds"] >= r["price"]]
rows.sort(key=lambda r: r["close"])
half = rows[len(rows) // 2]["close"]
for r in rows:
    r["r"] = r["pnl"] / r["spent"]
    r["edge"] = r["odds"] - r["price"]


def c(rs):
    s = sum(r["spent"] for r in rs)
    return sum(r["pnl"] for r in rs) / s * 100 if s else float("nan")


def show(label, rs):
    if rs:
        lost = sum(r["pnl"] < 0 for r in rs)
        print(f"  {label:22s} {len(rs):5d} bets  lost {lost/len(rs)*100:4.1f}%  {c(rs):+6.2f}c per $1  halves "
              f"{c([r for r in rs if r['close'] < half]):+6.2f} / {c([r for r in rs if r['close'] >= half]):+6.2f}")


print(f"1. Per $1 by how sure the coin check is ({len(rows)} bets)")
show("all", rows)
print(" coin-check odds minus our price:")
for lo, hi in ((0, 0.01), (0.01, 0.02), (0.02, 0.03), (0.03, 0.05), (0.05, 1)):
    show(f"+{lo*100:.0f} to +{hi*100:.0f}c", [r for r in rows if lo <= r["edge"] < hi])
print(" coin-check odds:")
for lo, hi in ((0.92, 0.97), (0.97, 0.99), (0.99, 0.995), (0.995, 0.999), (0.999, 1.01)):
    show(f"{lo*100:.1f} to {hi*100:.1f}%", [r for r in rows if lo <= r["odds"] < hi])

# Kelly's answer for one bet, from the replay itself: the share of the pool that grows it fastest
m1 = sum(r["r"] for r in rows) / len(rows)
m2 = sum(r["r"] ** 2 for r in rows) / len(rows)
print(f"\nKelly from the replay, if every bet were on its own: about {m1 / m2 * 100:.0f}% of the pool a bet")
win = defaultdict(list)
for r in rows:
    win[r["close"]].append(r)
same = sum(len(v) > 1 for v in win.values())
both = [v for v in win.values() if len(v) > 1]
together = sum(all(x["pnl"] < 0 for x in v) for v in both if any(x["pnl"] < 0 for x in v))
anyloss = sum(any(x["pnl"] < 0 for x in v) for v in both)
print(f"  ({same} of {len(win)} windows hold 2+ coins' bets; when one of those loses, every coin in it loses "
      f"{together} of {anyloss} times, so the window cap matters)")


def replay(size, cap):
    pool, peak, worst, low = 80.0, 80.0, 0.0, 80.0
    days = defaultdict(float)
    for close, bets in sorted(win.items()):
        stakes = [min(size(r) * pool, r["spent"]) for r in bets]
        total = sum(stakes)
        if total > cap * pool:
            stakes = [s * cap * pool / total for s in stakes]
        before = pool
        for r, s in zip(bets, stakes):
            if s >= 0.25:
                pool += s * r["r"]
        days[close // 86400] += pool - before
        peak = max(peak, pool); worst = max(worst, 1 - pool / peak); low = min(low, pool)
    return pool, worst, min(days.values()) if days else 0.0, low


print("\n2. Pool replays from $80 (bet = share of pool, at most what filled; window cap shared)")
print(f"  {'rule':40s} {'ends at':>9s} {'worst drop':>11s} {'worst day':>10s} {'lowest':>8s}")
schemes = [(f"flat {f*100:.0f}%, cap {f*4*100:.0f}%", (lambda r, f=f: f), f * 4) for f in (0.01, 0.02, 0.03, 0.05, 0.08)]
schemes += [
    ("3% x sureness (1% to 6%), cap 12%", lambda r: min(max(r["edge"] / 0.02, 0.33), 2) * 0.03, 0.12),
    ("3% x sureness (2% to 4%), cap 12%", lambda r: min(max(r["edge"] / 0.02, 0.67), 1.33) * 0.03, 0.12),
    ("3%, only bets 2c+ sure, cap 12%", lambda r: 0.03 if r["edge"] >= 0.02 else 0, 0.12),
    ("tenth-Kelly from coin odds, cap 12%", lambda r: max(r["edge"] / (1 - r["price"]), 0) * 0.1, 0.12),
    ("quarter-Kelly from coin odds, cap 25%", lambda r: max(r["edge"] / (1 - r["price"]), 0) * 0.25, 0.25),
]
for label, size, cap in schemes:
    end, worst, day, low = replay(size, cap)
    print(f"  {label:40s} ${end:8,.0f} {worst*100:10.1f}% ${day:+9,.0f} ${low:7,.0f}")
