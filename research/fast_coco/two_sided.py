"""Two-sided market making: rest a bid on BOTH sides (each at its best bid, joined) while the market's YES price is in
LO..HI and MIN..MAX seconds are left. A YES and a NO that both fill pay $1 together whatever happens, so the pair
locks in 1 - (yes + no). One-sided fills carry the risk. Harsh fills as in maker_grid.py; $CAP per side.
Optional SKEW: stop bidding a side once it holds SKEW dollars more than the other (inventory control).
    python two_sided.py TAPE_DIR MIN MAX LO HI [COIN...]     env CAP (10), SKEW (inf), QUEUE (0.3)"""
import gzip, json, os, sys
from collections import defaultdict
from datetime import datetime, timezone

TAPE = sys.argv[1]
A, B, LO, HI = int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
COINS = sys.argv[6:] or ["ETH", "SOL", "XRP", "DOGE"]
CAP = float(os.environ.get("CAP", "10")); SKEW = float(os.environ.get("SKEW", "inf"))
QUEUE, LAT = float(os.environ.get("QUEUE", "0.3")), 1.0
days = defaultdict(lambda: [0.0, 0.0, 0, 0.0])   # pnl, spent, markets, paired dollars
for coin in COINS:
    with gzip.open(os.path.join(TAPE, f"KX{coin}15M.jsonl.gz"), "rt") as f:
        for line in f:
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            close = m["close"]
            bid = {"yes": None, "no": None}; spent = {"yes": 0.0, "no": 0.0}; got = {"yes": 0.0, "no": 0.0}
            yes_px = None
            for t, yp, n, taker in m["t"]:
                side, p = (("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp))
                left = close - t
                b = bid[side]
                if A < left <= B and b and b[1] <= t and spent[side] < CAP and spent[side] - spent["no" if side == "yes" else "yes"] < SKEW:
                    q = n if p < b[0] - 1e-9 else n * QUEUE if abs(p - b[0]) < 1e-9 else 0
                    q = min(q, (CAP - spent[side]) / b[0])
                    if q >= 0.01:
                        spent[side] += q * b[0]; got[side] += q
                yes_px = yp
                if A < left <= B + LAT and LO <= yes_px <= HI:
                    if not b or b[0] != p:
                        bid[side] = (p, t + LAT)
                elif not (LO <= yes_px <= HI):
                    bid = {"yes": None, "no": None}
            s = spent["yes"] + spent["no"]
            if s > 0:
                win = m["result"]
                pnl = got[win] - s
                d = datetime.fromtimestamp(close - 7 * 3600, timezone.utc).strftime("%Y-%m-%d")
                pair = min(got["yes"], got["no"])
                a = days[d]; a[0] += pnl; a[1] += s; a[2] += 1; a[3] += pair
ds = sorted(days); half = ds[len(ds) // 2]
f = lambda sel: sum(days[d][0] for d in sel) / max(1e-9, sum(days[d][1] for d in sel)) * 100
tot = [sum(days[d][i] for d in ds) for i in range(4)]
print(f"{A}-{B}s, YES {LO}-{HI}, skew {SKEW}: {tot[2]/len(ds):.0f} markets/day, {f(ds):+.2f}c per $1 "
      f"(halves {f([d for d in ds if d < half]):+.2f} / {f([d for d in ds if d >= half]):+.2f}, last 7 {f(ds[-7:]):+.2f}), "
      f"${tot[0]/len(ds):+.2f}/day, {sum(1 for d in ds if days[d][0] > 0)}/{len(ds)} days up, paired contracts {tot[3]/len(ds):.0f}/day")
