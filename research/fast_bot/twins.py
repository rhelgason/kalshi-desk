"""
Taker originals vs. maker twins, replayed on the real KXBTC15M trade tape.

The live bot looks every 2 minutes (even clock minutes, ~15s late). At each
look, an employee whose signal fires either
  taker: buys at the ask right away (taker fee), or
  maker: posts a bid at (best bid + improve), capped under the ask, for `ttl`
         seconds. It fills only from real trades that sold into it: a trade
         below our price fills fully, a trade exactly at it fills `queue` of its
         size. No fee (this series charges takers only).
One position per market. $10 per bet. Hold to settlement.
"""
import math, sys
from tapelib import Quotes, Spot, load_markets, taker_fee

STAKE = 10.0


def tick(p):
    """Kalshi's tapered deci-cent ladder: 0.1c steps below 10c and above 90c, 1c between."""
    return 0.001 if p < 0.10 or p >= 0.90 else 0.01


def edie(bid, ask, secs, mom):
    if not (600 <= secs <= 780) or ask - bid > 0.03:
        return None
    for side, a in (("yes", ask), ("no", 1 - bid)):
        if 0.75 <= a <= 0.85:
            return side
    return None


def nick(bid, ask, secs, mom):
    if secs < 600 or ask - bid > 0.02:
        return None
    for side, a in (("yes", ask), ("no", 1 - bid)):
        if 0.88 <= a <= 0.95:
            return side
    return None


def betty(bid, ask, secs, mom):
    if mom is None or not (600 <= secs <= 900) or ask - bid > 0.03 or abs(mom) < 0.002:
        return None
    side = "yes" if mom > 0 else "no"
    a = ask if side == "yes" else 1 - bid
    return side if a <= 0.60 else None


def run(markets, signal, mode, improve=0.001, ttl=110, queue=0.3, spot=None, delay=15):
    bets = []
    for m in markets:
        q = Quotes(m["trades"])
        trades = m["trades"]
        t = math.ceil(m["open"] / 120) * 120 + delay
        while t < m["close"] - 60:
            secs = m["close"] - t
            quote = q.at(t)
            mom = None
            if spot and spot.lo + 900 <= t <= spot.hi:
                a, b = spot.at(t - 900), spot.at(t)
                mom = math.log(b / a) if a and b else None
            side = signal(*quote, secs, mom) if quote else None
            if side:
                bid, ask = quote
                s_bid, s_ask = (bid, ask) if side == "yes" else (1 - ask, 1 - bid)
                if mode == "taker":
                    n = math.floor(STAKE / s_ask)
                    bets.append((m["ticker"], side, s_ask, n, taker_fee(s_ask, n), m["yes"], t))
                    break
                if improve == "inside":
                    px = s_ask - tick(s_ask - 0.0001)
                else:
                    px = min(s_bid + improve * tick(s_bid), s_ask - tick(s_ask - 0.0001))
                px = round(max(px, s_bid), 4)
                want = math.floor(STAKE / px)
                got = 0.0
                for tt, ts_side, yp, c in trades:
                    if tt <= t or tt > t + ttl:
                        continue
                    if ts_side == side:
                        continue  # a buyer of our side doesn't sell to us
                    p = yp if side == "yes" else 1 - yp
                    if p < px - 1e-9:
                        got += c
                    elif abs(p - px) < 1e-9:
                        got += c * queue
                    if got >= want:
                        break
                got = math.floor(min(got, want))
                if got >= 1:
                    bets.append((m["ticker"], side, px, got, 0.0, m["yes"], t))
                    break
                t += 120
                continue
            t += 120
    return bets


def summary(name, bets):
    if not bets:
        print(f"{name:34s} no bets"); return
    pnl = [n * ((v if s == "yes" else 1 - v) - p) - fee for _, s, p, n, fee, v, _ in bets]
    staked = sum(p * n for _, _, p, n, _, _, _ in bets)
    wins = sum(1 for _, s, p, n, fee, v, _ in bets if (v if s == "yes" else 1 - v) == 1)
    avgp = sum(p for _, _, p, _, _, _, _ in bets) / len(bets)
    fees = sum(b[4] for b in bets)
    mean = sum(pnl) / len(pnl)
    sd = (sum((x - mean) ** 2 for x in pnl) / max(1, len(pnl) - 1)) ** 0.5
    se = sd * math.sqrt(len(pnl))
    print(f"{name:34s} {len(bets):4d} bets  win {wins / len(bets):5.1%}  avg price {avgp:.3f}  "
          f"fees ${fees:6.2f}  P&L ${sum(pnl):+8.2f} (±{se:.0f})  per $1 {sum(pnl) / staked * 100:+.2f}c")


if __name__ == "__main__":
    ms = load_markets()
    spot = Spot()
    print(len(ms), "markets", f"{(ms[-1]['close'] - ms[0]['open']) / 86400:.1f} days")
    for label, sig in (("Edie", edie), ("Nick", nick), ("Betty", betty)):
        summary(f"{label} taker", run(ms, sig, "taker", spot=spot))
        for imp, name in ((0, "join bid"), (1, "bid+1 tick"), ("inside", "ask-1 tick")):
            summary(f"{label} maker {name}", run(ms, sig, "maker", improve=imp, spot=spot))
        print()
