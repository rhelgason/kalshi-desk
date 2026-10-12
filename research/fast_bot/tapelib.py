"""Shared loading for the tape studies."""
import bisect, csv, glob, gzip, json, math, os
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def load_markets(folder=f"{HERE}/tape"):
    out = []
    for p in sorted(glob.glob(f"{folder}/*.json.gz")):
        with gzip.open(p, "rt") as f:
            d = json.load(f)
        m = d["m"]
        if m["result"] not in ("yes", "no"):
            continue
        rows = sorted(((ts(t), s, p, c) for t, s, p, c in d["trades"]), key=lambda r: r[0])
        out.append({"ticker": m["ticker"], "open": ts(m["open_time"]), "close": ts(m["close_time"]),
                    "yes": 1.0 if m["result"] == "yes" else 0.0, "trades": rows})
    out.sort(key=lambda m: m["open"])
    return out


class Quotes:
    """Best bid/ask for YES rebuilt from the tape: a YES taker paid the ask, a NO taker hit the bid."""

    def __init__(self, trades):
        self.t_ask, self.ask, self.t_bid, self.bid = [], [], [], []
        for t, side, p, c in trades:
            if side == "yes":
                self.t_ask.append(t); self.ask.append(p)
            else:
                self.t_bid.append(t); self.bid.append(p)

    def at(self, t, stale=15):
        i = bisect.bisect_right(self.t_ask, t) - 1
        j = bisect.bisect_right(self.t_bid, t) - 1
        if i < 0 or j < 0 or t - self.t_ask[i] > stale or t - self.t_bid[j] > stale:
            return None
        return self.bid[j], self.ask[i]


class Spot:
    """Binance BTCUSDT 1-second closes."""

    def __init__(self, folder=f"{HERE}/binance"):
        d = {}
        for p in sorted(glob.glob(f"{folder}/*.csv")):
            with open(p) as f:
                for row in csv.reader(f):
                    t = int(row[6])  # the bar's CLOSE time: its close price isn't known before then
                    t = (t // 1_000_000 if t > 1e14 else t // 1000) + 1
                    d[t] = float(row[4])
        self.t = sorted(d)
        self.p = [d[k] for k in self.t]
        self.lo, self.hi = self.t[0], self.t[-1]

    def at(self, t):
        i = bisect.bisect_right(self.t, t) - 1
        return self.p[i] if i >= 0 else None

    def avg(self, t0, t1):
        i, j = bisect.bisect_left(self.t, t0), bisect.bisect_right(self.t, t1)
        xs = self.p[i:j]
        return sum(xs) / len(xs) if xs else None


def taker_fee(p, n):
    return math.ceil(0.07 * n * p * (1 - p) * 100 - 1e-9) / 100
