"""
Every settled 15-minute market for a coin series, with 1-minute candles, as far back as Kalshi has them.

    python fetch.py KXBTC15M data/    (resumable: finished months are kept)

Writes data/<SERIES>-<YYYY-MM>.json.gz: {ticker: {meta..., "c": [[ts, bid, ask, bid_low, ask_high, volume], ...]}}
Public market data: no API key needed. Kalshi allows ~20 reads a second on the basic tier.
"""
import asyncio, gzip, json, os, sys, time
from collections import defaultdict
from datetime import datetime, timezone
import httpx

K = "https://api.elections.kalshi.com/trade-api/v2"
SERIES, OUT = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("", "")


def ts(s):
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def f(x):
    return float(x) if x not in (None, "") else None


async def get(http, path, params):
    for i in range(60):
        try:
            r = await http.get(K + path, params=params)
        except httpx.HTTPError:
            await asyncio.sleep(2)
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            await asyncio.sleep(1 + i * 0.5)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(path)


async def list_markets(http):
    ms, cur = [], None
    while True:
        d = await get(http, "/markets", {"series_ticker": SERIES, "status": "settled", "limit": 1000,
                                         **({"cursor": cur} if cur else {})})
        ms += d["markets"]
        cur = d.get("cursor")
        if ms:
            print(SERIES, len(ms), "markets, back to", ms[-1]["close_time"], flush=True)
        if not cur or not d["markets"]:
            return [m for m in ms if m.get("result") in ("yes", "no")]


def row(c):
    yb, ya = c.get("yes_bid") or {}, c.get("yes_ask") or {}
    # live candles say close_dollars / volume_fp; archived ones plain close / volume
    vals = [f(yb.get("close_dollars", yb.get("close"))), f(ya.get("close_dollars", ya.get("close"))),
            f(yb.get("low_dollars", yb.get("low"))), f(ya.get("high_dollars", ya.get("high")))]
    if None in vals:
        return None
    vol = f(c.get("volume_fp")) if c.get("volume_fp") is not None else f(c.get("volume"))
    return [int(c["end_period_ts"]), *vals, vol or 0.0]


async def month(http, sem, key, ms):
    path = f"{OUT}/{SERIES}-{key}.json.gz"
    if os.path.exists(path):
        return
    ms = sorted(ms, key=lambda m: m["close_time"])
    out = {}
    chunks, i = [], 0
    while i < len(ms):  # batches of markets whose shared range x count stays under 10k candles
        j = i + 1
        while j < len(ms) and j - i < 100 and (j - i + 1) * ((ts(ms[j]["close_time"]) - ts(ms[i]["open_time"])) // 60 + 2) <= 9500:
            j += 1
        chunks.append(ms[i:j])
        i = j

    async def one(chunk):
        async with sem:
            d = await get(http, "/markets/candlesticks", {
                "market_tickers": ",".join(m["ticker"] for m in chunk),
                "start_ts": ts(chunk[0]["open_time"]) - 60, "end_ts": ts(chunk[-1]["close_time"]), "period_interval": 1})
        for item in d.get("markets") or []:
            out[item["market_ticker"]] = [r for r in map(row, item.get("candlesticks") or []) if r]

    await asyncio.gather(*(one(c) for c in chunks))
    data = {m["ticker"]: {"open": ts(m["open_time"]), "close": ts(m["close_time"]), "result": m["result"],
                          "strike": m.get("floor_strike"), "c": out.get(m["ticker"], [])} for m in ms}
    with gzip.open(path + ".tmp", "wt") as fh:
        json.dump(data, fh)
    os.replace(path + ".tmp", path)
    print(SERIES, key, len(ms), "markets,", sum(len(v["c"]) for v in data.values()), "candles", flush=True)


async def main():
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    async with httpx.AsyncClient(timeout=60, limits=httpx.Limits(max_connections=8)) as http:
        ms = await list_markets(http)
        by = defaultdict(list)
        for m in ms:
            by[m["close_time"][:7]].append(m)
        sem = asyncio.Semaphore(6)
        for key in sorted(by):
            await month(http, sem, key, by[key])
    print(SERIES, "done in", round(time.time() - t0), "s")


if __name__ == "__main__":
    asyncio.run(main())
