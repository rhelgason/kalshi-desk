"""
How slow is Kalshi to react to bitcoin, and what's that worth to a fast bot?

For every second of every 15-minute market (Kalshi tape + Binance 1s prices):
  fair  = chance YES wins given where bitcoin is now (settlement = 60s average
          vs. the 60s average before the open; vol from the last 15 minutes)
  bid/ask/mid = Kalshi's quote rebuilt from the tape

1. Lead-lag: when fair value moves in second t, how much of that move shows up
   in Kalshi's mid over the next h seconds?
2. A simple fast bot: at second t, if fair - ask (after fee) > margin, buy at
   the ask L seconds later (our reaction time). Score by settlement and by the
   Kalshi mid 60s later (a less noisy read of the same edge).
"""
import bisect, math, sys
from statistics import NormalDist
from tapelib import Spot, load_markets, taker_fee

N = NormalDist()


def fair_series(m, spot):
    """Per-second fair P(YES) from bitcoin, keyed by unix second."""
    o, c = int(m["open"]), int(m["close"])
    pre = [spot.at(s) for s in range(o - 60, o)]
    if None in pre or o - 960 < spot.lo or c > spot.hi:
        return None
    K = sum(pre) / 60
    rets = [math.log(spot.at(s) / spot.at(s - 1)) for s in range(o - 900, o)]
    out = {}
    hist = []
    for s in range(o, c):
        S = spot.at(s)
        rets.append(math.log(S / spot.at(s - 1)))
        sig = (sum(r * r for r in rets[-900:]) / 900) ** 0.5
        tau = c - s
        if tau > 60:
            mean, sd = S, S * sig * math.sqrt(tau - 40)
        else:
            obs = [spot.at(x) for x in range(c - 60, s + 1)]
            mean = (sum(obs) + S * (tau - 1)) / 60
            sd = S * sig * math.sqrt(max(tau, 1) ** 3 / 3) / 60
        out[s] = N.cdf(math.log(mean / K) / max(sd / S, 1e-9))
    return out


def quote_series(m):
    """Per-second (bid, ask) for YES from the tape: last NO-taker price, last YES-taker price."""
    o, c = int(m["open"]), int(m["close"])
    out = {}
    tr = m["trades"]
    i = 0
    bid = ask = None
    tb = ta = -1e9
    for s in range(o, c + 61):
        while i < len(tr) and tr[i][0] < s:
            t, side, p, n = tr[i]
            if side == "yes":
                ask, ta = p, t
            else:
                bid, tb = p, t
            i += 1
        if bid is not None and ask is not None and s - ta < 10 and s - tb < 10 and bid < ask:
            out[s] = (bid, ask)
    return out


def leadlag(markets, spot, H=(0, 1, 2, 3, 5, 10, 20, 30)):
    xs, ys = [], {h: [] for h in H}
    for m in markets:
        f, q = m["fair"], m["q"]
        for s in range(int(m["open"]) + 1, int(m["close"]) - 90):
            if s not in f or s - 1 not in f or s - 1 not in q:
                continue
            dfair = f[s] - f[s - 1]
            if abs(dfair) < 0.01:
                continue  # only seconds where bitcoin moved the fair value by 1c+
            row = []
            for h in H:
                if s + h not in q:
                    break
                row.append(sum(q[s + h]) / 2 - sum(q[s - 1]) / 2)
            if len(row) < len(H):
                continue
            xs.append(dfair)
            for h, v in zip(H, row):
                ys[h].append(v)
    print(f"seconds where fair value jumped 1c+: {len(xs)}")
    sxx = sum(x * x for x in xs)
    for h in H:
        beta = sum(x * y for x, y in zip(xs, ys[h])) / sxx
        print(f"  Kalshi mid has absorbed {beta:6.1%} of the move {h:2d}s later")


def bot(markets, latency=1, margin=0.02, stake=20.0, cooldown=5, last_secs=30):
    trades = []
    for m in markets:
        f, q = m["fair"], m["q"]
        nxt = 0
        for s in sorted(f):
            if s < nxt or m["close"] - s < last_secs or s + latency not in q:
                continue
            bid, ask = q[s + latency]
            for side, price, fair in (("yes", ask, f[s]), ("no", 1 - bid, 1 - f[s])):
                if not (0.03 <= price <= 0.97):
                    continue
                n = math.floor(stake / price)
                fee = taker_fee(price, n) / n
                if fair - price - fee > margin:
                    later = q.get(s + latency + 60) or q.get(s + latency + 30)
                    mark = (sum(later) / 2 if side == "yes" else 1 - sum(later) / 2) if later else None
                    won = m["yes"] if side == "yes" else 1 - m["yes"]
                    trades.append({"ticker": m["ticker"], "t": s, "side": side, "price": price, "n": n,
                                   "fee": fee * n, "edge": fair - price, "pnl": n * (won - price) - fee * n,
                                   "mark": None if mark is None else n * (mark - price) - fee * n})
                    nxt = s + cooldown
                    break
    return trades


