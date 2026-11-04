"""Full morning trade tape for the daily-high weather markets, years back (2026-10-31).

Kalshi moves markets settled before its cutoff (GET /historical/cutoff) to /historical/markets and /historical/trades;
newer ones are on /markets and /markets/trades. Before 2025 the series were HIGHNY etc. (no KX). For every settled
market of a day in the last DAYS days this saves ALL trades from 18:00 the evening before to 13:00 on the day (city
time), which covers Wendy's hours (midnight to 11 am) plus the lead-in for a last price. Resumable.
    python research/other_markets/wx_history.py DAYS OUTDIR [SERIES...]     env RATE (req/s, 5)
Writes OUTDIR/SERIES.jsonl.gz (SERIES = the KX name), one market per line, the shape wx_maker.py reads:
    {"ticker", "event", "result", "t": [[unix_s, yes_price, count, taker_side], ...]}"""
import asyncio, gzip, json, os, sys, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

K = "https://api.elections.kalshi.com/trade-api/v2"
DAYS, OUT = float(sys.argv[1]), sys.argv[2]
TZ = {"KXHIGHNY": "America/New_York", "KXHIGHLAX": "America/Los_Angeles", "KXHIGHCHI": "America/Chicago",
      "KXHIGHMIA": "America/New_York", "KXHIGHAUS": "America/Chicago", "KXHIGHDEN": "America/Denver"}
# More cities (2026-11-03): daily highs Kalshi added in 2026, and daily lows in Wendell's six cities
MORE = {"KXHIGHPHIL": "America/New_York", "KXHIGHTATL": "America/New_York", "KXHIGHTBOS": "America/New_York",
        "KXHIGHTDC": "America/New_York", "KXHIGHTNOLA": "America/Chicago", "KXHIGHTHOU": "America/Chicago",
        "KXHIGHTMIN": "America/Chicago", "KXHIGHTOKC": "America/Chicago", "KXHIGHTSATX": "America/Chicago",
        "KXHIGHTDAL": "America/Chicago", "KXHIGHTPHX": "America/Phoenix", "KXHIGHTLV": "America/Los_Angeles",
        "KXHIGHTSAN": "America/Los_Angeles", "KXHIGHTSEA": "America/Los_Angeles", "KXHIGHTSFO": "America/Los_Angeles",
        "KXLOWTNYC": "America/New_York", "KXLOWTLAX": "America/Los_Angeles", "KXLOWTCHI": "America/Chicago",
        "KXLOWTMIA": "America/New_York", "KXLOWTAUS": "America/Chicago", "KXLOWTDEN": "America/Denver"}
TZ |= MORE
SERIES = sys.argv[3:] or list(TZ)
MON = {m: i for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}
ts = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
stats = {"req": 0, "429": 0}


class Limiter:
    def __init__(self, rate):
        self.gap, self.next, self.lock = 1 / rate, time.monotonic(), asyncio.Lock()

    async def wait(self):
        async with self.lock:
            now = time.monotonic(); t = max(now, self.next); self.next = t + self.gap
        await asyncio.sleep(max(0, t - now))


lim = Limiter(float(os.environ.get("RATE", "5")))


async def get(http, path, params):
    k429 = 0
    while True:
        await lim.wait()
        try:
            r = await http.get(K + path, params=params, timeout=30)
            stats["req"] += 1
            if r.status_code == 429:
                stats["429"] += 1; k429 += 1
                await asyncio.sleep(min(30, 2 ** k429)); continue
            r.raise_for_status()
            return r.json()
        except (httpx.TransportError, httpx.HTTPStatusError) as e:
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
                return {}
            await asyncio.sleep(3)


async def pages(http, path, params, key):
    cur = None
    while True:
        j = await get(http, path, {**params, **({"cursor": cur} if cur else {})})
        yield j.get(key, [])
        cur = j.get("cursor")
        if not cur or not j.get(key):
            return


def window(event, zone):
    """18:00 the evening before to 13:00 on the day, city time, as unix seconds."""
    code = event.split("-")[1]
    day = datetime(2000 + int(code[:2]), MON[code[2:5]], int(code[5:7]), tzinfo=ZoneInfo(zone))
    return int((day - timedelta(hours=6)).timestamp()), int((day + timedelta(hours=13)).timestamp())


async def main():
    os.makedirs(OUT, exist_ok=True)
    since = time.time() - DAYS * 86400
    async with httpx.AsyncClient() as http:
        cutoff = ts((await get(http, "/historical/cutoff", {}))["market_settled_ts"])
        for s in SERIES:
            path = os.path.join(OUT, f"{s}.jsonl.gz")
            done = set()
            if os.path.exists(path):
                with gzip.open(path, "rt") as fh:
                    for line in fh:
                        try:
                            done.add(json.loads(line)["ticker"])
                        except json.JSONDecodeError:
                            pass
            todo = []
            for name, mpath in ((s, "/markets"), (s, "/historical/markets"), (s[2:], "/historical/markets")):
                p = {"series_ticker": name, "limit": 1000} | ({"status": "settled"} if mpath == "/markets" else {})
                async for ms in pages(http, mpath, p, "markets"):
                    for m in ms:
                        if m.get("result") in ("yes", "no") and ts(m["close_time"]) >= since and m["ticker"] not in done:
                            todo.append((m, mpath != "/markets"))
            todo = list({m["ticker"]: (m, h) for m, h in todo}.values())
            print(s, f"{len(todo)} to fetch, {len(done)} saved", flush=True)
            t0 = time.time()

            async def one(m, hist):
                lo, hi = window(m["event_ticker"], TZ[s])
                tp = "/historical/trades" if hist else "/markets/trades"
                out = []
                async for tr in pages(http, tp, {"ticker": m["ticker"], "min_ts": lo, "max_ts": hi, "limit": 1000}, "trades"):
                    for x in tr:
                        yp = float(x.get("yes_price_dollars") or x.get("yes_price", 0) / 100)
                        n = float(x.get("count_fp") or x.get("count", 0))
                        out.append([ts(x["created_time"]), round(yp, 4), n, x["taker_side"]])
                out.sort()
                return {"ticker": m["ticker"], "event": m["event_ticker"], "result": m["result"], "t": out}

            with gzip.open(path, "at") as fh:
                for i in range(0, len(todo), 40):
                    for rec in await asyncio.gather(*(one(m, h) for m, h in todo[i:i + 40])):
                        fh.write(json.dumps(rec) + "\n")
                    fh.flush()
                    print(s, f"{min(i + 40, len(todo))} of {len(todo)}", int(time.time() - t0), "s", stats, flush=True)
    print("ALLDONE", flush=True)


asyncio.run(main())
