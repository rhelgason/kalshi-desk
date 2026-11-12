"""Do the GitHub bots' "check the coin first" filters improve Sadie? (2026-10-27)

Replays Sadie in cron mode (maker_bets.py MODE=cron: a look every 120 s, 300-540 s left, 92-99.5c favorites, one tick
over the best bid, 110 s bids, harsh fills) on ETH/SOL/XRP and records, for each market she bets, what the official
index (index_history.py) said at the look that placed her first filled bid:
  fair   the index odds of her side winning (buzzer.py's model: drift to the close, then the 60 s average)
  mom30  the coin's move over the last 30 s, toward her side, in sigmas  (the bots' "momentum confirms")
  mom120 the same over 120 s
  prev   did the coin's previous 15-minute market settle her side's way  (reedjacobp's "previous result")
  peers  how many of the other two coins' markets closing at the same moment have a favorite on the same side
Prints per-$1 results by bucket, with first-half / second-half so a filter has to hold in both.
    python sadie_filters.py TAPE_DIR INDEX_DIR"""
import gzip, json, math, os, sys
from collections import defaultdict

sys.argv += [] if len(sys.argv) > 2 else ["data/tape62", "data/index"]
TAPE, IDX = sys.argv[1], sys.argv[2]
A, B, LO, HI, CAP, QUEUE, LAT = 300, 540, 0.92, 0.995, 10.0, 0.3, 1.0
COINS = {"ETH": "ETHUSD_RTI", "SOL": "SOLUSD_RTI", "XRP": "XRPUSD_RTI"}
# SRC=binance: what the live bot can know instead (an exchange's spot, vol from 4 hours of 1-minute closes), all 4 coins
SRC = os.environ.get("SRC", "index")
if SRC == "binance":
    COINS = {c: c for c in ("ETH", "SOL", "XRP", "DOGE")}
Phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))
tick = lambda p: 0.001 if p >= 0.9 or p <= 0.1 else 0.01


def load_index(name):
    v = {}
    with gzip.open(os.path.join(IDX, f"{name}.jsonl.gz"), "rt") as fh:
        for line in fh:
            try:
                v.update({int(k): x for k, x in json.loads(line)["v"].items()})
            except json.JSONDecodeError:
                pass
    return v


class Binance:
    def __init__(self, coin):
        import csv, io, zipfile
        from datetime import datetime
        d = "data/binance1s"
        files = sorted(f for f in os.listdir(d) if f.startswith(coin + "USDT-1s-"))
        self.t0 = int(datetime.fromisoformat(files[0][-14:-4] + "T00:00:00+00:00").timestamp())
        import array
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

    __getitem__ = get


def sigma(v, close, at):
    if SRC == "binance" or os.environ.get("VOL") == "4h":   # like the bot's Kraken realized vol: 240 one-minute closes
        c = [v.get(s) for s in range(at - 14400, at, 60)]
        if None in c:
            return None
        r = [math.log(b / a) for a, b in zip(c, c[1:])]
        return max((sum(x * x for x in r) / len(r)) ** 0.5 / math.sqrt(60), 1e-6)
    if os.environ.get("VOL") == "15m":   # 1-minute closes over the last 15 minutes
        c = [v.get(s) for s in range(at - 900, at, 60)]
        if None in c:
            return None
        r = [math.log(b / a) for a, b in zip(c, c[1:])]
        return max((sum(x * x for x in r) / len(r)) ** 0.5 / math.sqrt(60), 1e-6)
    if os.environ.get("VOL") == "lag":   # the index's own 1-second history, which Kalshi serves ~8 minutes late
        at -= 480
    r = [math.log(v[s] / v[s - 1]) for s in range(at - 600, at) if v.get(s) and v.get(s - 1)]
    return max((sum(x * x for x in r) / len(r)) ** 0.5, 1e-6) if len(r) > 300 else None


def fair_yes(v, close, strike, at, sig):
    now = v.get(at - 1)
    if now is None:
        return None
    left = close - at                     # all of it unfixed: drift to the window, then the average's own noise
    sd = sig * math.sqrt(max(left - 60, 0) + 60 * (61 * 121) / 6 / 3600)
    return Phi(math.log(now / strike) / max(sd, 1e-9))


