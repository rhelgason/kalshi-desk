"""Bitcoin Bea's trade-tape test (2026-11-01): Sadie's cron rules with the coin check, on each coin's real trade tape.

Same replay as sadie_filters.py SRC=binance (a look every 120 s, 300-540 s left, 92-99.5c favorites, one tick over the
best bid, 110 s bids, harsh fills, $10 a market), then the live rule: skip the market when the exchange's spot and
4 hours of 1-minute vol give her side worse odds than her bid. Streams each tape (bitcoin's is 1 GB), so any coin works.
Prints per-$1 results overall, by half, by week, and over the window every tape shares, so coins compare fairly.
    python research/fast_coco/btc_check.py data/tape_btc:BTC data/tape62:ETH data/tape62:SOL ...     env OUT=rows.json"""
import gzip, json, math, os, sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
os.environ["SRC"] = "binance"
A, B, LO, HI, CAP, QUEUE, LAT = 300, 540, 0.92, 0.995, 10.0, 0.3, 1.0
Phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))
tick = lambda p: 0.001 if p >= 0.9 or p <= 0.1 else 0.01


class Binance:
    def __init__(self, coin):
        import array, csv, io, zipfile
        d = "data/binance1s"
        files = sorted(f for f in os.listdir(d) if f.startswith(coin + "USDT-1s-"))
        self.t0 = int(datetime.fromisoformat(files[0][-14:-4] + "T00:00:00+00:00").timestamp())
        self.px = array.array("d", [0.0]) * (len(files) * 86400 + 86400)
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


rows = []
for arg in sys.argv[1:]:
    tape, coin = arg.split(":")
    v = Binance(coin)
    n = 0
    with gzip.open(os.path.join(tape, f"KX{coin}15M.jsonl.gz"), "rt") as fh:
        for line in fh:
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            n += 1
            r = sadie(m)
            if not r or not m.get("strike") or m.get("result") not in ("yes", "no"):
                continue
            side, spent, got, at, price = r
            odds = side_odds(v, m["close"], m["strike"], at, side)
            if odds is None:
                continue
            rows.append({"coin": coin, "close": m["close"], "price": price, "spent": spent, "odds": odds,
                         "pnl": (got if side == m["result"] else 0) - spent})
    print(coin, n, "markets", file=sys.stderr)


def c(rs):
    s = sum(r["spent"] for r in rs)
    return sum(r["pnl"] for r in rs) / s * 100 if s else float("nan")


def show(label, rs):
    if not rs:
        return
    rs = sorted(rs, key=lambda r: r["close"])
    half = rs[len(rs) // 2]["close"]
    weeks = defaultdict(list)
    for r in rs:
        weeks[r["close"] // (7 * 86400)].append(r)
    up = sum(c(w) > 0 for w in weeks.values())
    lost = sum(r["pnl"] < 0 for r in rs)
    print(f"  {label:26s} {len(rs):5d} bets  lost {lost:4d} ({lost/len(rs)*100:4.1f}%)  {c(rs):+6.2f}c per $1"
          f"  ${sum(r['pnl'] for r in rs):+8.2f}  halves {c([r for r in rs if r['close'] < half]):+6.2f} /"
          f" {c([r for r in rs if r['close'] >= half]):+6.2f}  weeks up {up}/{len(weeks)}")


if os.environ.get("OUT"):
    json.dump(rows, open(os.environ["OUT"], "w"))   # for sizing studies (sizing.py)
coins = list(dict.fromkeys(r["coin"] for r in rows))
lo = max(min(r["close"] for r in rows if r["coin"] == k) for k in coins)
hi = min(max(r["close"] for r in rows if r["coin"] == k) for k in coins)
day = lambda s: datetime.fromtimestamp(s, timezone.utc).strftime("%b %d")
for title, sel in (("whole tape", lambda r: True), (f"shared window {day(lo)} - {day(hi)}", lambda r: lo <= r["close"] <= hi)):
    print(f"Sadie's cron rules, $10 a market, {title}")
    for k in coins:
        mine = [r for r in rows if r["coin"] == k and sel(r)]
        show(f"{k} no coin check", mine)
        show(f"{k} with coin check", [r for r in mine if r["odds"] >= r["price"]])
if "BTC" in coins:
    print("bitcoin with the coin check, by week:")
    weeks = defaultdict(list)
    for r in rows:
        if r["coin"] == "BTC" and r["odds"] >= r["price"]:
            weeks[r["close"] // (7 * 86400)].append(r)
    for w in sorted(weeks):
        rs = weeks[w]
        print(f"  week of {day(w * 7 * 86400)}  {len(rs):4d} bets  {c(rs):+6.2f}c per $1  ${sum(r['pnl'] for r in rs):+7.2f}")
    print("bitcoin with the coin check, by price:")
    for a, b in ((0.92, 0.95), (0.95, 0.97), (0.97, 0.99), (0.99, 1.0)):
        show(f"{a*100:.0f}-{b*100:.0f}c", [r for r in rows if r["coin"] == "BTC" and r["odds"] >= r["price"] and a <= r["price"] < b])
