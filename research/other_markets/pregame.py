"""Pre-game tape for the team-sport markets already sampled (2026-10-28): every trade from ref - 12 h to ref - 4 h
(ref = Kalshi's scheduled time, about start + 3-4 h, so this window is before the first pitch / kickoff / tip),
which sample_tape.py's newest-page slices miss. Then the same harsh resting-bid replay as fixed_clock.py.
    python research/other_markets/pregame.py data/other        writes data/other/pregame.json.gz"""
import gzip, json, math, os, sys, time
from collections import defaultdict
from datetime import datetime

import httpx

D = sys.argv[1]
K = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = ("KXNFLGAME", "KXNCAAFGAME", "KXMLBGAME", "KXNBAGAME", "KXATPMATCH", "KXWTAMATCH")
REF = json.load(open(os.path.join(D, "refs.json")))
OUT = os.path.join(D, "pregame.json.gz")
ts = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
H = 3600

tape = json.load(gzip.open(OUT, "rt")) if os.path.exists(OUT) else {}
meta = {}
http = httpx.Client(timeout=60)
for s in SERIES:
    with gzip.open(os.path.join(D, f"{s}.jsonl.gz"), "rt") as fh:
        for line in fh:
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            meta[m["ticker"]] = (s, m["result"], m.get("fee_mult") or 1)
            if m["ticker"] in tape:
                continue
            ref, rows, cur = REF[m["ticker"]], [], None
            for _ in range(15):
                for k in range(8):
                    r = http.get(K + "/markets/trades", params={"ticker": m["ticker"], "limit": 1000, "min_ts": int(ref - 12 * H),
                                                                "max_ts": int(ref - 4 * H), **({"cursor": cur} if cur else {})})
                    if r.status_code != 429:
                        break
                    time.sleep(2 ** k)
                d = r.json(); time.sleep(0.2)
                rows += [[round(ts(t["created_time"]), 3), float(t["yes_price_dollars"]), float(t["count_fp"]),
                          t.get("taker_outcome_side") or t["taker_side"]] for t in d.get("trades") or []]
                cur = d.get("cursor")
                if not cur or not d.get("trades"):
                    break
            tape[m["ticker"]] = sorted(rows)
    print(s, "done", flush=True)
    json.dump(tape, gzip.open(OUT, "wt"))

QUEUE, CAP = 0.3, 10.0


def run(group, a, b, lo, hi):
    out = []
    for tk, rows in tape.items():
        s, res, mult = meta[tk]
        if s not in group or not rows:
            continue
        t_look, t_stop = REF[tk] - a, REF[tk] - b
        best = {"yes": None, "no": None}
        for t, yp, n, taker in rows:
            if t >= t_look:
                break
            side, p = (("no", round(1 - yp, 4)) if taker == "yes" else ("yes", yp))
            best[side] = (p, t)
        pick = [(sd, v[0]) for sd, v in best.items() if v and lo <= v[0] < hi]
        if not pick:
            continue
        side, price = pick[0]
        spent = got = 0.0
        for t, yp, n, taker in rows:
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
            fee = got * 0.0175 * mult * price * (1 - price)
            out.append({"day": int(REF[tk] // 86400), "spent": spent, "pnl": (got if res == side else 0) - spent - fee})
    return out


def show(label, rows):
    if len(rows) < 20:
        return
    byday = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        byday[r["day"]][0] += r["pnl"]; byday[r["day"]][1] += r["spent"]
    tot = sum(v[1] for v in byday.values()); r0 = sum(v[0] for v in byday.values()) / tot
    se = math.sqrt(sum((p - r0 * sp) ** 2 for p, sp in byday.values())) / tot
    days = sorted(byday); half = days[len(days) // 2]
    c = lambda rs: sum(r["pnl"] for r in rs) / max(1e-9, sum(r["spent"] for r in rs)) * 100
    lost = sum(r["pnl"] < 0 for r in rows) / len(rows) * 100
    print(f"    {label:8s} {len(rows):4d} bets lost {lost:4.1f}%  {r0*100:+6.2f}c per $1 (t {r0/se if se else 0:+4.1f}) halves "
          f"{c([r for r in rows if r['day'] < half]):+6.2f}/{c([r for r in rows if r['day'] >= half]):+6.2f}")


print("\nPre-game resting bids (bid at ref-12h or ref-8h, fills until ref-4h), harsh fills, $10 cap, after maker fees")
for name, group in (("NFL/college", ("KXNFLGAME", "KXNCAAFGAME")), ("baseball", ("KXMLBGAME",)), ("basketball", ("KXNBAGAME",)),
                    ("tennis", ("KXATPMATCH", "KXWTAMATCH")), ("all team sports", ("KXNFLGAME", "KXNCAAFGAME", "KXMLBGAME", "KXNBAGAME"))):
    print(f"  {name} ({sum(1 for tk in tape if meta[tk][0] in group and tape[tk])} markets with pre-game trades)")
    for a in (12 * H, 8 * H):
        print(f"   bid at ref-{a//H}h:")
        for lo, hi in ((0.30, 0.50), (0.50, 0.70), (0.70, 0.85), (0.85, 0.92), (0.92, 0.99)):
            show(f"{lo*100:.0f}-{hi*100:.0f}c", run(group, a, 4 * H, lo, hi))
