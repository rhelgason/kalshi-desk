"""Wendy's rules replayed on two years of morning weather trades (2026-10-31).

Tape from wx_history.py (every trade 18:00 the evening before to 13:00 on the day, city time). Like the bot: a look
every 2 minutes from START to END local time on the day; at a look, a market she holds no bet in, with a side whose
last price (wx_maker.py's convention, a trade on that side within 3 h) is in LO..HI, gets a bid at that price for
110 s. Fills with maker_bets.py's harsh rules (a trade through our price fills in full, at it QUEUE of it), from 1 s
after posting, up to $CAP a market; the first filled bid makes the market busy (Wendy skips markets she holds).
Held to the settle; weather makers pay no fee.
    python research/other_markets/wx_years.py data/wx_history     env QUEUE (0.3), CAP (10), LO (0.92), HI (0.995),
                                                                  START (0), END (11)"""
import gzip, json, math, os, sys
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

D = sys.argv[1]
QUEUE, CAP = float(os.environ.get("QUEUE", "0.3")), float(os.environ.get("CAP", "10"))
LO, HI = float(os.environ.get("LO", "0.92")), float(os.environ.get("HI", "0.995"))
START, END = float(os.environ.get("START", "0")), float(os.environ.get("END", "11"))
TZ = {"KXHIGHNY": "America/New_York", "KXHIGHLAX": "America/Los_Angeles", "KXHIGHCHI": "America/Chicago",
      "KXHIGHMIA": "America/New_York", "KXHIGHAUS": "America/Chicago", "KXHIGHDEN": "America/Denver"}
MON = {m: i for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}
SEASON = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
          6: "summer", 7: "summer", 8: "summer", 9: "fall", 10: "fall", 11: "fall"}


def side_price(yp, taker):
    return ("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp)


def replay(m, s):
    code = m["event"].split("-")[1]
    day = (2000 + int(code[:2]), MON[code[2:5]], int(code[5:7]))
    base = datetime(*day, tzinfo=ZoneInfo(TZ[s])).timestamp()
    t, i, last = m["t"], 0, {}
    look = base + START * 3600
    while look < base + END * 3600:
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
                return {"s": s, "day": day, "price": price, "spent": spent,
                        "pnl": (got if m["result"] == sd else 0) - spent}
        look += 120
    return None


rows = []
for s in TZ:
    with gzip.open(os.path.join(D, f"{s}.jsonl.gz"), "rt") as fh:
        for line in fh:
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            r = replay(m, s) if m["t"] else None
            if r:
                rows.append(r)


def line(label, rs, days=True):
    if not rs:
        return
    spent = sum(r["spent"] for r in rs); pnl = sum(r["pnl"] for r in rs)
    byday = defaultdict(lambda: [0.0, 0.0])
    for r in rs:
        byday[r["day"]][0] += r["pnl"]; byday[r["day"]][1] += r["spent"]
    v = [a / b for a, b in byday.values()]
    mu = sum(v) / len(v); sd = (sum((x - mu) ** 2 for x in v) / max(1, len(v) - 1)) ** 0.5
    t = mu / sd * math.sqrt(len(v)) if sd else 0
    lost = sum(r["pnl"] < 0 for r in rs)
    print(f"  {label:18s} {len(rs):5d} bets  lost {lost:4d} ({lost/len(rs)*100:4.1f}%)  {pnl/spent*100:+6.2f}c per $1  "
          f"${pnl:+8.2f} on ${spent:9,.0f}  days up {sum(x > 0 for x in v):4d}/{len(v):4d}  t {t:+5.1f}"
          + (f"  worst day ${min(a for a, _ in byday.values()):+.2f}" if days else ""))


print(f"Wendy on 2 years of morning trades: {LO*100:.1f}-{HI*100:.1f}c, {START:g}:00-{END:g}:00 city time, "
      f"2-minute looks, 110 s bids, harsh fills (queue {QUEUE}), ${CAP:g} a market")
line("all", rows)
print("by year (Nov-Oct):")
for y in sorted({(r["day"][0] + (r["day"][1] >= 11)) for r in rows}):
    line(f"to Oct {y}", [r for r in rows if r["day"][0] + (r["day"][1] >= 11) == y])
print("by season:")
for se in ("winter", "spring", "summer", "fall"):
    line(se, [r for r in rows if SEASON[r["day"][1]] == se])
print("by city:")
for s in TZ:
    line(s[6:], [r for r in rows if r["s"] == s])
print("by price:")
for a, b in ((0.92, 0.95), (0.95, 0.97), (0.97, 0.99), (0.99, 0.995)):
    line(f"{a*100:.0f}-{b*100:.1f}c", [r for r in rows if a <= r["price"] < b])
print("by month:")
months = sorted({r["day"][:2] for r in rows})
for ym in months:
    line(f"{ym[0]}-{ym[1]:02d}", [r for r in rows if r["day"][:2] == ym], days=False)
print("by city and year:")
for s in TZ:
    for y in (2025, 2026):
        line(f"{s[6:]} to Oct {y}", [r for r in rows if r["s"] == s and r["day"][0] + (r["day"][1] >= 11) == y])
