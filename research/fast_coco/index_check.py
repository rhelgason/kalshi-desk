"""Can this Kalshi key read the official CF Benchmarks index? Tries the live value, the tick history (REST
passthrough) and the websocket feed for ETH, and prints what came back (no secrets).
    python research/fast_coco/index_check.py      (reads KALSHI_API_KEY_ID / KALSHI_PRIVATE_KEY_PATH)"""
import asyncio, json, sys, time
from datetime import datetime, timedelta, timezone

import httpx
import websockets

sys.path.insert(0, ".")
from desk.kalshi.auth import KalshiSigner  # noqa: E402

signer = KalshiSigner.from_env()
if not signer:
    sys.exit("No Kalshi key in the environment.")
hour = (datetime.now(timezone.utc) - timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
for host in ("https://api.elections.kalshi.com", "https://external-api.kalshi.com"):
    for path, params in (("/trade-api/v2/cfbenchmarks/values", {"id": "ETHUSD_RTI"}),
                         ("/trade-api/v2/cfbenchmarks/history/values",
                          {"id": "ETHUSD_RTI", "timespan": "HOUR", "timestamp": hour.strftime("%Y-%m-%dT%H:%M:%S.000Z")})):
        try:
            r = httpx.get(host + path, params=params, headers=signer.headers("GET", path), timeout=30)
            body = r.text
            try:
                d = r.json(); body = json.dumps(d)[:300]
                pts = d.get("payload") if isinstance(d, dict) else None
                if isinstance(pts, list):
                    body += f" ... {len(pts)} points"
            except ValueError:
                body = body[:300]
            print(f"{host.split('//')[1]:28} {path.split('/v2')[1]:28} {r.status_code}  {body}")
        except httpx.HTTPError as e:
            print(host, path, "error", e)


async def ws():
    path = "/trade-api/ws/v2"
    async with websockets.connect("wss://api.elections.kalshi.com" + path, additional_headers=signer.headers("GET", path)) as s:
        await s.send(json.dumps({"id": 1, "cmd": "subscribe", "params": {"channels": ["cfbenchmarks_value"], "index_ids": ["ETHUSD_RTI"]}}))
        end = time.time() + 8
        while time.time() < end:
            try:
                m = json.loads(await asyncio.wait_for(s.recv(), 8))
            except asyncio.TimeoutError:
                break
            msg = m.get("msg") or {}
            print("websocket", m.get("type"), msg.get("index_id"), (msg.get("avg_60s_data") or {}).get("value"), msg.get("code") or "")

asyncio.run(ws())
