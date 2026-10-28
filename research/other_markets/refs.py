"""Each sampled market's scheduled time (expected_expiration_time), which Kalshi sets before trading starts, so a
replay can run on a clock that knows nothing about the outcome (2026-10-28). Sports games: about the expected end
(MLB: start + 3 h). 15-minute markets: 5 minutes after the close.
    python research/other_markets/refs.py data/other        writes data/other/refs.json {ticker: unix_s}"""
import gzip, json, os, sys, time
from datetime import datetime

import httpx

D = sys.argv[1]
K = "https://api.elections.kalshi.com/trade-api/v2"
ts = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None
out = {}
for fn in sorted(os.listdir(D)):
    if not fn.endswith(".jsonl.gz"):
        continue
    s = fn.split(".")[0]
    want = set()
    with gzip.open(os.path.join(D, fn), "rt") as fh:
        for line in fh:
            try:
                want.add(json.loads(line)["ticker"])
            except json.JSONDecodeError:
                pass
    cur, since = None, int(time.time() - 70 * 86400)
    while True:
        for k in range(8):
            r = httpx.get(K + "/markets", params={"series_ticker": s, "status": "settled", "min_close_ts": since,
                                                  "limit": 1000, **({"cursor": cur} if cur else {})}, timeout=60)
            if r.status_code != 429:
                break
            time.sleep(2 ** k)
        d = r.json()
        for m in d.get("markets") or []:
            if m["ticker"] in want:
                out[m["ticker"]] = ts(m.get("expected_expiration_time") or m.get("occurrence_datetime")) or ts(m["close_time"])
        cur = d.get("cursor")
        if not cur or not d.get("markets"):
            break
        time.sleep(0.3)
    print(s, sum(t in out for t in want), "of", len(want), flush=True)
json.dump(out, open(os.path.join(D, "refs.json"), "w"))
