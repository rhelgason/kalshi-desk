"""
Turn fetch.py / fetch_archive.py output into a history store the bot reads (desk/backtest/store.py),
with each minute's bid low and ask high kept so `desk seed-season` can fill the twins' resting bids.

    python to_store.py data/ ../../data/history-full.db
"""
import gzip
import glob
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, "../..")
from desk.paper.ledger import Ledger  # noqa: E402

SRC, DEST = sys.argv[1], sys.argv[2]


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


led = Ledger(DEST)
n = 0
for path in sorted(glob.glob(f"{SRC}/KX*15M-*.json.gz")):
    series = path.rsplit("/", 1)[-1].split("-")[0]
    rows = []
    for tk, m in json.load(gzip.open(path, "rt")).items():
        if m["result"] not in ("yes", "no") or not m["c"]:
            continue
        market = {"ticker": tk, "event_ticker": m.get("event_ticker") or tk.rsplit("-", 1)[0],
                  "strike_type": m.get("strike_type") or "greater_or_equal", "floor_strike": m.get("strike"),
                  "cap_strike": None, "open_time": iso(m["open"]), "close_time": iso(m["close"]),
                  "result": m["result"], "settlement_value_dollars": None, "expiration_value": None,
                  "status": "finalized"}
        # fetch rows are [ts, bid, ask, bid_low, ask_high, volume]; the store keeps [ts, bid, ask, volume, bid_low, ask_high]
        candles = [[t, b, a, v, lo, hi] for t, b, a, lo, hi, v in m["c"]]
        rows.append((tk, series, m["close"], json.dumps({"m": market, "c": candles}, separators=(",", ":"))))
    led.db.executemany("INSERT INTO market_history(ticker, series, close_ts, data) VALUES (?, ?, ?, ?)"
                       " ON CONFLICT(ticker) DO NOTHING", rows)
    led.db.commit()
    n += len(rows)
    print(path.rsplit("/", 1)[-1], len(rows), flush=True)
print(n, "markets in", DEST)
