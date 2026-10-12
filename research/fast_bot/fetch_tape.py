"""Download the KXBTC15M trade tape for the last N days, one gz file per market."""
import asyncio, gzip, json, os, sys
from datetime import datetime, timedelta, timezone
import httpx

K = "https://api.elections.kalshi.com/trade-api/v2"
DAYS = float(sys.argv[1])
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)
stats = {"ok": 0, "429": 0}


RATE = float(os.environ.get("RATE", 6))
_next = [0.0]


async def get(http, url, params):
    for i in range(30):
        loop = asyncio.get_running_loop()
        wait = _next[0] - loop.time()
        _next[0] = max(_next[0], loop.time()) + 1 / RATE
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            r = await http.get(url, params=params)
            if r.status_code == 429:
                stats["429"] += 1
                await asyncio.sleep(0.5)
                continue
            stats["ok"] += 1
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError:
            await asyncio.sleep(1 + i)
    raise RuntimeError(url)


async def markets(http):
    since = datetime.now(timezone.utc) - timedelta(days=DAYS)
    out, cur = [], None
    while True:
        d = await get(http, f"{K}/markets", {"series_ticker": "KXBTC15M", "status": "settled", "limit": 1000,
                                             **({"cursor": cur} if cur else {})})
        page = d["markets"]
        out += page
        cur = d.get("cursor")
        if not cur or not page or page[-1]["close_time"] < since.isoformat():
            break
    return [m for m in out if m["close_time"] >= since.isoformat().replace("+00:00", "Z")]


async def tape(http, m, sem):
    path = f"{OUT}/{m['ticker']}.json.gz"
    if os.path.exists(path):
        return
    async with sem:
        rows, cur = [], None
        while True:
            d = await get(http, f"{K}/markets/trades", {"ticker": m["ticker"], "limit": 1000,
                                                       **({"cursor": cur} if cur else {})})
            for t in d["trades"]:
                rows.append([t["created_time"], t["taker_outcome_side"], float(t["yes_price_dollars"]),
                             float(t["count_fp"])])
            cur = d.get("cursor")
            if not cur or not d["trades"]:
                break
        meta = {k: m.get(k) for k in ("ticker", "open_time", "close_time", "result", "floor_strike",
                                      "expiration_value", "volume_fp")}
        with gzip.open(path + ".tmp", "wt") as f:
            json.dump({"m": meta, "trades": rows}, f)
        os.rename(path + ".tmp", path)
        print(m["ticker"], len(rows), stats, flush=True)


async def main():
    async with httpx.AsyncClient(timeout=20) as http:
        ms = await markets(http)
        print(len(ms), "markets", flush=True)
        sem = asyncio.Semaphore(5)
        await asyncio.gather(*(tape(http, m, sem) for m in ms))


asyncio.run(main())
