"""Per-market results of one naive maker rule (same fill model as maker_grid.py), for sizing studies.
Rule: in the window MIN..MAX seconds left, rest a bid at the best bid of the side priced LO..HI; harsh fills.
    python maker_bets.py TAPE_DIR OUT.json MIN MAX LO HI [COIN...]     env QUEUE (0.3), LAT (1.0)"""
import gzip, json, os, sys

TAPE, OUT = sys.argv[1], sys.argv[2]
A, B, LO, HI = int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6])
COINS = sys.argv[7:] or ["ETH", "SOL", "XRP", "DOGE"]
CAP, QUEUE, LAT = 10.0, float(os.environ.get("QUEUE", "0.3")), float(os.environ.get("LAT", "1.0"))
IMPROVE = int(os.environ.get("IMPROVE", "0"))   # ticks above the best bid (0 = join it)
MODE = os.environ.get("MODE", "follow")   # "cron": look every 120 s, post once for 110 s, never follow or pull
tick = lambda p: 0.001 if p >= 0.9 or p <= 0.1 else 0.01


def run(m, a=A, b=B, lo=LO, hi=HI):
    close = m["close"]
    if MODE == "cron":
        return run_cron(m, a, b, lo, hi)
    bid = None; spent = got = 0.0; held = None
    for t, yp, n, taker in m["t"]:
        side, p = (("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp))
        left = close - t
        if a < left <= b and bid and bid[2] <= t and side == bid[0] and spent < CAP:
            q = n if p < bid[1] - 1e-9 else n * QUEUE if abs(p - bid[1]) < 1e-9 else 0
            q = min(q, (CAP - spent) / bid[1])
            if q >= 0.01:
                spent += q * bid[1]; got += q; held = bid[0]
        if a < left <= b + LAT and lo <= p < hi and (held is None or side == held):
            price = round(min(p + IMPROVE * tick(p), 0.999), 4)
            if not bid or (bid[0], bid[1]) != (side, price):
                bid = (side, price, t + LAT)
        elif bid and bid[0] == side and not (lo <= p < hi):
            bid = None
    if spent <= 0:
        return None
    return {"close": close, "spent": round(spent, 4), "pnl": round((got if held == m["result"] else 0) - spent, 4),
            "avg": round(spent / got, 4)}


def run_cron(m, a, b, lo, hi):
    close = m["close"]
    best = {"yes": None, "no": None}; bid = None; spent = got = 0.0; held = None; looked = set()
    for t, yp, n, taker in m["t"]:
        side, p = (("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp))
        left = close - t
        slot = int(t - 5) // 120
        if slot not in looked and a < left <= b and (bid is None or bid[3] <= t):
            looked.add(slot)
            for s_ in ("yes", "no"):
                q = best[s_]
                if q and lo <= q < hi and (held is None or s_ == held):
                    price = round(min(q + IMPROVE * tick(q), 0.999), 4)
                    bid = (s_, price, slot * 120 + 5 + LAT, slot * 120 + 5 + 110)
        if bid and bid[2] <= t <= bid[3] and side == bid[0] and spent < CAP:
            qq = n if p < bid[1] - 1e-9 else n * QUEUE if abs(p - bid[1]) < 1e-9 else 0
            qq = min(qq, (CAP - spent) / bid[1])
            if qq >= 0.01:
                spent += qq * bid[1]; got += qq; held = bid[0]
        best[side] = p
    if spent <= 0:
        return None
    return {"close": close, "spent": round(spent, 4), "pnl": round((got if held == m["result"] else 0) - spent, 4),
            "avg": round(spent / got, 4)}


if __name__ == "__main__":
    out = []
    for coin in COINS:
        with gzip.open(os.path.join(TAPE, f"KX{coin}15M.jsonl.gz"), "rt") as f:
            for line in f:
                try:
                    m = json.loads(line)
                except json.JSONDecodeError:
                    continue
                r = run(m)
                if r:
                    r["coin"] = coin; r["ticker"] = m["ticker"]; out.append(r)
    json.dump(out, open(OUT, "w"))
    print(len(out), "bets", file=sys.stderr)
