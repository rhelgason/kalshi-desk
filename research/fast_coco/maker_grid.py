"""Every naive maker strategy in the last 6 minutes: for each (time slice, price band), rest a bid at the best bid
of whichever side is in the band, re-posting LAT seconds after each change. Harsh fills: a trade AT our price gives
QUEUE of it, a trade THROUGH it fills us in full. $10 a market, one side per market.
    python maker_grid.py TAPE_DIR [COIN...]"""
import gzip, json, os, sys
from collections import defaultdict
from datetime import datetime, timezone

TAPE = sys.argv[1]
COINS = sys.argv[2:] or ["ETH", "SOL", "XRP", "DOGE"]
CAP, QUEUE, LAT = 10.0, float(os.environ.get("QUEUE", "0.3")), 1.0
SLICES = [(300, 360), (240, 300), (180, 240), (120, 180), (60, 120), (30, 60), (0, 30)]
BANDS = [(0.01, 0.05), (0.05, 0.15), (0.15, 0.35), (0.35, 0.65), (0.65, 0.85), (0.85, 0.94), (0.94, 0.97),
         (0.97, 0.99), (0.99, 0.996), (0.996, 1.0)]
out = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0, 0]))
for coin in COINS:
    with gzip.open(os.path.join(TAPE, f"KX{coin}15M.jsonl.gz"), "rt") as f:
        for line in f:
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            close = m["close"]
            day = datetime.fromtimestamp(close - 7 * 3600, timezone.utc).strftime("%Y-%m-%d")
            tr = [(t, *(("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp)), n) for t, yp, n, taker in m["t"]]
            for a, b in SLICES:
                for lo, hi in BANDS:
                    bid = None; spent = got = 0.0; held = None
                    for t, side, p, n in tr:          # a seller hit `side` at p (p was that side's best bid)
                        left = close - t
                        if a < left <= b and bid and bid[2] <= t and side == bid[0] and spent < CAP:
                            q = n if p < bid[1] - 1e-9 else n * QUEUE if abs(p - bid[1]) < 1e-9 else 0
                            q = min(q, (CAP - spent) / bid[1])
                            if q >= 0.01:
                                spent += q * bid[1]; got += q; held = bid[0]
                        if a < left <= b + LAT and lo <= p < hi and (held is None or side == held):
                            if not bid or (bid[0], bid[1]) != (side, p):
                                bid = (side, p, t + LAT)
                        elif bid and bid[0] == side and not (lo <= p < hi):
                            bid = None                   # the side left the band: pull
                    if spent > 0:
                        pnl = (got if held == m["result"] else 0) - spent
                        o = out[(a, b, lo, hi)][day]; o[0] += pnl; o[1] += spent; o[2] += 1; o[3] += pnl < 0
    print(coin, "done", file=sys.stderr, flush=True)

print("Per $1 (cents): ALL | first half / second half | last 7 days ; bets/day. * = positive in both halves and overall")
for a, b in SLICES:
    print(f"\n{a}-{b}s left")
    for lo, hi in BANDS:
        days = out[(a, b, lo, hi)]
        if not days:
            continue
        ds = sorted(days); half = ds[len(ds) // 2]
        f = lambda sel: sum(days[d][0] for d in sel) / max(1e-9, sum(days[d][1] for d in sel)) * 100
        allc, h1, h2, l7 = f(ds), f([d for d in ds if d < half]), f([d for d in ds if d >= half]), f(ds[-7:])
        n = sum(days[d][2] for d in ds)
        star = "*" if allc > 0 and h1 > 0 and h2 > 0 else " "
        print(f" {star} {lo:5.3f}-{hi:5.3f}: {allc:+6.2f} | {h1:+6.2f} / {h2:+6.2f} | {l7:+6.2f} ; {n/len(ds):5.1f}/day, "
              f"lost {sum(days[d][3] for d in ds)/n*100:5.1f}%")
