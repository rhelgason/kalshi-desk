"""
The prediction model's replay library (11-17). The live rule (a look every 2 minutes, 300-540 s left, a favourite at
92-99.5c, one tick over the best bid, 110 s bids, the coin check against Binance's price and 4 h of 1-minute vol;
QUEUE share of trades at our price) on every coin's real trade tape, with NO size limit, so each window says what a bid
of any size would have filled and made. Per window it keeps the curve at CAPS (dollars filled, profit) plus what the
coin was doing just before the first look, for the bad-day guard.

    python research/forecast/library.py OUT.json.gz data/tape_btc:BTC data/tape62:ETH ...
"""
import gzip, json, math, os, sys

from datetime import datetime

Phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))


# Copied from research/fast_coco/btc_check.py (that script runs on import)
class Binance:
    def __init__(self, coin):
        import array, csv, io, zipfile
        d = "data/binance1s"
        files = sorted(f for f in os.listdir(d) if f.startswith(coin + "USDT-1s-"))
        self.t0 = int(datetime.fromisoformat(files[0][-14:-4] + "T00:00:00+00:00").timestamp())
        t1 = int(datetime.fromisoformat(files[-1][-14:-4] + "T00:00:00+00:00").timestamp())
        self.px = array.array("d", [0.0]) * (t1 - self.t0 + 2 * 86400)  # by dates, not file count: days can be missing
        for f in files:
            with zipfile.ZipFile(os.path.join(d, f)) as z:
                for row in csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]))):
                    t = int(row[0]); t = t // 1_000_000 if t > 10**14 else t // 1000
                    if 0 <= t - self.t0 < len(self.px):
                        self.px[t - self.t0] = float(row[4])
        last = 0.0
        for i in range(len(self.px)):
            last = self.px[i] = self.px[i] or last

    def get(self, s):
        i = s - self.t0
        return self.px[i] if 0 <= i < len(self.px) and self.px[i] > 0 else None


def side_odds(v, close, strike, at, side):
    c = [v.get(s) for s in range(at - 14400, at, 60)]
    now = v.get(at - 1)
    if None in c or now is None:
        return None
    r = [math.log(b / a) for a, b in zip(c, c[1:])]
    sig = max((sum(x * x for x in r) / len(r)) ** 0.5 / math.sqrt(60), 1e-6)
    sd = sig * math.sqrt(max(close - at - 60, 0) + 60 * (61 * 121) / 6 / 3600)
    fy = Phi(math.log(now / strike) / max(sd, 1e-9))
    return fy if side == "yes" else 1 - fy


A, B, HI, QUEUE, LAT = 300, 540, 0.995, 0.3, 1.0
# Commodities have no free second-by-second price: CHECK=0 skips the coin check; LO=0.97 is their Training setting
LO = float(os.environ.get("LO", "0.92"))
CHECK = os.environ.get("CHECK", "1") != "0"
CAPS = [5, 10, 20, 40, 80, 160, 320, 640, 1280, 2560, 5120, 10240]
tick = lambda p: 0.001 if p >= 0.9 or p <= 0.1 else 0.01


def replay(m, v):
    close = m["close"]; best = {"yes": None, "no": None}; bid = None; held = None; looked = set(); fl = []; first_look = None
    for t, yp, n, taker in m["t"]:
        side, p = (("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp))
        slot = int(t - 5) // 120
        if slot not in looked and A < close - t <= B and (bid is None or bid[3] <= t):
            looked.add(slot)
            at = slot * 120 + 5
            for s_ in ("yes", "no"):
                q = best[s_]
                if q and LO <= q < HI and (held is None or s_ == held):
                    price = round(min(q + tick(q), 0.999), 4)
                    odds = side_odds(v, close, m["strike"], at, s_) if v else 1.0
                    if odds is None or odds < price:  # the coin check: skip when the coin says worse odds than the bid
                        continue
                    bid = (s_, price, at + LAT, at + 110)
                    first_look = first_look or at
        if bid and bid[2] <= t <= bid[3] and side == bid[0]:
            qq = n if p < bid[1] - 1e-9 else n * QUEUE if abs(p - bid[1]) < 1e-9 else 0
            if qq >= 0.01:
                fl.append((qq, bid[1])); held = bid[0]
        best[side] = p
    return fl, held, first_look


def move(v, at, secs):
    a, b = v.get(at - secs), v.get(at - 1)
    return round(math.log(b / a), 5) if a and b else None


def main(out, args):
    lib = {"caps": CAPS, "coins": {}}
    for arg in args:
        tape, coin = arg.split(":")
        v = Binance(coin) if CHECK else None
        path = os.path.join(tape, f"KX{coin}15M.jsonl.gz")
        wins = []
        with gzip.open(path, "rt") as fh:
            for line in fh:
                m = json.loads(line)
                if not m.get("result") or not m.get("t") or (CHECK and not m.get("strike")):
                    continue
                fl, held, look = replay(m, v)
                if not fl:
                    wins.append([m["close"], 0]); continue
                won = held == m["result"]
                curve = []
                for c in CAPS:
                    spent = got = 0.0
                    for q, p in fl:
                        take = min(q, (c - spent) / p)
                        if take < 0.01:
                            break
                        spent += take * p; got += take
                    curve.append([round(spent, 2), round((got if won else 0) - spent, 3)])
                wins.append([m["close"], 1, curve] + ([move(v, look, 300), move(v, look, 900), move(v, look, 3600)] if v else [None] * 3))
        lib["coins"][coin] = wins
        bet = [w for w in wins if w[1]]
        s10 = sum(w[2][1][0] for w in bet); p10 = sum(w[2][1][1] for w in bet)
        print(coin, len(wins), "windows,", len(bet), "bet;", f"{100 * p10 / s10:.2f}c per $1 at $10" if s10 else "", flush=True)
    with gzip.open(out, "wt") as f:
        json.dump(lib, f)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
