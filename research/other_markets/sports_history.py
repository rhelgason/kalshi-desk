"""End-of-game trade tape for the game-winner markets, years back (2026-11-02), for Final Whistle Fiona.

Same plumbing as wx_history.py (/historical/* for markets settled before Kalshi's cutoff, /markets/* after; old
series names without KX). For every settled market that closed in the last DAYS days this saves ALL trades from
BEFORE hours before its scheduled end (`expected_expiration_time`, set before the game) to AFTER hours after it,
which covers Fiona's hours (3 h before to 2 h after) plus a lead-in for a last price. One market per game.
Resumable.
    python research/other_markets/sports_history.py DAYS OUTDIR [SERIES...]     env RATE (req/s, 5), BEFORE (3.5), AFTER (2)
Writes OUTDIR/SERIES.jsonl.gz, one market per line:
    {"ticker", "event", "result", "ref": unix_s, "t": [[unix_s, yes_price, count, taker_side], ...]}"""
import asyncio, gzip, json, os, sys, time
from datetime import datetime

import httpx

K = "https://api.elections.kalshi.com/trade-api/v2"
DAYS, OUT = float(sys.argv[1]), sys.argv[2]
SERIES = sys.argv[3:] or ["KXNFLGAME", "KXNCAAFGAME", "KXNBAGAME", "KXMLBGAME", "KXNHLGAME"]
BEFORE, AFTER = float(os.environ.get("BEFORE", "3.5")) * 3600, float(os.environ.get("AFTER", "2")) * 3600
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
                        if (m.get("result") in ("yes", "no") and m.get("expected_expiration_time")
                                and ts(m["close_time"]) >= since and m["ticker"] not in done):
                            todo.append((m, mpath != "/markets"))
            todo = list({m["ticker"]: (m, h) for m, h in todo}.values())
            # One market per game: "A wins" and "B wins" mirror each other (a 98c favorite is in both), and a big
            # game holds ~60k trades in these hours, so the second market doubles the download for nothing
            seen = {r.rsplit("-", 1)[0] for r in done}
            todo = [x for x in todo if x[0]["event_ticker"] not in seen and not seen.add(x[0]["event_ticker"])]
            print(s, f"{len(todo)} to fetch, {len(done)} saved", flush=True)
            t0 = time.time()

            async def one(m, hist):
                ref = ts(m["expected_expiration_time"])
                lo, hi = int(ref - BEFORE), int(ref + AFTER)
                tp = "/historical/trades" if hist else "/markets/trades"
                out = []
                async for tr in pages(http, tp, {"ticker": m["ticker"], "min_ts": lo, "max_ts": hi, "limit": 1000}, "trades"):
                    for x in tr:
                        yp = float(x.get("yes_price_dollars") or x.get("yes_price", 0) / 100)
                        n = float(x.get("count_fp") or x.get("count", 0))
                        out.append([ts(x["created_time"]), round(yp, 4), n, x["taker_side"]])
                out.sort()
                return {"ticker": m["ticker"], "event": m["event_ticker"], "result": m["result"], "ref": ref, "t": out}

            with gzip.open(path, "at") as fh:
                for i in range(0, len(todo), 40):
                    for rec in await asyncio.gather(*(one(m, h) for m, h in todo[i:i + 40])):
                        fh.write(json.dumps(rec) + "\n")
                    fh.flush()
                    print(s, f"{min(i + 40, len(todo))} of {len(todo)}", int(time.time() - t0), "s", stats, flush=True)
    print("ALLDONE", flush=True)


asyncio.run(main())
