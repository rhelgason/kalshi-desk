"""A sampled trade tape for any Kalshi series, for the cross-market scan (2026-10-27).

For each series: settled markets that closed in the last DAYS days, at most PER markets (seeded random sample; for
paired markets like "Team A wins" / "Team B wins", one per event). For each market, up to SLICES pages of 1,000
trades: its last 7 days of trading cut into SLICES equal slices, the newest page of each. Busy markets are sampled,
quiet ones come in full. Resumable.
    python research/other_markets/sample_tape.py DAYS PER OUTDIR SERIES...    env RATE (req/s, 8), SLICES (8)
Writes OUTDIR/SERIES.jsonl.gz, one market per line:
    {"ticker", "event", "open", "end", "result", "volume", "fee_type", "fee_mult",
     "t": [[unix_s, yes_price, count, taker_side, slice, slice_full], ...]}
slice_full = 1 when that slice came back in full (so its trades are all of them, not a sample)."""
import asyncio, gzip, json, os, random, sys, time
from datetime import datetime

import httpx

K = "https://api.elections.kalshi.com/trade-api/v2"
DAYS, PER, OUT, SERIES = float(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4:]
SLICES = int(os.environ.get("SLICES", "8"))
ts = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None
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
    k = 0
    while True:
        await lim.wait()
        try:
            r = await http.get(K + path, params=params)
        except httpx.HTTPError:
            await asyncio.sleep(3); continue
        stats["req"] += 1
        if r.status_code == 429:
            stats["429"] += 1; k += 1; await asyncio.sleep(min(60, 2 ** min(k, 6))); continue
        if r.status_code >= 500:
            await asyncio.sleep(3); continue
        r.raise_for_status()
        return r.json()


async def series(http, s):
    path = f"{OUT}/{s}.jsonl.gz"
    done = set()
    if os.path.exists(path):
        try:
            with gzip.open(path, "rt") as fh:
                for line in fh:
                    done.add(json.loads(line)["ticker"])
        except (EOFError, OSError, json.JSONDecodeError):
            pass
    info = (await get(http, f"/series/{s}", {})).get("series", {})
    since, ms, cur = int(time.time() - DAYS * 86400), [], None
    while True:
        d = await get(http, "/markets", {"series_ticker": s, "status": "settled", "min_close_ts": since, "limit": 1000,
                                         **({"cursor": cur} if cur else {})})
        ms += d.get("markets") or []; cur = d.get("cursor")
        if not cur or not d.get("markets"):
            break
    ms = [m for m in ms if m.get("result") in ("yes", "no") and float(m.get("volume_fp") or 0) > 0]
    rng = random.Random(s)
    rng.shuffle(ms)
    seen, pick = set(), []
    for m in ms:                       # one market per event: paired markets are mirror images
        if m["event_ticker"] in seen and s.endswith(("GAME", "MATCH")):
            continue
        seen.add(m["event_ticker"]); pick.append(m)
    pick = [m for m in pick[:PER] if m["ticker"] not in done]
    print(s, len(ms), "settled,", len(pick), "to fetch,", len(done), "saved", flush=True)
    out, lock, n, t0 = gzip.open(path, "at"), asyncio.Lock(), 0, time.time()
    sem = asyncio.Semaphore(4)

    async def one(m):
        nonlocal n
        close = ts(m["close_time"]); exp = ts(m.get("expected_expiration_time")) or close
        end = min(close, exp + 6 * 3600); start = max(ts(m.get("open_time")) or end - 7 * 86400, end - 7 * 86400)
        width = (end - start) / SLICES
        tr = []
        async with sem:
            for i in range(SLICES):
                a, b = int(start + i * width), int(start + (i + 1) * width)
                d = await get(http, "/markets/trades", {"ticker": m["ticker"], "limit": 1000, "min_ts": a, "max_ts": b})
                got = d.get("trades") or []
                full = 0 if d.get("cursor") and len(got) == 1000 else 1
                tr += [[round(ts(t["created_time"]), 3), float(t["yes_price_dollars"]), float(t["count_fp"]),
                        t.get("taker_outcome_side") or t["taker_side"], i, full] for t in got]
        line = json.dumps({"ticker": m["ticker"], "event": m["event_ticker"], "open": start, "end": end,
                           "result": m["result"], "volume": float(m.get("volume_fp") or 0),
                           "fee_type": info.get("fee_type"), "fee_mult": float(info.get("fee_multiplier") or 1),
                           "t": sorted(tr)}, separators=(",", ":"))
        async with lock:
            out.write(line + "\n"); n += 1
            if n % 100 == 0:
                out.flush(); print(s, n, "of", len(pick), round(time.time() - t0), "s", stats, flush=True)

    await asyncio.gather(*(one(m) for m in pick))
    out.close()
    print(s, "saved", n, round(time.time() - t0), "s", stats, flush=True)


async def main():
    os.makedirs(OUT, exist_ok=True)
    async with httpx.AsyncClient(timeout=60, limits=httpx.Limits(max_connections=8)) as http:
        for s in SERIES:
            await series(http, s)
    print("ALLDONE", flush=True)


asyncio.run(main())