def sadie(m):
    """Cron Sadie on one market: (side, spent, got, look time of the first filled bid, the bid price) or None."""
    close = m["close"]; best = {"yes": None, "no": None}; bid = None; spent = got = 0.0; held = None
    looked = set(); first = None
    for t, yp, n, taker in m["t"]:
        side, p = (("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp))
        slot = int(t - 5) // 120
        if slot not in looked and A < close - t <= B and (bid is None or bid[3] <= t):
            looked.add(slot)
            for s_ in ("yes", "no"):
                q = best[s_]
                if q and LO <= q < HI and (held is None or s_ == held):
                    bid = (s_, round(min(q + tick(q), 0.999), 4), slot * 120 + 5 + LAT, slot * 120 + 5 + 110, slot * 120 + 5)
        if bid and bid[2] <= t <= bid[3] and side == bid[0] and spent < CAP:
            qq = n if p < bid[1] - 1e-9 else n * QUEUE if abs(p - bid[1]) < 1e-9 else 0
            qq = min(qq, (CAP - spent) / bid[1])
            if qq >= 0.01:
                spent += qq * bid[1]; got += qq; held = bid[0]
                first = first or (bid[4], bid[1])
        best[side] = p
    return (held, spent, got, *first) if spent > 0 else None


def favorite_at(m, at):
    """The side priced 70c+ at second `at` (from the last trade print on each side), or None."""
    best = {"yes": None, "no": None}
    for t, yp, n, taker in m["t"]:
        if t >= at:
            break
        side, p = (("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp))
        best[side] = p
    for s in ("yes", "no"):
        if best[s] and best[s] >= 0.7:
            return s
    return None


markets = {c: {} for c in COINS}
for coin in COINS:
    with gzip.open(os.path.join(TAPE, f"KX{coin}15M.jsonl.gz"), "rt") as f:
        for line in f:
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            markets[coin][m["close"]] = m
    print(coin, len(markets[coin]), "markets", file=sys.stderr)

rows = []
for coin, name in COINS.items():
    v = Binance(coin) if SRC == "binance" else load_index(name)
    for close, m in markets[coin].items():
        r = sadie(m)
        if not r or not m.get("strike"):
            continue
        side, spent, got, at, price = r
        sig = sigma(v, close, at)
        if sig is None or v.get(at - 121) is None or v.get(at - 31) is None:
            continue
        fy = fair_yes(v, close, m["strike"], at, sig)
        if fy is None:
            continue
        sgn = 1 if side == "yes" else -1
        prev = markets[coin].get(close - 900)
        peers = [favorite_at(markets[c][close], at) for c in COINS if c != coin and close in markets[c]]
        rows.append({"coin": coin, "close": close, "side": side, "price": price, "spent": spent,
                     "pnl": (got if side == m["result"] else 0) - spent,
                     "fair": fy if side == "yes" else 1 - fy,
                     "mom30": sgn * math.log(v[at - 1] / v[at - 31]) / (sig * math.sqrt(30)),
                     "mom120": sgn * math.log(v[at - 1] / v[at - 121]) / (sig * math.sqrt(120)),
                     "prev": None if not prev else prev["result"] == side,
                     "peers": sum(p == side for p in peers) - sum(p is not None and p != side for p in peers)})
    print(coin, "done", file=sys.stderr)
json.dump(rows, open("/tmp/sadie_filters.json" if not os.environ.get("OUT") else os.environ["OUT"], "w"))

rows.sort(key=lambda r: r["close"])
half = rows[len(rows) // 2]["close"]


def show(label, sel):
    def c(rs):
        s = sum(r["spent"] for r in rs)
        return (sum(r["pnl"] for r in rs) / s * 100) if s else float("nan")
    rs = [r for r in rows if sel(r)]
    if not rs:
        return
    lost = sum(r["pnl"] < 0 for r in rs) / len(rs) * 100
    print(f"  {label:28s} {len(rs):6d} bets  lost {lost:4.1f}%  {c(rs):+6.2f}c per $1 | halves "
          f"{c([r for r in rs if r['close'] < half]):+6.2f} / {c([r for r in rs if r['close'] >= half]):+6.2f}")


print(f"Sadie (cron) on {'/'.join(COINS)}, coin price from {SRC}, at her look")
show("all", lambda r: True)
print("index odds minus her price (c):")
for lo, hi in ((-99, -5), (-5, -2), (-2, 0), (0, 1), (1, 2), (2, 3), (3, 99)):
    show(f"{lo:+d}..{hi:+d}", lambda r, lo=lo, hi=hi: lo <= (r["fair"] - r["price"]) * 100 < hi)
for key in ("mom30", "mom120"):
    print(f"{key} (sigmas toward her side):")
    for lo, hi in ((-99, -1), (-1, -0.3), (-0.3, 0.3), (0.3, 1), (1, 99)):
        show(f"{lo:+.1f}..{hi:+.1f}", lambda r, lo=lo, hi=hi, k=key: lo <= r[k] < hi)
print("previous market settled her way:")
for val in (True, False):
    show(str(val), lambda r, val=val: r["prev"] is val)
print("peers agreeing minus disagreeing:")
for val in (-2, -1, 0, 1, 2):
    show(str(val), lambda r, val=val: r["peers"] == val)
