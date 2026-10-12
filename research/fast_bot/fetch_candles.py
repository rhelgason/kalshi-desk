"""Full 1-minute candles (bid/ask/trade OHLC) for every settled KXBTC15M market in the last N days."""
import asyncio, gzip, json, sys, time
from datetime import datetime, timedelta, timezone
import httpx

K = "https://api.elections.kalshi.com/trade-api/v2"
DAYS = float(sys.argv[1])
OUT = sys.argv[2]


def ts(s):
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


async def get(http, url, params):
    for i in range(40):
        r = await http.get(url, params=params)
        if r.status_code == 429:
            await asyncio.sleep(1)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(url)


async def main():
    since = (datetime.now(timezone.utc) - timedelta(days=DAYS)).isoformat().replace("+00:00", "Z")
    async with httpx.AsyncClient(timeout=30) as http:
        ms, cur = [], None
        while True:
            d = await get(http, f"{K}/markets", {"series_ticker": "KXBTC15M", "status": "settled", "limit": 1000,
                                                 **({"cursor": cur} if cur else {})})
            ms += d["markets"]
            cur = d.get("cursor")
            print(len(ms), ms[-1]["close_time"], flush=True)
            if not cur or not d["markets"] or ms[-1]["close_time"] < since:
                break
        ms = sorted((m for m in ms if m["close_time"] >= since and m["result"] in ("yes", "no")),
                    key=lambda m: m["close_time"])
        out = {}
        i = 0
        while i < len(ms):
            j = i + 1  # grow the batch while markets x minutes of the shared range stays < 10k
            while j < len(ms) and j - i < 100:
                rng = (ts(ms[j]["close_time"]) - ts(ms[i]["open_time"])) // 60 + 2
                if (j - i + 1) * rng > 9500:
                    break
                j += 1
            chunk = ms[i:j]
            start = ts(chunk[0]["open_time"]) - 60
            end = ts(chunk[-1]["close_time"])
            d = await get(http, f"{K}/markets/candlesticks", {
                "market_tickers": ",".join(m["ticker"] for m in chunk), "start_ts": start, "end_ts": end,
                "period_interval": 1})
            for item in d.get("markets") or []:
                out[item["market_ticker"]] = item.get("candlesticks") or []
            i += len(chunk)
            print(i, len(ms), flush=True)
        meta = {m["ticker"]: {k: m.get(k) for k in ("open_time", "close_time", "result", "floor_strike",
                                                    "expiration_value")} for m in ms}
        with gzip.open(OUT, "wt") as f:
            json.dump({"meta": meta, "candles": out}, f)


asyncio.run(main())
