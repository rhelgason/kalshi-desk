"""
Second-by-second recorder for the fast-bot study.

Writes one JSON line per event to OUT (gzip):
  {"k":"spot","t":..., "p":...}                Coinbase BTC-USD trades (websocket)
  {"k":"book","t":..., "tk":..., "y":[[p,s]..], "n":[[p,s]..]}   Kalshi book ~1/s
  {"k":"trade", ...raw kalshi trade}           Kalshi tape, polled every 2s
  {"k":"mkt", ...}                             market metadata when a window opens
"""
import asyncio, gzip, json, sys, time
import httpx, websockets

OUT = sys.argv[1]
HOURS = float(sys.argv[2]) if len(sys.argv) > 2 else 8
K = "https://api.elections.kalshi.com/trade-api/v2"
f = gzip.open(OUT, "at")


def w(obj):
    f.write(json.dumps(obj, separators=(",", ":")) + "\n")


state = {"ticker": None, "close": 0, "last_spot": 0.0}


async def spot():
    while True:
        try:
            async with websockets.connect("wss://ws-feed.exchange.coinbase.com", max_size=2**22) as ws:
                await ws.send(json.dumps({"type": "subscribe", "product_ids": ["BTC-USD"], "channels": ["matches"]}))
                async for raw in ws:
                    m = json.loads(raw)
                    if m.get("type") in ("match", "last_match"):
                        now = time.time()
                        # one line per 100 ms is plenty
                        if now - state["last_spot"] >= 0.1:
                            state["last_spot"] = now
                            w({"k": "spot", "t": now, "p": float(m["price"])})
        except Exception as e:
            print("spot reconnect", e, flush=True)
            await asyncio.sleep(1)


async def markets(http):
    while True:
        try:
            r = await http.get(f"{K}/markets", params={"series_ticker": "KXBTC15M", "status": "open", "limit": 5})
            ms = sorted(r.json()["markets"], key=lambda m: m["close_time"])
            if ms and ms[0]["ticker"] != state["ticker"]:
                m = ms[0]
                state["ticker"] = m["ticker"]
                w({"k": "mkt", "t": time.time(), "tk": m["ticker"], "open": m["open_time"], "close": m["close_time"],
                   "strike": m.get("floor_strike")})
                print("now recording", m["ticker"], flush=True)
        except Exception as e:
            print("markets err", e, flush=True)
        await asyncio.sleep(5)


async def book(http):
    while True:
        tk = state["ticker"]
        t0 = time.time()
        if tk:
            try:
                r = await http.get(f"{K}/markets/{tk}/orderbook", params={"depth": 10})
                ob = r.json().get("orderbook_fp") or {}
                w({"k": "book", "t": (t0 + time.time()) / 2, "tk": tk, "y": ob.get("yes_dollars") or [],
                   "n": ob.get("no_dollars") or []})
            except Exception as e:
                print("book err", e, flush=True)
        await asyncio.sleep(max(0, 0.5 - (time.time() - t0)))


async def tape(http):
    seen = set()
    while True:
        tk = state["ticker"]
        if tk:
            try:
                r = await http.get(f"{K}/markets/trades", params={"ticker": tk, "limit": 200})
                for t in reversed(r.json().get("trades") or []):
                    if t["trade_id"] not in seen:
                        seen.add(t["trade_id"])
                        w({"k": "trade", "t": time.time(), **t})
            except Exception as e:
                print("tape err", e, flush=True)
        await asyncio.sleep(2)


async def main():
    async with httpx.AsyncClient(timeout=10) as http:
        tasks = [asyncio.create_task(c) for c in (spot(), markets(http), book(http), tape(http))]
        end = time.time() + HOURS * 3600
        while time.time() < end:
            await asyncio.sleep(30)
            f.flush()
        for t in tasks:
            t.cancel()
    f.close()


asyncio.run(main())
