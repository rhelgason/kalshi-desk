"""
Async Kalshi Trade API v2 client.

Public market data works without any keys. Portfolio endpoints need an API
key (see desk.kalshi.auth). Placing or cancelling orders additionally needs
`allow_trading=True`, so nothing can trade real money by accident.

Rate limits: Kalshi meters requests in "tokens" (most calls cost 10). The
Basic tier refills 200 read tokens/sec (about 20 requests/sec) and 100 write
tokens/sec. We default to a gentler 10 requests/sec and back off on HTTP 429.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from typing import Any, AsyncIterator, Optional

import httpx

from desk.kalshi.auth import KalshiSigner
from desk.kalshi.fees import FeeSchedule
from desk.kalshi.models import Event, Market, Orderbook, Side

logger = logging.getLogger(__name__)

API_PREFIX = "/trade-api/v2"
HOSTS = {
    "prod": "https://external-api.kalshi.com",
    "demo": "https://external-api.demo.kalshi.co",
}


class KalshiAPIError(Exception):
    def __init__(self, status: int, message: str, body: Any = None):
        super().__init__(f"Kalshi API {status}: {message}")
        self.status = status
        self.body = body


class TradingDisabledError(RuntimeError):
    pass


class RateLimiter:
    """Simple token bucket: `rate` requests per second, bursting up to `burst`."""

    def __init__(self, rate: float, burst: Optional[float] = None):
        self.rate = rate
        self.capacity = burst if burst is not None else rate
        self._tokens = self.capacity
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
                self._last = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await asyncio.sleep((1 - self._tokens) / self.rate)


class KalshiClient:
    def __init__(
        self,
        env: str = "prod",
        signer: Optional[KalshiSigner] = None,
        allow_trading: bool = False,
        requests_per_second: float = 10.0,
        timeout: float = 20.0,
        max_retries: int = 4,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        if env not in HOSTS:
            raise ValueError(f"env must be one of {list(HOSTS)}")
        self.env = env
        self.base_url = HOSTS[env] + API_PREFIX
        self.signer = signer
        self.allow_trading = allow_trading
        self.max_retries = max_retries
        self._limiter = RateLimiter(requests_per_second, burst=requests_per_second)
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": "desk/0.1"},
            transport=transport,
        )
        self._fee_cache: dict[str, FeeSchedule] = {}

    async def __aenter__(self) -> "KalshiClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Low-level request
    # ------------------------------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
        auth: bool = False,
    ) -> dict:
        url = self.base_url + path
        params = {k: v for k, v in (params or {}).items() if v is not None}
        headers: dict[str, str] = {}

        for attempt in range(self.max_retries + 1):
            await self._limiter.acquire()
            if auth or self.signer:
                if not self.signer:
                    raise KalshiAPIError(401, f"{path} needs an API key (set KALSHI_API_KEY_ID)")
                headers = self.signer.headers(method, API_PREFIX + path)
            try:
                resp = await self._http.request(method, url, params=params, json=json, headers=headers)
            except httpx.TransportError as e:
                if attempt >= self.max_retries:
                    raise
                wait = 0.5 * 2**attempt
                logger.warning("Kalshi %s %s network error (%s); retrying in %.1fs", method, path, e, wait)
                await asyncio.sleep(wait)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt >= self.max_retries:
                    raise KalshiAPIError(resp.status_code, resp.text[:200])
                wait = 0.5 * 2**attempt
                logger.warning("Kalshi %s %s -> %s; retrying in %.1fs", method, path, resp.status_code, wait)
                await asyncio.sleep(wait)
                continue

            if resp.status_code >= 400:
                try:
                    body = resp.json()
                except ValueError:
                    body = resp.text
                msg = body.get("error", body) if isinstance(body, dict) else body
                if isinstance(msg, dict):
                    msg = msg.get("message") or msg.get("code") or str(msg)
                raise KalshiAPIError(resp.status_code, str(msg)[:300], body)

            return resp.json() if resp.content else {}

        raise KalshiAPIError(0, "retries exhausted")  # pragma: no cover

    async def _paginate(
        self, path: str, key: str, params: dict, max_items: Optional[int] = None
    ) -> AsyncIterator[dict]:
        cursor = None
        seen = 0
        while True:
            data = await self.request("GET", path, params={**params, "cursor": cursor})
            for item in data.get(key) or []:
                yield item
                seen += 1
                if max_items is not None and seen >= max_items:
                    return
            cursor = data.get("cursor")
            if not cursor:
                return

    # ------------------------------------------------------------------
    # Public market data
    # ------------------------------------------------------------------

    async def get_exchange_status(self) -> dict:
        return await self.request("GET", "/exchange/status")

    async def get_series(self, series_ticker: str) -> dict:
        data = await self.request("GET", f"/series/{series_ticker}")
        return data.get("series") or {}

    async def get_fee_schedule(self, series_ticker: str) -> FeeSchedule:
        """Fee settings for a series (cached; they rarely change). Defaults if Kalshi can't be reached."""
        if series_ticker not in self._fee_cache:
            try:
                self._fee_cache[series_ticker] = FeeSchedule.from_series(await self.get_series(series_ticker))
            except (KalshiAPIError, httpx.TransportError) as e:
                # Not cached: a passing outage shouldn't fix the wrong fees in place for good
                logger.warning("Couldn't load fees for %s (%s); assuming defaults this time", series_ticker, e)
                return FeeSchedule(assumed=True)
        return self._fee_cache[series_ticker]

    async def get_events(
        self,
        series_ticker: Optional[str] = None,
        status: Optional[str] = "open",
        with_markets: bool = True,
        min_close_ts: Optional[int] = None,
        max_items: Optional[int] = None,
        page_size: int = 100,
    ) -> list[Event]:
        params = {
            "series_ticker": series_ticker,
            "status": status,
            "with_nested_markets": "true" if with_markets else None,
            "min_close_ts": min_close_ts,
            "limit": page_size,
        }
        return [Event.from_api(e) async for e in self._paginate("/events", "events", params, max_items)]

    async def get_event(self, event_ticker: str) -> Event:
        data = await self.request("GET", f"/events/{event_ticker}", params={"with_nested_markets": "true"})
        event = data.get("event") or {}
        if "markets" not in event and data.get("markets"):
            event = {**event, "markets": data["markets"]}
        return Event.from_api(event)

    async def get_markets(
        self,
        series_ticker: Optional[str] = None,
        event_ticker: Optional[str] = None,
        status: Optional[str] = None,
        min_close_ts: Optional[int] = None,
        max_close_ts: Optional[int] = None,
        tickers: Optional[list[str]] = None,
        exclude_multivariate: bool = True,
        max_items: Optional[int] = None,
        page_size: int = 1000,
    ) -> list[Market]:
        """
        List markets. Note Kalshi's filter rules: close-time filters can only be
        combined with status "closed" or no status at all.
        """
        params = {
            "series_ticker": series_ticker,
            "event_ticker": event_ticker,
            "status": status,
            "min_close_ts": min_close_ts,
            "max_close_ts": max_close_ts,
            "tickers": ",".join(tickers) if tickers else None,
            "mve_filter": "exclude" if exclude_multivariate else None,
            "limit": page_size,
        }
        return [Market.from_api(m) async for m in self._paginate("/markets", "markets", params, max_items)]

    async def get_market(self, ticker: str) -> Market:
        data = await self.request("GET", f"/markets/{ticker}")
        return Market.from_api(data.get("market") or {})

    async def get_orderbook(self, ticker: str, depth: Optional[int] = None) -> Orderbook:
        data = await self.request("GET", f"/markets/{ticker}/orderbook", params={"depth": depth})
        return Orderbook.from_api(ticker, data)

    async def get_orderbooks(self, tickers: list[str]) -> dict[str, Orderbook]:
        """Fetch many orderbooks, 100 tickers per request."""
        books: dict[str, Orderbook] = {}
        for i in range(0, len(tickers), 100):
            chunk = tickers[i : i + 100]
            data = await self.request("GET", "/markets/orderbooks", params={"tickers": ",".join(chunk)})
            for item in data.get("orderbooks") or []:
                books[item["ticker"]] = Orderbook.from_api(item["ticker"], item)
        return books

    async def get_candlesticks(self, tickers: list[str], start_ts: int, end_ts: int,
                               period_minutes: int = 1) -> dict[str, list[dict]]:
        """Price history for up to 100 markets per request (live, non-archived markets)."""
        out: dict[str, list[dict]] = {}
        for i in range(0, len(tickers), 100):
            data = await self.request("GET", "/markets/candlesticks", params={
                "market_tickers": ",".join(tickers[i:i + 100]),
                "start_ts": start_ts, "end_ts": end_ts, "period_interval": period_minutes,
            })
            for item in data.get("markets") or []:
                out[item["market_ticker"]] = item.get("candlesticks") or []
        return out

    async def get_trades(self, ticker: str, limit: int = 100, max_items: Optional[int] = None,
                         min_ts: Optional[int] = None) -> list[dict]:
        """Recent trades, newest first; with min_ts, only trades at or after that unix time."""
        params = {"ticker": ticker, "limit": limit, "min_ts": min_ts}
        return [t async for t in self._paginate("/markets/trades", "trades", params, max_items)]

    # ------------------------------------------------------------------
    # Portfolio (needs API key)
    # ------------------------------------------------------------------

    async def get_balance(self) -> float:
        """Available cash in dollars."""
        data = await self.request("GET", "/portfolio/balance", auth=True)
        if "balance_dollars" in data:
            return float(data["balance_dollars"])
        return float(data.get("balance", 0)) / 100

    async def get_shard_balances(self) -> dict[int, float]:
        """Cash on each exchange shard, in dollars. Kalshi checks an order against its market's shard only
        (crypto markets are on shard 2), so money on shard 0 can't buy bitcoin bets."""
        data = await self.request("GET", "/portfolio/balance", auth=True)
        return {int(b["exchange_index"]): float(b["balance"]) for b in data.get("balance_breakdown") or []}

    async def get_target_allocation(self) -> dict[int, int]:
        data = await self.request("GET", "/portfolio/target_balance_allocation", auth=True)
        return {int(a["exchange_index"]): int(a["percent"]) for a in data.get("allocations") or []}

    async def set_target_allocation(self, percents: dict[int, int]) -> dict:
        """Have Kalshi keep cash split across shards like this (it rebalances every ~10 seconds).
        Percentages must total 100; an empty dict turns rebalancing off."""
        body = {"allocations": [{"exchange_index": k, "percent": v} for k, v in sorted(percents.items())],
                "resting_margin_reservation": "sum"}
        return await self.request("POST", "/portfolio/target_balance_allocation", json=body, auth=True)

    async def transfer_between_shards(self, dollars: float, source: int, destination: int) -> dict:
        """Move cash from one exchange shard to another (processed by Kalshi shortly after)."""
        body = {"source": "event_contract", "destination": "event_contract",
                "amount": int(round(dollars * 10_000)),  # centicents
                "source_exchange_shard": source, "destination_exchange_shard": destination}
        logger.info("Moving $%.2f from shard %d to shard %d on %s", dollars, source, destination, self.env)
        return await self.request("POST", "/portfolio/intra_exchange_instance_transfer", json=body, auth=True)

    async def get_positions(self, settlement_status: Optional[str] = None) -> list[dict]:
        params = {"settlement_status": settlement_status, "limit": 1000}
        out = []
        cursor = None
        while True:
            data = await self.request("GET", "/portfolio/positions", params={**params, "cursor": cursor}, auth=True)
            out.extend(data.get("market_positions") or [])
            cursor = data.get("cursor")
            if not cursor:
                return out

    async def get_orders(self, ticker: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        params = {"ticker": ticker, "status": status, "limit": 1000}
        out = []
        cursor = None
        while True:
            data = await self.request("GET", "/portfolio/orders", params={**params, "cursor": cursor}, auth=True)
            out.extend(data.get("orders") or [])
            cursor = data.get("cursor")
            if not cursor:
                return out

    async def get_fills(self, ticker: Optional[str] = None, order_id: Optional[str] = None,
                        min_ts: Optional[int] = None, limit: int = 200) -> list[dict]:
        """Our own fills (newest first), optionally for one order or market, every page."""
        params = {"ticker": ticker, "order_id": order_id, "min_ts": min_ts, "limit": limit}
        out = []
        cursor = None
        while True:
            data = await self.request("GET", "/portfolio/fills", params={**params, "cursor": cursor}, auth=True)
            out.extend(data.get("fills") or [])
            cursor = data.get("cursor")
            if not cursor:
                return out

    async def get_order(self, order_id: str, ticker: Optional[str] = None) -> dict:
        """One order. Pass its market's ticker: Kalshi only finds orders off shard 0 when told the market."""
        params = {"market_ticker": ticker} if ticker else None
        data = await self.request("GET", f"/portfolio/orders/{order_id}", params=params, auth=True)
        return data.get("order") or {}

    # ------------------------------------------------------------------
    # Trading (needs API key AND allow_trading=True)
    # ------------------------------------------------------------------

    def _require_trading(self) -> None:
        if not self.allow_trading:
            raise TradingDisabledError(
                "Order placement is disabled. Create the client with allow_trading=True to trade."
            )

    async def create_order(
        self,
        ticker: str,
        side: Side,
        count: float,
        limit_price: float,
        time_in_force: str = "immediate_or_cancel",
        post_only: bool = False,
        reduce_only: bool = False,
        client_order_id: Optional[str] = None,
        expiration_ts: Optional[int] = None,
    ) -> dict:
        """
        Buy `count` contracts of `side` paying at most `limit_price` each.

        Kalshi's V2 order endpoint quotes everything from the YES side:
        buying NO at p is sent as an "ask" (sell YES) at 1 - p. Counts go in
        0.01-contract steps (rounded down). time_in_force is immediate_or_cancel,
        fill_or_kill or good_till_canceled (with expiration_ts for a timed order).
        The response carries order_id, fill_count, remaining_count and, if
        anything filled, average_fill_price and average_fee_paid.
        """
        self._require_trading()
        if not (0 < limit_price < 1):
            raise ValueError(f"limit_price must be between 0 and 1, got {limit_price}")
        count = math.floor(count * 100 + 1e-6) / 100
        if count <= 0:
            raise ValueError("count must be at least 0.01")

        if side is Side.YES:
            book_side, yes_price = "bid", limit_price
        else:
            book_side, yes_price = "ask", 1 - limit_price

        body = {
            "ticker": ticker,
            "client_order_id": client_order_id or str(uuid.uuid4()),
            "side": book_side,
            "count": f"{count:.2f}",
            "price": f"{yes_price:.4f}",
            "time_in_force": time_in_force,
            "self_trade_prevention_type": "taker_at_cross",
            "post_only": post_only,
            "reduce_only": reduce_only,
            "cancel_order_on_pause": True,
        }
        if expiration_ts is not None:
            body["expiration_time"] = expiration_ts
        logger.info("Placing order on %s: %s", self.env, body)
        return await self.request("POST", "/portfolio/events/orders", json=body, auth=True)

    async def cancel_order(self, order_id: str, ticker: str) -> dict:
        """Cancel one order. Cancelling is always allowed, even with trading switched off."""
        return await self.request(
            "DELETE", f"/portfolio/events/orders/{order_id}", params={"market_ticker": ticker}, auth=True
        )

    async def cancel_all_orders(self) -> dict:
        """Cancel every resting order on the account (the kill switch)."""
        return await self.request("DELETE", "/portfolio/events/orders", auth=True)
