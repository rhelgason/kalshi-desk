"""Sadie's resting-bid idea in every sampled market, on a clock that can't see the outcome (2026-10-28).

scan.py measured time back from each market's last trade, which leaks the result (the loser stops trading, and late
trades come after the game is decided), so every group looked like +5c at 92-97c. Here the clock is each market's
scheduled time from refs.py. At ref - A, take the side whose last trade (within 3 h) is in LO..HI, rest a bid at
that price, and let trades until ref - B fill it with harsh rules (through our price fills in full, at it gives
QUEUE of it), $CAP per market, held to the settle, after Kalshi's maker fee where the series charges one.
t is clustered by day.
    python research/other_markets/fixed_clock.py data/other        env QUEUE (0.3), CAP (10)"""
import gzip, json, math, os, sys
from collections import defaultdict

D = sys.argv[1]
QUEUE, CAP = float(os.environ.get("QUEUE", "0.3")), float(os.environ.get("CAP", "10"))
REF = json.load(open(os.path.join(D, "refs.json")))
H, M = 3600, 60
GROUPS = {   # group: (series, windows as (A, B) seconds before ref)
    "NFL/college football": (("KXNFLGAME", "KXNCAAFGAME"), ((10*H, 5*H), (5*H, 3*H), (3*H, 2*H), (2*H, 1*H), (1*H, 0), (0, -2*H))),
    "baseball": (("KXMLBGAME",), ((10*H, 4*H), (4*H, 3*H), (3*H, 2*H), (2*H, 1*H), (1*H, 0), (0, -2*H))),
    "basketball": (("KXNBAGAME",), ((10*H, 4*H), (4*H, 3*H), (3*H, 2*H), (2*H, 1*H), (1*H, 0), (0, -2*H))),
    "tennis": (("KXATPMATCH", "KXWTAMATCH", "KXATPCHALLENGERMATCH"), ((10*H, 4*H), (4*H, 2*H), (2*H, 1*H), (1*H, 0), (0, -2*H))),
    "weather": (("KXHIGHNY", "KXHIGHLAX", "KXHIGHCHI", "KXHIGHMIA", "KXHIGHAUS", "KXHIGHDEN"), ((30*H, 22*H), (22*H, 16*H), (16*H, 12*H), (12*H, 8*H), (8*H, 4*H))),
    "gold/oil/euro 15-min": (("KXGOLD15M", "KXWTI15M", "KXEURUSD15M"), ((15*M, 11*M), (11*M, 9*M), (9*M, 7*M), (7*M, 5*M), (5*M, 3*M))),
    "S&P/Nasdaq hourly": (("KXINXU", "KXNASDAQ100U"), ((60*M, 30*M), (30*M, 15*M), (15*M, 5*M))),
    "gas prices daily": (("KXAAAGASD",), ((30*H, 20*H), (20*H, 12*H), (12*H, 6*H))),
    "Trump mentions": (("KXTRUMPMENTION",), ((48*H, 24*H), (24*H, 6*H), (6*H, 1*H))),
    "Trump approval": (("KXTRUMPAPPROVE",), ((72*H, 24*H), (24*H, 6*H), (6*H, 1*H))),
    "Rotten Tomatoes": (("KXRT",), ((72*H, 24*H), (24*H, 6*H), (6*H, 1*H))),
}
BANDS = ((0.50, 0.70), (0.70, 0.85), (0.85, 0.92), (0.92, 0.97), (0.97, 0.995))


def load(series):
    out = []
    for s in series:
        p = os.path.join(D, f"{s}.jsonl.gz")
        with gzip.open(p, "rt") as fh:
            for line in fh:
                try:
                    m = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if m["ticker"] in REF and m["t"]:
                    m["s"] = s; out.append(m)
    return out


def run(markets, a, b, lo, hi):
    out = []
    for m in markets:
        t_look, t_stop = REF[m["ticker"]] - a, REF[m["ticker"]] - b
        mult = m.get("fee_mult") or 1
        maker_fee = "maker" in (m.get("fee_type") or "")
        best = {"yes": None, "no": None}
        for t, yp, n, taker, *_ in m["t"]:
            if t >= t_look:
                break
            side, p = (("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp))
            best[side] = (p, t)
        pick = [(s, v[0]) for s, v in best.items() if v and lo <= v[0] < hi and t_look - v[1] < 3 * H]
        if not pick:
            continue
        side, price = pick[0]
        spent = got = 0.0
        for t, yp, n, taker, *_ in m["t"]:
            if t < t_look + 1:
                continue
            if t > t_stop or spent >= CAP:
                break
            s2, p = (("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp))
            if s2 != side:
                continue
            q = n if p < price - 1e-9 else n * QUEUE if abs(p - price) < 1e-9 else 0
            q = min(q, (CAP - spent) / price)
            if q >= 0.01:
                spent += q * price; got += q
        if spent > 0:
            fee = got * 0.0175 * mult * price * (1 - price) if maker_fee else 0.0
            out.append({"day": int(REF[m["ticker"]] // 86400), "spent": spent,
                        "pnl": (got if m["result"] == side else 0) - spent - fee})
    return out


def show(label, rows):
    if len(rows) < 30:
        return
    days = sorted({r["day"] for r in rows}); half = days[len(days) // 2]
    c = lambda rs: sum(r["pnl"] for r in rs) / max(1e-9, sum(r["spent"] for r in rs)) * 100
    byday = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        byday[r["day"]][0] += r["pnl"]; byday[r["day"]][1] += r["spent"]
    tot = sum(v[1] for v in byday.values()); r0 = sum(v[0] for v in byday.values()) / tot
    se = math.sqrt(sum((p - r0 * s) ** 2 for p, s in byday.values())) / tot
    t = r0 / se if se else 0
    h1, h2 = c([r for r in rows if r["day"] < half]), c([r for r in rows if r["day"] >= half])
    star = "*" if t > 2.5 and min(h1, h2) > 0 else " "
    lost = sum(r["pnl"] < 0 for r in rows) / len(rows) * 100
    print(f"  {star} {label:10s} {len(rows):4d} bets lost {lost:4.1f}%  {c(rows):+6.2f}c per $1 (t {t:+4.1f}) halves "
          f"{h1:+6.2f}/{h2:+6.2f}  ${sum(r['pnl'] for r in rows)/len(days):+.2f}/day over {len(days)} days")


fmt = lambda x: f"{x/H:.0f}h" if abs(x) >= H else (f"{x/M:.0f}m" if x else "0")
print(f"Resting bids, fixed clock (scheduled time = ref), harsh fills, ${CAP:.0f} cap, after maker fees. * = t > 2.5 and both halves up")
for g, (series, windows) in GROUPS.items():
    mk = load(series)
    print(f"\n=== {g} ({len(mk)} markets; sampled tape, so fills are undercounted)")
    for a, b in windows:
        print(f" bid at ref-{fmt(a)}, fills until ref-{fmt(b)}:")
        for lo, hi in BANDS:
            show(f"{lo*100:.0f}-{hi*100:.0f}c", run(mk, a, b, lo, hi))