def anchored(markets, latency=1, margin=0.02, stake=20.0, anchor=5, cooldown=5, last_secs=30, min_jump=0.0):
    """
    The latency bot: Kalshi's own mid `anchor` seconds ago, plus how much bitcoin's
    move since then should have changed it. If the ask (seen `latency` seconds
    later, when our order lands) is still below that by more than fee + margin, buy.
    """
    trades = []
    for m in markets:
        f, q = m["fair"], m["q"]
        nxt = 0
        for s in sorted(f):
            if s < nxt or m["close"] - s < last_secs or s + latency not in q or s - anchor not in q or s - anchor not in f:
                continue
            jump = f[s] - f[s - anchor]
            if abs(jump) < min_jump:
                continue
            target = sum(q[s - anchor]) / 2 + jump
            bid, ask = q[s + latency]
            for side, price, fair in (("yes", ask, target), ("no", 1 - bid, 1 - target)):
                if not (0.03 <= price <= 0.97):
                    continue
                n = math.floor(stake / price)
                fee = taker_fee(price, n) / n
                if fair - price - fee > margin:
                    later = q.get(s + latency + 60) or q.get(s + latency + 30)
                    mark = (sum(later) / 2 if side == "yes" else 1 - sum(later) / 2) if later else None
                    won = m["yes"] if side == "yes" else 1 - m["yes"]
                    trades.append({"ticker": m["ticker"], "t": s, "side": side, "price": price, "n": n,
                                   "fee": fee * n, "edge": fair - price, "pnl": n * (won - price) - fee * n,
                                   "mark": None if mark is None else n * (mark - price) - fee * n})
                    nxt = s + cooldown
                    break
    return trades


def report(name, trades, days):
    if not trades:
        print(f"{name}: no trades"); return
    pnl = sum(t["pnl"] for t in trades)
    marks = [t["mark"] for t in trades if t["mark"] is not None]
    by_mkt = {}
    for t in trades:
        by_mkt[t["ticker"]] = by_mkt.get(t["ticker"], 0) + t["pnl"]
    vals = list(by_mkt.values())
    mu = sum(vals) / len(vals)
    se = (sum((v - mu) ** 2 for v in vals) / max(1, len(vals) - 1)) ** 0.5 * math.sqrt(len(vals))
    print(f"{name}: {len(trades)} trades ({len(trades) / days:.0f}/day), avg seen edge {sum(t['edge'] for t in trades) / len(trades) * 100:.1f}c, "
          f"settled P&L ${pnl:+.2f} (±{se:.0f}) = ${pnl / days:+.2f}/day; "
          f"60s mark-to-market ${sum(marks):+.2f} = ${sum(marks) / days:+.2f}/day")


if __name__ == "__main__":
    spot = Spot()
    ms = []
    for m in load_markets():
        f = fair_series(m, spot)
        if f:
            m["fair"], m["q"] = f, quote_series(m)
            ms.append(m)
    days = len(ms) / 96
    print(f"{len(ms)} markets with bitcoin data ({days:.1f} days)")
    # sanity: is the fair value any good? Brier vs Kalshi mid at the 7-minute mark
    bf = bk = 0
    n = 0
    for m in ms:
        s = int(m["open"]) + 420
        if s in m["q"]:
            bf += (m["fair"][s] - m["yes"]) ** 2
            bk += (sum(m["q"][s]) / 2 - m["yes"]) ** 2
            n += 1
    print(f"Brier at 7 min in: our fair {bf / n:.4f}  Kalshi mid {bk / n:.4f}  (lower is better, n={n})")
    leadlag(ms, spot)
    if "--model" in sys.argv:
        for lat in (1, 5):
            report(f"model bot, react {lat}s", bot(ms, latency=lat, margin=0.05), days)
    for lat in (0, 1, 2, 3, 5):
        for margin in (0.01, 0.03, 0.05):
            report(f"latency bot, react {lat}s, need {margin * 100:.0f}c", anchored(ms, latency=lat, margin=margin), days)
