"""
Taker originals vs. patient twins over ~55 days of 1-minute Kalshi candles.

Same rules as twins.py (looks every 2 minutes, $10 a bet, one bet per market,
hold to settlement), but fills for a resting bid come from the candles: our bid
for YES at p sits alone at the top of the book, so if the best YES bid ever
dropped below p while we waited, sellers went through us and we were filled.
(For a NO bid at p: the YES ask rose above 1 - p.)
"""
import gzip, json, math, os, sys
from datetime import datetime
from tapelib import Spot, taker_fee
from twins import betty, edie, nick, summary, tick

HERE = os.path.dirname(os.path.abspath(__file__))
STAKE = 10.0


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def f(x):
    return float(x) if x not in (None, "") else None


def load():
    d = json.load(gzip.open(f"{HERE}/candles.json.gz", "rt"))
    out = []
    for tk, cs in d["candles"].items():
        meta = d["meta"].get(tk)
        if not meta or meta["result"] not in ("yes", "no"):
            continue
        rows = {}
        for c in cs:
            yb, ya = c.get("yes_bid") or {}, c.get("yes_ask") or {}
            vals = [f(yb.get("close_dollars")), f(ya.get("close_dollars")), f(yb.get("low_dollars")),
                    f(ya.get("high_dollars"))]
            if None in vals:
                continue
            rows[int(c["end_period_ts"])] = vals
        out.append({"ticker": tk, "open": ts(meta["open_time"]), "close": ts(meta["close_time"]),
                    "yes": 1.0 if meta["result"] == "yes" else 0.0, "c": rows})
    out.sort(key=lambda m: m["open"])
    return out


def run(markets, signal, mode, improve=1, ttl=110, spot=None, delay=15):
    bets = []
    for m in markets:
        c = m["c"]
        t = math.ceil(m["open"] / 120) * 120 + delay
        while t < m["close"] - 60:
            minute = int(t // 60 * 60)
            row = c.get(minute)
            secs = m["close"] - t
            mom = None
            if spot and spot.lo + 900 <= t <= spot.hi:
                a, b = spot.at(t - 900), spot.at(t)
                mom = math.log(b / a) if a and b else None
            side = signal(row[0], row[1], secs, mom) if row and 0 < row[0] < row[1] < 1 else None
            if side:
                bid, ask = row[0], row[1]
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
                filled = False
                for k in range(minute + 60, int(t + ttl + 30), 60):
                    r = c.get(k)
                    if not r or k - 60 >= m["close"]:
                        continue
                    if side == "yes" and r[2] < px - 1e-9:
                        filled = True
                    if side == "no" and r[3] > 1 - px + 1e-9:
                        filled = True
                    if filled:
                        break
                if filled:
                    bets.append((m["ticker"], side, px, math.floor(STAKE / px), 0.0, m["yes"], t))
                    break
            t += 120
    return bets


if __name__ == "__main__":
    ms = load()
    spot = Spot(f"{HERE}/binance1m")
    half = ms[len(ms) // 2]["open"]
    print(len(ms), "markets", f"{(ms[-1]['close'] - ms[0]['open']) / 86400:.1f} days")
    for label, sig in (("Edie", edie), ("Nick", nick), ("Betty", betty)):
        for name, kw in (("taker", {"mode": "taker"}), ("maker join bid", {"mode": "maker", "improve": 0}),
                         ("maker bid+1 tick", {"mode": "maker", "improve": 1}),
                         ("maker ask-1 tick", {"mode": "maker", "improve": "inside"})):
            bets = run(ms, sig, spot=spot, **kw)
            summary(f"{label} {name}", bets)
            if "--halves" in sys.argv:
                summary("   first half", [b for b in bets if b[6] < half])
                summary("   second half", [b for b in bets if b[6] >= half])
        print()
