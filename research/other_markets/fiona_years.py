"""Final Whistle Fiona's rules replayed on a year of end-of-game trades (2026-11-02).

Tape from sports_history.py (one market per game, every trade from 3.5 h before Kalshi's scheduled end to 2 h after).
Like the bot: a look every 2 minutes from FROM to TO hours around the scheduled end; at a look, a game she holds no
bet in, with a side whose last price (a trade on that side within 3 h) is in LO..HI, gets a bid at that price for
110 s. Harsh fills (a trade through our price fills in full, at it QUEUE of it), from 1 s after posting, up to $CAP;
the first filled bid makes the game busy. Held to the settle, after the sports maker fee (0.0175 x p(1-p) a contract,
rounded up to the cent per order). Breaks results down by league, price, and when the bet filled, so one wide run
shows where the edge is.
    python research/other_markets/fiona_years.py data/sports_history   env QUEUE (0.3), CAP (10), LO (0.97), HI (0.995),
                                                                       FROM (-3), TO (2)"""
import gzip, json, math, os, sys
from collections import defaultdict
from datetime import datetime, timezone

D = sys.argv[1]
QUEUE, CAP = float(os.environ.get("QUEUE", "0.3")), float(os.environ.get("CAP", "10"))
LO, HI = float(os.environ.get("LO", "0.97")), float(os.environ.get("HI", "0.995"))
FROM, TO = float(os.environ.get("FROM", "-3")), float(os.environ.get("TO", "2"))
LEAGUE = {"KXNFLGAME": "NFL", "KXNCAAFGAME": "college football", "KXNBAGAME": "NBA", "KXMLBGAME": "MLB",
          "KXNHLGAME": "NHL"}


def side_price(yp, taker):
    return ("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp)


def replay(m, s):
    t, i, last = m["t"], 0, {}
    look, end = m["ref"] + FROM * 3600, m["ref"] + TO * 3600
    while look < end:
        while i < len(t) and t[i][0] < look:
            sd, p = side_price(t[i][1], t[i][3]); last[sd] = (p, t[i][0]); i += 1
        pick = next(((sd, v[0]) for sd, v in sorted(last.items(), key=lambda kv: kv[0] != "yes")
                     if LO <= v[0] < HI and look - v[1] < 3 * 3600), None)
        if pick:
            sd, price = pick
            spent = got = 0.0
            for ts, yp, n, taker in t[i:]:
                if ts < look + 1:
                    continue
                if ts > look + 110 or spent >= CAP:
                    break
                s2, p = side_price(yp, taker)
                if s2 != sd:
                    continue
                q = n if p < price - 1e-9 else n * QUEUE if abs(p - price) < 1e-9 else 0
                q = min(q, (CAP - spent) / price)
                if q >= 0.01:
                    spent += q * price; got += q
            if spent > 0:
                fee = math.ceil(0.0175 * got * price * (1 - price) * 100 - 1e-9) / 100
                return {"s": s, "close": m["ref"], "at": (look - m["ref"]) / 3600, "price": price, "spent": spent,
                        "pnl": (got if m["result"] == sd else 0) - spent - fee, "ticker": m["ticker"]}
        look += 120
    return None


rows = []
for s in LEAGUE:
    path = os.path.join(D, f"{s}.jsonl.gz")
    if not os.path.exists(path):
        continue
    with gzip.open(path, "rt") as fh:
        for line in fh:
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            r = replay(m, s) if m["t"] else None
            if r:
                rows.append(r)
rows.sort(key=lambda r: r["close"])
half = rows[len(rows) // 2]["close"] if rows else 0


def line(label, rs):
    if not rs:
        return
    spent = sum(r["spent"] for r in rs); pnl = sum(r["pnl"] for r in rs)
    byday = defaultdict(lambda: [0.0, 0.0])
    for r in rs:
        byday[r["close"] // 86400][0] += r["pnl"]; byday[r["close"] // 86400][1] += r["spent"]
    v = [a / b for a, b in byday.values()]
    mu = sum(v) / len(v); sd = (sum((x - mu) ** 2 for x in v) / max(1, len(v) - 1)) ** 0.5
    t = mu / sd * math.sqrt(len(v)) if sd else 0
    c = lambda xs: sum(r["pnl"] for r in xs) / sum(r["spent"] for r in xs) * 100 if xs else float("nan")
    lost = sum(r["pnl"] < -0.5 * r["spent"] for r in rs)
    print(f"  {label:20s} {len(rs):5d} bets  lost {lost:3d} ({lost/len(rs)*100:4.1f}%)  {pnl/spent*100:+6.2f}c per $1  "
          f"${pnl:+8.2f}  halves {c([r for r in rs if r['close'] < half]):+6.2f} / {c([r for r in rs if r['close'] >= half]):+6.2f}"
          f"  t {t:+5.1f}")


day = lambda s: datetime.fromtimestamp(s, timezone.utc).strftime("%b %d %Y")
if rows:
    print(f"Fiona on {day(rows[0]['close'])} - {day(rows[-1]['close'])}: {LO*100:.1f}-{HI*100:.1f}c, {FROM:+g} h to {TO:+g} h "
          f"around the scheduled end, 2-minute looks, 110 s bids, harsh fills (queue {QUEUE}), ${CAP:g} a game, after fees")
line("all", rows)
print("by league:")
for s, name in LEAGUE.items():
    line(name, [r for r in rows if r["s"] == s])
print("by when the bet filled (hours from the scheduled end):")
for a, b in ((-3.5, -2), (-2, -1), (-1, -0.5), (-0.5, 0), (0, 0.5), (0.5, 1), (1, 2)):
    line(f"{a:+.1f} to {b:+.1f} h", [r for r in rows if a <= r["at"] < b])
print("by price:")
for a, b in ((0.90, 0.95), (0.95, 0.97), (0.97, 0.98), (0.98, 0.99), (0.99, 0.995)):
    line(f"{a*100:.0f}-{b*100:.1f}c", [r for r in rows if a <= r["price"] < b])
print("league by when:")
for s, name in LEAGUE.items():
    for a, b in ((-3.5, -1), (-1, 0), (0, 2)):
        line(f"{name[:10]} {a:+.0f}..{b:+.0f}h", [r for r in rows if r["s"] == s and a <= r["at"] < b])
print("worst losses:")
for r in sorted(rows, key=lambda r: r["pnl"])[:8]:
    print(f"  {r['ticker']:40s} {r['price']:.3f} at {r['at']:+.1f} h  ${r['pnl']:+.2f}")
