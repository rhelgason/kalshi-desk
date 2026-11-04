"""Hourly coin markets (KXBTCD etc., "above $X at 3 pm") on Sadie's rules (2026-11-03).

Same replay as btc_check.py (a look every 120 s, 92-99.5c favorites, one tick over the side's last price, 110 s bids,
harsh fills, $10 a market, the coin check from Binance 1-second prices), but each hour has ~30 traded strikes instead
of one market, so it reports by minutes left, by strike count per hour (every strike vs one per hour), by price and
by half. Tape from tape.py (the final 30 minutes of every settled market):
    python research/fast_coco/tape.py 60 30 data/tape_hourly KXBTCD KXETHD ...
    python research/fast_coco/hourly_check.py data/tape_hourly BTC ETH SOL XRP DOGE
"""
import gzip, json, math, os, re, sys
from collections import defaultdict
from datetime import datetime, timezone

QUEUE, LAT, CAP, LO, HI = 0.3, 1.0, 10.0, 0.92, 0.995
WINDOWS = ((120, 300), (300, 540), (540, 900), (900, 1260), (1260, 1740))
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
    """btc_check.py's coin check: spot vs strike with 4 h of 1-minute vol, settling on a 60-second average."""
    c = [v.get(s) for s in range(at - 14400, at, 60)]
    now = v.get(at - 1)
    if None in c or now is None:
        return None
    r = [math.log(b / a) for a, b in zip(c, c[1:])]
    sig = max((sum(x * x for x in r) / len(r)) ** 0.5 / math.sqrt(60), 1e-6)
    sd = sig * math.sqrt(max(close - at - 60, 0) + 60 * (61 * 121) / 6 / 3600)
    fy = Phi(math.log(now / strike) / max(sd, 1e-9))
    return fy if side == "yes" else 1 - fy


def sadie(m, a, b):
    """Cron Sadie on one market from a to b seconds left: (side, spent, got, look time, bid price) or None."""
    close = m["close"]; best = {"yes": None, "no": None}; bid = None; spent = got = 0.0; held = None
    looked = set(); first = None
    for t, yp, n, taker in m["t"]:
        side, p = (("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp))
        slot = int(t - 5) // 120
        if slot not in looked and a < close - t <= b and (bid is None or bid[3] <= t):
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


def markets(path):
    """Each saved market; a tape still downloading ends mid-stream, so stop quietly there."""
    with gzip.open(path, "rt") as fh:
        try:
            for line in fh:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
        except (EOFError, OSError):
            return


def strike_of(m):
    if m.get("strike"):
        return float(m["strike"])
    x = re.search(r"-T([\d.]+)$", m["ticker"])
    return float(x.group(1)) if x else None


def main():
    D, COINS = sys.argv[1], sys.argv[2:]
    rows = []
    for coin in COINS:
        path = os.path.join(D, f"KX{coin}D.jsonl.gz")
        if not os.path.exists(path):
            continue
        v = Binance(coin)
        n = 0
        for m in markets(path):
            strike = strike_of(m)
            if not m["t"] or not strike or m.get("result") not in ("yes", "no"):
                continue
            n += 1
            for a, b in WINDOWS:
                r = sadie(m, a, b)
                if not r:
                    continue
                side, spent, got, at, price = r
                odds = side_odds(v, m["close"], strike, int(at), side)
                if odds is None:
                    continue
                rows.append({"coin": coin, "w": (a, b), "event": m["ticker"].rsplit("-", 1)[0], "close": m["close"],
                             "price": price, "spent": spent, "odds": odds, "at": at,
                             "pnl": (got if side == m["result"] else 0) - spent})
        print(coin, n, "markets with trades", file=sys.stderr)


    def c(rs):
        s = sum(r["spent"] for r in rs)
        return sum(r["pnl"] for r in rs) / s * 100 if s else float("nan")


    def show(label, rs):
        if not rs:
            return
        rs = sorted(rs, key=lambda r: r["close"])
        half = rs[len(rs) // 2]["close"]
        days = defaultdict(lambda: [0.0, 0.0])
        for r in rs:
            d = days[r["close"] // 86400]; d[0] += r["pnl"]; d[1] += r["spent"]
        v = [p / s for p, s in days.values()]
        mu = sum(v) / len(v); sd = (sum((x - mu) ** 2 for x in v) / max(1, len(v) - 1)) ** 0.5
        t = mu / sd * math.sqrt(len(v)) if sd else 0
        lost = sum(r["pnl"] < 0 for r in rs)
        print(f"  {label:30s} {len(rs):6d} bets  lost {lost:4d} ({lost/len(rs)*100:4.1f}%)  {c(rs):+6.2f}c per $1"
              f"  ${sum(r['pnl'] for r in rs):+9.2f}  halves {c([r for r in rs if r['close'] < half]):+6.2f} /"
              f" {c([r for r in rs if r['close'] >= half]):+6.2f}  days up {sum(x > 0 for x in v)}/{len(v)}  t {t:+4.1f}")


    def one_per_hour(rs):
        """The bot's one-bet-per-event habit: the first bid that fills in each hour (ties: nearest to 95c)."""
        by = {}
        for r in sorted(rs, key=lambda r: (r["at"], abs(r["price"] - 0.95))):
            by.setdefault(r["event"], r)
        return list(by.values())


    day = lambda s: datetime.fromtimestamp(s, timezone.utc).strftime("%b %d")
    if rows:
        print(f"Hourly coins on Sadie's rules, {day(min(r['close'] for r in rows))} - {day(max(r['close'] for r in rows))},"
              f" $10 a market, harsh fills (queue {QUEUE})")
    for coin in COINS:
        mine = [r for r in rows if r["coin"] == coin]
        if not mine:
            continue
        print(f"{coin}, by minutes left (every strike / with the coin check / one per hour with the check):")
        for w in WINDOWS:
            ws = [r for r in mine if r["w"] == w]
            chk = [r for r in ws if r["odds"] >= r["price"]]
            show(f"{w[0]//60}-{w[1]//60} min left", ws)
            show(f"{w[0]//60}-{w[1]//60} min, coin check", chk)
            show(f"{w[0]//60}-{w[1]//60} min, check, 1/hour", one_per_hour(chk))
    print("all coins with the coin check, by price (5-9 min left, every strike):")
    for a, b in ((0.92, 0.95), (0.95, 0.97), (0.97, 0.99), (0.99, 1.0)):
        show(f"{a*100:.0f}-{b*100:.0f}c", [r for r in rows if r["w"] == (300, 540) and r["odds"] >= r["price"] and a <= r["price"] < b])
    if os.environ.get("OUT"):
        json.dump(rows, open(os.environ["OUT"], "w"))


if __name__ == "__main__":
    main()
