"""KalshiClient against a fake HTTP server (httpx.MockTransport)."""

import json

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from desk.kalshi.auth import KalshiSigner
from desk.kalshi.client import KalshiAPIError, KalshiClient, TradingDisabledError
from desk.kalshi.models import Side


def client_with(handler, **kw) -> KalshiClient:
    kw.setdefault("requests_per_second", 1000)
    return KalshiClient(transport=httpx.MockTransport(handler), **kw)


async def test_paginates_markets():
    pages = {
        None: {"markets": [{"ticker": "A"}, {"ticker": "B"}], "cursor": "c2"},
        "c2": {"markets": [{"ticker": "C"}], "cursor": ""},
    }

    def handler(req: httpx.Request):
        assert req.url.path == "/trade-api/v2/markets"
        assert req.url.params["mve_filter"] == "exclude"
        return httpx.Response(200, json=pages[req.url.params.get("cursor")])

    async with client_with(handler) as c:
        markets = await c.get_markets()
    assert [m.ticker for m in markets] == ["A", "B", "C"]


async def test_retries_on_429_then_succeeds(monkeypatch):
    calls = {"n": 0}

    async def no_sleep(_):
        return None

    monkeypatch.setattr("desk.kalshi.client.asyncio.sleep", no_sleep)

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"error": "too many requests"})
        return httpx.Response(200, json={"exchange_active": True})

    async with client_with(handler) as c:
        assert (await c.get_exchange_status())["exchange_active"]
    assert calls["n"] == 3


async def test_4xx_raises_with_message():
    def handler(req):
        return httpx.Response(404, json={"error": {"code": "not_found", "message": "market not found"}})

    async with client_with(handler) as c:
        with pytest.raises(KalshiAPIError, match="market not found"):
            await c.get_market("NOPE")


async def test_orderbooks_batch(fixture_json):
    ob = fixture_json("orderbook.json")["orderbook_fp"]

    def handler(req):
        tickers = req.url.params["tickers"].split(",")
        return httpx.Response(200, json={"orderbooks": [{"ticker": t, "orderbook_fp": ob} for t in tickers]})

    async with client_with(handler) as c:
        books = await c.get_orderbooks(["A", "B"])
    assert set(books) == {"A", "B"}
    assert books["A"].best_ask(Side.YES) > 0


async def test_portfolio_requires_key():
    async with client_with(lambda r: httpx.Response(200, json={})) as c:
        with pytest.raises(KalshiAPIError, match="API key"):
            await c.get_balance()


async def test_signed_requests_and_balance():
    seen = {}

    def handler(req):
        seen.update(req.headers)
        return httpx.Response(200, json={"balance": 12345, "balance_dollars": "123.45", "portfolio_value": 0})

    signer = KalshiSigner("kid", ed25519.Ed25519PrivateKey.generate())
    async with client_with(handler, signer=signer) as c:
        assert await c.get_balance() == pytest.approx(123.45)
    assert seen["kalshi-access-key"] == "kid"
    assert "kalshi-access-signature" in seen


async def test_orders_blocked_unless_trading_enabled():
    signer = KalshiSigner("kid", ed25519.Ed25519PrivateKey.generate())
    async with client_with(lambda r: httpx.Response(201, json={}), signer=signer) as c:
        with pytest.raises(TradingDisabledError):
            await c.create_order("T", Side.YES, 1, 0.5)


async def test_buy_no_is_sent_as_yes_ask_at_complement():
    body = {}

    def handler(req):
        assert req.url.path == "/trade-api/v2/portfolio/events/orders"
        body.update(json.loads(req.content))
        return httpx.Response(201, json={"order_id": "o1", "fill_count": "0.00", "remaining_count": "3.00", "ts_ms": 1})

    signer = KalshiSigner("kid", ed25519.Ed25519PrivateKey.generate())
    async with client_with(handler, signer=signer, allow_trading=True) as c:
        await c.create_order("T", Side.NO, 3, 0.30)
    assert body["side"] == "ask"
    assert body["price"] == "0.7000"
    assert body["count"] == "3.00"
    assert body["time_in_force"] == "immediate_or_cancel"


async def test_fee_lookup_failure_is_not_remembered():
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(404, json={"error": {"message": "nope"}})
        return httpx.Response(200, json={"series": {"fee_type": "quadratic_with_maker_fees", "fee_multiplier": 1}})

    async with client_with(handler) as c:
        first = await c.get_fee_schedule("KXBTC15M")
        assert first.assumed and first.fee_type == "quadratic"
        second = await c.get_fee_schedule("KXBTC15M")  # asks again, and this time it's real
        assert not second.assumed and second.charges_maker_fees
        await c.get_fee_schedule("KXBTC15M")
    assert len(calls) == 2


async def test_shard_balances_transfer_and_order_lookup():
    """Crypto markets are paid from shard 2: read each shard, move cash there, and look orders up by market."""
    seen = []

    def handler(req):
        seen.append((req.method, req.url.path, dict(req.url.params), json.loads(req.content or b"null")))
        if req.url.path.endswith("/portfolio/balance"):
            return httpx.Response(200, json={"balance": 100000, "balance_breakdown": [
                {"balance": "1000.0000", "exchange_index": 0}, {"balance": "0.0000", "exchange_index": 2}]})
        if "/portfolio/orders/" in req.url.path:
            return httpx.Response(200, json={"order": {"order_id": "o1", "status": "resting"}})
        return httpx.Response(200, json={"transfer_id": "t1"})

    signer = KalshiSigner("kid", ed25519.Ed25519PrivateKey.generate())
    async with client_with(handler, signer=signer) as c:
        assert await c.get_shard_balances() == {0: 1000.0, 2: 0.0}
        await c.transfer_between_shards(1000.0, 0, 2)
        await c.set_target_allocation({2: 100})
        assert (await c.get_order("o1", "KXBTC15M-X"))["status"] == "resting"
    transfer = next(b for m, p, _, b in seen if p.endswith("/intra_exchange_instance_transfer"))
    assert transfer["amount"] == 10_000_000  # centicents
    assert (transfer["source_exchange_shard"], transfer["destination_exchange_shard"]) == (0, 2)
    alloc = next(b for m, p, _, b in seen if p.endswith("/target_balance_allocation"))
    assert alloc["allocations"] == [{"exchange_index": 2, "percent": 100}]
    assert seen[-1][2] == {"market_ticker": "KXBTC15M-X"}
