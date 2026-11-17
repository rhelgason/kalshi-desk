"""
How much money one 15-minute window can take (11-17, for the prediction model). Replays Sadie's rule on Kalshi's real
trade tape the way the bot bids (a look every 2 minutes, a resting bid at the favourite's best bid, 92-99c, 5-9
minutes left; QUEUE share of trades at our exact price, LAT seconds before a bid counts), once per market with no
size limit, then asks: with at most $C in that window, how much fills and what does it make?

    python research/forecast/capacity.py OUT.json TAPE.jsonl.gz [...]

Out: per coin and per cap C, windows bet, dollars filled, profit, profit per $1, and the share of windows where the
cap was the limit (more money would have filled more).
"""
import gzip, json, os, sys

A, B, LO, HI = 300, 540, 0.92, 0.99
QUEUE, LAT = float(os.environ.get("QUEUE", "0.3")), float(os.environ.get("LAT", "1.0"))
CAPS = [10, 25, 50, 100, 200, 400, 800, 1600, 3200, 6400]


def fills(m):
    """Every fill our bid could have had in this market, in order: (contracts, price), plus the side held."""
    close = m["close"]
    best = {"yes": None, "no": None}; bid = None; held = None; looked = set(); out = []
    for t, yp, n, taker in m["t"]:
        side, p = (("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp))
        left = close - t
        slot = int(t - 5) // 120
        if slot not in looked and A < left <= B and (bid is None or bid[3] <= t):
            looked.add(slot)
            for s_ in ("yes", "no"):
                q = best[s_]
                if q and LO <= q < HI and (held is None or s_ == held):
                    bid = (s_, q, slot * 120 + 5 + LAT, slot * 120 + 5 + 110)
        if bid and bid[2] <= t <= bid[3] and side == bid[0]:
            qq = n if p < bid[1] - 1e-9 else n * QUEUE if abs(p - bid[1]) < 1e-9 else 0
            if qq >= 0.01:
                out.append((qq, bid[1])); held = bid[0]
        best[side] = p
    return out, held


def main(out_path, tapes):
    report = {}
    for path in tapes:
        coin = os.path.basename(path).split("15M")[0].replace("KX", "")
        rows = {c: {"windows": 0, "spent": 0.0, "pnl": 0.0, "capped": 0} for c in CAPS}
        first = last = None; markets = 0
        with gzip.open(path, "rt") as fh:
            for line in fh:
                m = json.loads(line)
                if not m.get("result") or not m.get("t"):
                    continue
                markets += 1
                first = m["close"] if first is None else min(first, m["close"]); last = max(last or 0, m["close"])
                fl, held = fills(m)
                if not fl:
                    continue
                won = held == m["result"]
                for c in CAPS:
                    spent = got = 0.0
                    for q, p in fl:
                        take = min(q, (c - spent) / p)
                        if take < 0.01:
                            break
                        spent += take * p; got += take
                    r = rows[c]
                    r["windows"] += 1; r["spent"] += spent; r["pnl"] += (got if won else 0) - spent
                    r["capped"] += spent >= c - 0.01
        days = (last - first) / 86400 if first else 0
        report[coin] = {"days": round(days, 1), "markets": markets, "caps": {
            c: {"windows": r["windows"], "spent_per_day": round(r["spent"] / days, 2) if days else 0,
                "avg_fill": round(r["spent"] / r["windows"], 2) if r["windows"] else 0,
                "per_dollar": round(r["pnl"] / r["spent"], 4) if r["spent"] else 0,
                "capped_share": round(r["capped"] / r["windows"], 3) if r["windows"] else 0}
            for c, r in rows.items()}}
        print(coin, report[coin]["days"], "days", {c: (v["avg_fill"], v["per_dollar"], v["capped_share"]) for c, v in report[coin]["caps"].items()}, flush=True)
    json.dump(report, open(out_path, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
