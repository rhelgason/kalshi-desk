"""
Hourly Hazel's replay library (11-19): her live rule (a look every 2 minutes, 2-29 minutes before the hour, a favourite
at 92-99.5c, one tick over the side's last price, 110 s bids, no coin check, QUEUE share of trades at our price) on every
strike of bitcoin's hourly ladder (KXBTCD), with NO size limit, so each strike says what a bid of any size would have
filled and made. Same format as the coins' library (research/forecast/library.py): one window per strike, stamped with
its close, so the model's window cap shares each hour with the coins closing at the same moment.

    python research/forecast/hazel_library.py OUT.json.gz data/tape_hourly data/tape_hourly3 data/tape_hourly4
"""
import gzip, json, os, sys

sys.path.insert(0, os.path.dirname(__file__))
import library as L  # the coins' replay, reused with Hazel's settings

L.A, L.B, L.LO, L.HI, L.CHECK = 120, 1740, 0.92, 0.995, False


def markets(path):
    with gzip.open(path, "rt") as fh:
        try:
            for line in fh:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
        except (EOFError, OSError):  # a tape still downloading ends mid-stream
            return


def main(out, tapes):
    seen, wins = set(), []
    for d in tapes:
        for m in markets(os.path.join(d, "KXBTCD.jsonl.gz")):
            if m["ticker"] in seen or m.get("result") not in ("yes", "no") or not m.get("t"):
                continue
            seen.add(m["ticker"])
            fl, held, _ = L.replay(m, None)
            if not fl:
                wins.append([m["close"], 0]); continue
            won = held == m["result"]
            curve = []
            for c in L.CAPS:
                spent = got = 0.0
                for q, p in fl:
                    take = min(q, (c - spent) / p)
                    if take < 0.01:
                        break
                    spent += take * p; got += take
                curve.append([round(spent, 2), round((got if won else 0) - spent, 3)])
            wins.append([m["close"], 1, curve, None, None, None])
    bet = [w for w in wins if w[1]]
    days = (max(w[0] for w in wins) - min(w[0] for w in wins)) / 86400
    print(f"{len(seen)} strikes, {len(bet)} bet, {len(bet) / days:.0f} a day over {days:.0f} days")
    for i, c in enumerate(L.CAPS):
        s = sum(w[2][i][0] for w in bet); p = sum(w[2][i][1] for w in bet)
        half = sorted(w[0] for w in bet)[len(bet) // 2]
        h = [(sum(w[2][i][1] for w in bet if (w[0] < half) == k) / max(1e-9, sum(w[2][i][0] for w in bet if (w[0] < half) == k)))
             for k in (True, False)]
        print(f"  bid ${c:>6}: fills ${s / len(bet):8.2f} a strike on average, {100 * p / s:+.2f}c per $1"
              f" (halves {100 * h[0]:+.2f} / {100 * h[1]:+.2f})")
    with gzip.open(out, "wt") as f:
        json.dump({"caps": L.CAPS, "coins": {"BTCD": wins}}, f)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
