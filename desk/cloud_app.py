"""
Vercel entrypoint: a tiny ASGI app with one job.

    POST /api/tick   (Authorization: Bearer $TICK_SECRET)  -> run one desk tick
    GET  /api/health                                       -> "ok"

Supabase's pg_cron calls /api/tick every couple of minutes. No web framework,
to keep cold starts (and Vercel CPU time) small.
"""

from __future__ import annotations

import hmac
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


async def _send(send, status: int, body: dict) -> None:
    data = json.dumps(body, default=str).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(data)).encode())]})
    await send({"type": "http.response.body", "body": data})


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    if scope["type"] != "http":
        return

    path = scope.get("path", "")
    if path.endswith("/health"):
        return await _send(send, 200, {"ok": True})
    if not path.endswith("/tick"):
        return await _send(send, 404, {"error": "not found"})

    secret = os.environ.get("TICK_SECRET", "")
    auth = dict(scope.get("headers") or []).get(b"authorization", b"").decode()
    if not secret or not hmac.compare_digest(auth, f"Bearer {secret}"):
        return await _send(send, 401, {"error": "unauthorized"})

    from desk.cloud import run_cloud_tick

    try:
        result = await run_cloud_tick()
        await _send(send, 200, result)
    except Exception as e:  # report, don't crash the worker
        logging.exception("tick failed")
        await _send(send, 500, {"ok": False, "error": f"{type(e).__name__}: {e}"})
