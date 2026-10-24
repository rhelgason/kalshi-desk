"""
Markets older than Kalshi's historical cutoff (~2 months), from the archive endpoints.
Archived candles come one market per request, so this is the slow part (resumable by month).

    python fetch_archive.py KXBTC15M data/ [oldest YYYY-MM-DD]

Writes data/<SERIES>-<YYYY-MM>-a.json.gz in the same format as fetch.py.
"""
import asyncio, gzip, json, os, sys, time
from collections import defaultdict
import httpx
from fetch import get, row, ts

SERIES, OUT = sys.argv[1], sys.argv[2]
OLDEST = sys.argv[3] if len(sys.argv) > 3 else "2000-01-01"


async def main():
    t0 = time.time()
    async with httpx.AsyncClient(timeout=60, limits=httpx.Limits(max_connections=12)) as http:
        ms, cur = [], None
        while True:
            d = await get(http, "/historical/markets", {"series_ticker": SERIES, "limit": 1000, **({"cursor": cur} if cur else {})})
            ms += d.get("markets") or []
            cur = d.get("cursor")
            if ms:
                print(SERIES, "archive:", len(ms), "markets, back to", ms[-1]["close_time"], flush=True)
            if not cur or not d.get("markets") or ms[-1]["close_time"] < OLDEST:
                break
        by = defaultdict(list)
        for m in ms:
            if m.get("result") in ("yes", "no") and m["close_time"] >= OLDEST:
                by[m["close_time"][:7]].append(m)
        sem = asyncio.Semaphore(6)
        for key in sorted(by, reverse=True):  # newest first
            path = f"{OUT}/{SERIES}-{key}-a.json.gz"
            if os.path.exists(path):
                continue
            out = {}

            async def one(m):
                async with sem:
                    d = await get(http, f"/historical/markets/{m['ticker']}/candlesticks",
                                  {"start_ts": ts(m["open_time"]) - 60, "end_ts": ts(m["close_time"]), "period_interval": 1})
                out[m["ticker"]] = [r for r in map(row, d.get("candlesticks") or []) if r]

            await asyncio.gather(*(one(m) for m in by[key]))
            data = {m["ticker"]: {"open": ts(m["open_time"]), "close": ts(m["close_time"]), "result": m["result"],
                                  "strike": m.get("floor_strike"), "c": out.get(m["ticker"], [])} for m in by[key]}
            with gzip.open(path + ".tmp", "wt") as fh:
                json.dump(data, fh)
            os.replace(path + ".tmp", path)
            print(SERIES, key, len(data), "archived markets,", sum(len(v["c"]) for v in data.values()), "candles,",
                  round(time.time() - t0), "s", flush=True)


asyncio.run(main())
