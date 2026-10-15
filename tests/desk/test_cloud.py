"""Cloud runner pieces: state round-trips, the lease, and the CPU budget governor."""

from datetime import datetime, timedelta, timezone

import pytest

from desk.cloud import _budget_check, dump_accounts, dump_feed, load_accounts, load_feed
from desk.feeds.crypto import CryptoFeed, UnderlyingQuote
from desk.kalshi.models import Side
from desk.paper.account import PaperAccount
from desk.paper.ledger import Ledger
from desk.strategies import WhaleWatcherWalt


def test_accounts_round_trip():
    a = PaperAccount("s", 1000)
    a.apply_fill("T", Side.YES, 10, 0.40, 0.17)
    a.apply_fill("U", Side.NO, 5, 0.30, 0.05)
    a.settle("U", 0.0)
    b = load_accounts(dump_accounts({"s": a}))["s"]
    assert b.cash == pytest.approx(a.cash)
    assert b.positions["T"].yes == 10 and b.positions["T"].yes_fees == pytest.approx(0.17)
    assert (b.realized_pnl, b.settled_wins, b.trades) == (a.realized_pnl, a.settled_wins, a.trades)


def test_zero_cash_account_stays_at_zero():
    a = PaperAccount("s", 100)
    a.cash = 0.0
    assert load_accounts(dump_accounts({"s": a}))["s"].cash == 0.0


def test_feed_round_trip_keeps_recent_history():
    feed = CryptoFeed(("BTC",))
    now = datetime.now(timezone.utc)
    feed._merge_history("BTC", [(now - timedelta(minutes=200), 1.0), (now - timedelta(minutes=10), 2.0)])
    feed.quotes["BTC"] = UnderlyingQuote("BTC", 2.0, implied_vol=0.4, realized_vol=0.2)
    feed._vol_refreshed["BTC"] = now
    fresh = CryptoFeed(("BTC",))
    load_feed(fresh, dump_feed(feed))
    assert [p for _, p in fresh.history["BTC"]] == [2.0]  # old point trimmed
    assert fresh.quotes["BTC"].realized_vol == 0.2
    assert fresh._vol_refreshed["BTC"] == now


def test_a_saved_price_goes_stale_and_unwatched_coins_are_dropped():
    feed = CryptoFeed(("BTC", "ETH"))
    now = datetime.now(timezone.utc)
    feed.quotes["BTC"] = UnderlyingQuote("BTC", 2.0, fetched_at=now - timedelta(minutes=3))
    feed.quotes["ETH"] = UnderlyingQuote("ETH", 3.0, fetched_at=now)
    fresh = CryptoFeed(("BTC",))  # the desk stopped watching ETH
    load_feed(fresh, dump_feed(feed))
    assert set(fresh.quotes) == {"BTC"}
    assert fresh.quotes["BTC"].fetched_at == now - timedelta(minutes=3)  # not "now": it's an old price
    assert fresh.fresh_quotes(now) == {}
    # A state saved before prices carried a time counts as stale too
    old = CryptoFeed(("BTC",))
    load_feed(old, {"quotes": {"BTC": {"spot": 1.0, "iv": None, "rv": None}}})
    assert old.fresh_quotes() == {}


async def test_failed_price_sources_mean_no_price_not_an_old_one():
    import httpx

    feed = CryptoFeed(("BTC",), transport=httpx.MockTransport(lambda req: httpx.Response(503)))
    feed.quotes["BTC"] = UnderlyingQuote("BTC", 2.0, fetched_at=datetime.now(timezone.utc) - timedelta(minutes=2))
    try:
        assert await feed.refresh() == {}
    finally:
        await feed.close()


def test_lease_blocks_second_holder_until_released_or_stale():
    led = Ledger(":memory:")
    assert led.try_lease("tick", 60)
    assert not led.try_lease("tick", 60)
    led.release_lease("tick")
    assert led.try_lease("tick", 60)
    assert led.try_lease("tick", 0)  # a stale lease can be taken over


def test_budget_governor_paces_the_month():
    now = datetime(2026, 10, 16, tzinfo=timezone.utc)  # about half way through October
    ok, b = _budget_check({"budget": {"month": "2026-10", "cpu_seconds": 1.0 * 3600}}, now)
    assert ok and 1.8 < b["projected_cpu_hours"] < 2.2
    ok, _ = _budget_check({"budget": {"month": "2026-10", "cpu_seconds": 2.0 * 3600}}, now)
    assert not ok  # on pace for ~4h
    ok, b = _budget_check({"budget": {"month": "2026-09", "cpu_seconds": 99999}}, now)
    assert ok and b["cpu_seconds"] == 0  # new month resets


def test_walt_remembers_followed_trades():
    w = WhaleWatcherWalt()
    w._followed = {"a", "b"}
    w2 = WhaleWatcherWalt()
    w2.set_state(w.get_state())
    assert w2._followed == {"a", "b"}


async def _call(path, headers=()):
    from desk.cloud_app import app

    sent = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(msg):
        sent.append(msg)

    await app({"type": "http", "path": path, "headers": list(headers)}, receive, send)
    return sent[0]["status"]


async def test_cloud_app_health_and_auth(monkeypatch):
    monkeypatch.setenv("TICK_SECRET", "s3cret")
    assert await _call("/api/health") == 200
    assert await _call("/api/tick") == 401
    assert await _call("/api/tick", [(b"authorization", b"Bearer wrong")]) == 401
    assert await _call("/nope") == 404
