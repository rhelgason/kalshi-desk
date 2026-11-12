"""Kalshi trade tape for the final WINDOW minutes of every settled market, streamed to disk (resumable).
    python tape.py DAYS WINDOW_MIN OUTDIR SERIES...     env RATE (req/s, default 8), CONC (default 4),
        NEAR (hourly ladders: skip strikes more than this fraction from the coin's Binance price WINDOW_MIN before
        the close; they sit at 0c/100c the whole window and cost a request each), COIN (NEAR for a series not
        named KX<COIN>D, e.g. COIN=BTC for the KXBTC ranges)
Writes OUTDIR/SERIES.jsonl.gz, one market per line:
    {"ticker", "close", "result", "strike", "t": [[unix_seconds_float, yes_price, count, taker_side], ...]}
"""
import asyncio, gzip, json, os, sys, time
from datetime import datetime
import httpx

sys.path.insert(0, ".")
try:  # signed requests get the key's own rate limit instead of the IP's public one
    from desk.kalshi.auth import KalshiSigner
    SIGNER = KalshiSigner.from_env()
except ImportError:
    SIGNER = None

K = "https://api.elections.kalshi.com/trade-api/v2"
DAYS, WIN, OUT, SERIES = float(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4:]
ts = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
stats = {"req": 0, "429": 0}


class Limiter:
    def __init__(self, rate):
        self.gap, self.next, self.lock = 1 / rate, time.monotonic(), asyncio.Lock()

    async def wait(self):
        async with self.lock:
            now = time.monotonic(); t = max(now, self.next); self.next = t + self.gap
        await asyncio.sleep(max(0, t - now))


lim = Limiter(float(os.environ.get("RATE", "8")))


async def get(http, path, params):
    k429 = 0
    while True:
        await lim.wait()
        try:
            hdrs = SIGNER.headers("GET", "/trade-api/v2" + path) if SIGNER else {}
            r = await http.get(K + path, params=params, headers=hdrs)
        except httpx.HTTPError:
            await asyncio.sleep(3); continue
        stats["req"] += 1
        if r.status_code == 429:
            stats["429"] += 1; k429 += 1; await asyncio.sleep(min(60, 2 ** min(k429, 6))); continue
        if r.status_code >= 500:
            await asyncio.sleep(3); continue
        r.raise_for_status()
        return r.json()


async def series(http, s):
    path = f"{OUT}/{s}.jsonl.gz"
    done, good, torn = set(), [], False
    if os.path.exists(path):
        try:
            with gzip.open(path, "rt") as fh:
                for line in fh:
                    done.add(json.loads(line)["ticker"]); good.append(line)
        except (EOFError, OSError, json.JSONDecodeError):
            torn = True  # a torn last line from a crash: the market is fetched again
    if torn:  # rewrite cleanly, or everything appended after the tear can't be read back
        with gzip.open(path, "wt") as fh:
            fh.writelines(good)
    t0 = time.time(); since = int(time.time() - DAYS * 86400); ms, cur = [], None
    while True:
        d = await get(http, "/markets", {"series_ticker": s, "status": "settled", "min_close_ts": since, "limit": 1000,
                                         **({"cursor": cur} if cur else {})})
        ms += d.get("markets") or []; cur = d.get("cursor")
        if not cur or not d.get("markets"):
            break
    ms = [m for m in ms if m.get("result") in ("yes", "no") and float(m.get("volume_fp") or 0) > 0 and m["ticker"] not in done]
    if os.environ.get("NEAR") and (s.endswith("D") or os.environ.get("COIN")):
        sys.path.insert(0, os.path.dirname(__file__))
        from hourly_check import Binance
        v, near = Binance(os.environ.get("COIN") or s[2:-1]), float(os.environ["NEAR"])
        def close_to(m):  # a ladder's strike, or (hourly ranges, COIN=BTC) the nearer edge of the range
            px = v.get(int(ts(m["close_time"])) - WIN * 60)
            ks = [k for k in (m.get("floor_strike"), m.get("cap_strike")) if k]
            return px is None or not ks or min(abs(k / px - 1) for k in ks) <= near
        ms = [m for m in ms if close_to(m)]
    print(s, len(ms), "markets to fetch,", len(done), "already saved", flush=True)
    sem, n = asyncio.Semaphore(int(os.environ.get("CONC", "4"))), 0
    out = gzip.open(path, "at")
    lock = asyncio.Lock()

    async def one(m):
        nonlocal n
        tr, cur, close = [], None, int(ts(m["close_time"]))
        async with sem:
            while True:
                d = await get(http, "/markets/trades", {"ticker": m["ticker"], "limit": 1000, "min_ts": close - WIN * 60,
                                                         "max_ts": close + 60, **({"cursor": cur} if cur else {})})
                tr += [[round(ts(t["created_time"]), 3), float(t["yes_price_dollars"]), float(t["count_fp"]),
                        t.get("taker_outcome_side") or t["taker_side"]] for t in d.get("trades") or []]
                cur = d.get("cursor")
                if not cur or not d.get("trades"):
                    break
        line = json.dumps({"ticker": m["ticker"], "close": close, "result": m["result"], "strike": m.get("floor_strike"),
                           "t": sorted(tr)}, separators=(",", ":"))
        async with lock:
            out.write(line + "\n"); n += 1
            if n % 200 == 0:
                out.flush()
                print(s, n, "of", len(ms), round(time.time() - t0), "s", stats, flush=True)

    await asyncio.gather(*(one(m) for m in ms))
    out.close()
    print(s, "saved", n, "markets,", round(time.time() - t0), "s", stats, flush=True)


async def main():
    os.makedirs(OUT, exist_ok=True)
    async with httpx.AsyncClient(timeout=60, limits=httpx.Limits(max_connections=8)) as http:
        for s in SERIES:
            await series(http, s)
    print("ALLDONE", flush=True)


asyncio.run(main())
