"""Kalshi's 15-minute commodity markets (gold, oil, silver...) on Sadie's rules, no price check (2026-11-09).

The coins' replay (hourly_check.sadie: a look every 120 s, 92-99.5c favorites, one tick over the side's last price,
110 s bids, harsh fills, $10 a market) by minutes left, by half, by week and by price. There's no free 1-second gold
or oil price to check the favorite against, so this is Sadie before the coin check (+1.23c per $1 on the coins).
Tape from tape.py:
    python research/fast_coco/tape.py 60 15 data/tape_cmdty KXGOLD15M KXWTI15M KXSILVER15M
    python research/fast_coco/cmdty_check.py data/tape_cmdty KXGOLD15M KXWTI15M KXSILVER15M
"""
import math, os, sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from hourly_check import markets, sadie  # noqa: E402

WINDOWS = ((120, 300), (300, 540), (540, 840))


def show(label, rs):
    if not rs:
        print(f"  {label:26s} no bets")
        return
    rs = sorted(rs, key=lambda r: r["close"])
    c = lambda xs: sum(r["pnl"] for r in xs) / sum(r["spent"] for r in xs) * 100 if xs else float("nan")
    half = rs[len(rs) // 2]["close"]
    days = defaultdict(lambda: [0.0, 0.0])
    for r in rs:
        d = days[r["close"] // 86400]; d[0] += r["pnl"]; d[1] += r["spent"]
    v = [p / s for p, s in days.values()]
    mu = sum(v) / len(v); sd = (sum((x - mu) ** 2 for x in v) / max(1, len(v) - 1)) ** 0.5
    t = mu / sd * math.sqrt(len(v)) if sd else 0
    lost = sum(r["pnl"] < 0 for r in rs)
    print(f"  {label:26s} {len(rs):5d} bets  lost {lost:3d} ({lost/len(rs)*100:4.1f}%)  {c(rs):+6.2f}c per $1"
          f"  halves {c([r for r in rs if r['close'] < half]):+6.2f} / {c([r for r in rs if r['close'] >= half]):+6.2f}"
          f"  days up {sum(x > 0 for x in v)}/{len(v)}  t {t:+4.1f}")


def main():
    D, SERIES = sys.argv[1], sys.argv[2:]
    for s in SERIES:
        path = os.path.join(D, f"{s}.jsonl.gz")
        if not os.path.exists(path):
            continue
        rows = []
        for m in markets(path):
            if not m["t"] or m.get("result") not in ("yes", "no"):
                continue
            for a, b in WINDOWS:
                r = sadie(m, a, b)
                if r:
                    side, spent, got, at, price = r
                    rows.append({"w": (a, b), "close": m["close"], "price": price, "spent": spent,
                                 "pnl": (got if side == m["result"] else 0) - spent})
        if not rows:
            print(s, "no bets")
            continue
        day = lambda x: datetime.fromtimestamp(x, timezone.utc).strftime("%b %d")
        print(f"{s}: {day(min(r['close'] for r in rows))} - {day(max(r['close'] for r in rows))}, $10 a market")
        for a, b in WINDOWS:
            show(f"{a // 60}-{b // 60} min left", [r for r in rows if r["w"] == (a, b)])
        sadies = [r for r in rows if r["w"] == (300, 540)]
        for lo, hi in ((0.92, 0.95), (0.95, 0.97), (0.97, 1.0)):
            show(f"  5-9 min, {lo*100:.0f}-{hi*100:.0f}c", [r for r in sadies if lo <= r["price"] < hi])
        weeks = defaultdict(list)
        for r in sadies:
            weeks[datetime.fromtimestamp(r["close"], timezone.utc).strftime("%G-W%V")].append(r)
        print("  5-9 min by week: " + "  ".join(
            f"{w[-3:]} {sum(r['pnl'] for r in rs) / sum(r['spent'] for r in rs) * 100:+.1f}c"
            for w, rs in sorted(weeks.items())))


if __name__ == "__main__":
    main()
