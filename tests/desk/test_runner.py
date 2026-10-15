"""The full desk loop against a fake Kalshi client: discover, trade, settle."""

import math
from datetime import timedelta

import pytest

from desk.config import DeskConfig
from desk.kalshi.fees import FeeSchedule
from desk.kalshi.models import Event, Side
from desk.paper.ledger import Ledger
from desk.runner import Desk
from desk.strategies import CoverArb, LongshotFade
from desk.strategies.base import Leg, Snapshot, TradeIntent

from tests.desk.conftest import NOW, book_for, make_market


class FakeClient:
    def __init__(self, events, broad):
        self.events = {e.event_ticker: e for e in events}
        self.broad = broad
        self.results: dict[str, str] = {}

    async def get_events(self, series_ticker=None, status=None, with_markets=True, **kw):
        return [Event(e.event_ticker, e.series_ticker, strike_date=NOW.replace(year=2999))
                for e in self.events.values() if e.series_ticker == series_ticker]

    async def get_event(self, ticker):
        return self.events[ticker]

    async def get_fee_schedule(self, series):
        return FeeSchedule()

    async def get_markets(self, tickers=None, **kw):
        if tickers is None:
            return self.broad
        everything = {m.ticker: m for e in self.events.values() for m in e.markets}
        everything.update({m.ticker: m for m in self.broad})
        out = []
        for t in tickers:
            m = everything[t]
            m.result = self.results.get(t, "")
            out.append(m)
        return out

    async def get_orderbooks(self, tickers):
        everything = {m.ticker: m for e in self.events.values() for m in e.markets}
        everything.update({m.ticker: m for m in self.broad})
        return {t: book_for(everything[t]) for t in tickers}


@pytest.fixture
def desk_and_client():
    lo = make_market("ARB-T100", "greater", floor=100, yes_bid=0.48, yes_ask=0.50, series="ARB", event="ARB-1")
    hi = make_market("ARB-T110", "greater", floor=110, yes_bid=0.60, yes_ask=0.62, series="ARB", event="ARB-1")
    event = Event("ARB-1", "ARB", markets=[lo, hi])
    longshot = make_market("LS-1", "custom", yes_bid=0.05, yes_ask=0.06, event="LS", close_in=timedelta(days=2))

    # The runner checks strike_date against "now"; pin the horizon wide open
    cfg = DeskConfig(crypto_series=["ARB"], crypto_horizon_hours=24 * 365 * 1000, liquidity_share=1.0,
                     starting_cash=100, pool_cash=200)
    client = FakeClient([event], [longshot])
    desk = Desk(cfg, client, [CoverArb(), LongshotFade()], Ledger(":memory:"))
    return desk, client


async def test_tick_trades_and_settles(desk_and_client, monkeypatch):
    desk, client = desk_and_client
    # Freeze the clock the strategies see so fixture close times are in the future
    monkeypatch.setattr("desk.runner._now", lambda: NOW)

    results = await desk.tick()
    filled = {r.intent.strategy for r in results if r.filled}
    assert filled == {"cover_arb", "longshot_fade"}

    carl = desk.accounts["cover_arb"]
    assert carl.position("ARB-T100")[0] > 0 and carl.position("ARB-T110")[1] > 0

    # Price settles between the strikes: both arb legs pay
    client.results = {"ARB-T100": "yes", "ARB-T110": "no", "LS-1": "no"}
    desk._last_settle = None
    await desk.settle_check()
    assert not carl.open_tickers
    assert carl.realized_pnl > 0
    assert desk.accounts["longshot_fade"].realized_pnl > 0
    assert "Risk-Free Rick" in desk.scoreboard()


async def test_desk_follows_roster_changes(desk_and_client, monkeypatch):
    desk, client = desk_and_client
    monkeypatch.setattr("desk.runner._now", lambda: NOW)
    from desk import hr

    # Suspend Bill from "the website": he stops trading but Rick keeps going
    rec = desk.roster["longshot_fade"]
    rec.status, rec.suspended_until = "suspended", (NOW + timedelta(days=3650)).isoformat()
    desk.ledger.upsert_employee(rec.to_row())
    results = await desk.tick()
    assert {r.intent.strategy for r in results if r.filled} == {"cover_arb"}


async def test_level_scales_bet_size(desk_and_client, monkeypatch):
    desk, client = desk_and_client
    monkeypatch.setattr("desk.runner._now", lambda: NOW)
    rec = desk.roster["longshot_fade"]
    rec.level = 3  # VP: 2x
    desk.ledger.upsert_employee(rec.to_row())
    results = await desk.tick()
    bill = next(r for r in results if r.intent.strategy == "longshot_fade" and r.filled)
    # A VP bets 2% of the pool (two employees x $100), at a 95c NO price
    assert bill.fills[0].count == pytest.approx(math.floor(200 * 0.02 / 0.95 * 100) / 100)


async def test_reporting_failure_does_not_stop_trading(desk_and_client, monkeypatch):
    desk, client = desk_and_client
    monkeypatch.setattr("desk.runner._now", lambda: NOW)

    def boom():
        raise RuntimeError("broken summary")

    monkeypatch.setattr(desk, "publish_accuracy", boom)
    results = await desk.tick()  # must not raise
    assert any(r.filled for r in results)
    assert any(e["kind"] == "error" for e in desk.ledger.events_since())


async def test_resting_bids_that_would_cross_the_live_book_are_not_posted(desk_and_client):
    desk, client = desk_and_client
    snap = Snapshot.build(NOW, list(client.events.values()), [], {}, {})
    strat = desk.strategies[0]
    ok = TradeIntent(strat.key, [Leg("ARB-T100", Side.YES, 0.49, 5)], "", post_only=True, ttl_seconds=60)
    crossing = TradeIntent(strat.key, [Leg("ARB-T100", Side.YES, 0.50, 5)], "", post_only=True, ttl_seconds=60)
    assert await desk.live_post(strat, ok, snap) is ok
    assert await desk.live_post(strat, crossing, snap) is None  # the ask is 0.50: Kalshi would reject it


def test_bets_are_trimmed_to_whats_left_of_the_window_cap(desk_and_client):
    desk, _ = desk_and_client
    desk.pool.update(desk.pool.total_equity(desk.accounts, {}), NOW)  # $200 pool: $6 per window
    desk.multipliers["longshot_fade"] = 2.0  # VP: $4 bets
    t = "KXBTC15M-26OCT151200-00"
    desk.accounts["cover_arb"].apply_fill(t, Side.YES, 8, 0.5, 0)  # $4 already riding on this window
    bet = desk.sized(TradeIntent("longshot_fade", [Leg(t, Side.NO, 0.5, 100)], ""))
    assert bet.legs[0].count == pytest.approx(4)  # $2 left under the cap
    other = desk.sized(TradeIntent("longshot_fade", [Leg("KXBTC15M-26OCT151215-15", Side.NO, 0.5, 100)], ""))
    assert other.legs[0].count == pytest.approx(8)  # a fresh window: the full $4
    desk.accounts["cover_arb"].apply_fill(t, Side.YES, 4, 0.5, 0)
    assert desk.sized(TradeIntent("longshot_fade", [Leg(t, Side.NO, 0.5, 100)], "")) is None


async def test_every_run_leaves_a_journal(desk_and_client, monkeypatch):
    desk, client = desk_and_client
    monkeypatch.setattr("desk.runner._now", lambda: NOW)
    await desk.tick()
    [run] = desk.ledger.recent_runs("2000-01-01")
    s = run["summary"]
    assert s["employees"]["cover_arb"]["bets"] == 1 and s["employees"]["longshot_fade"]["ideas"] == 1
    assert {"hr", "decide", "settle", "report"} <= set(s["phases"])
    assert s["pool"]["equity"] == pytest.approx(200)
    assert s["market"]["markets"] == 3


async def test_a_failed_run_is_journaled_with_its_error(desk_and_client, monkeypatch):
    desk, client = desk_and_client
    monkeypatch.setattr("desk.runner._now", lambda: NOW)

    async def down(*a, **kw):
        raise RuntimeError("kalshi is down")

    monkeypatch.setattr(desk, "build_snapshot", down)
    with pytest.raises(RuntimeError):
        await desk.tick()
    [run] = desk.ledger.recent_runs("2000-01-01")
    assert run["summary"]["failed"] == "RuntimeError: kalshi is down"


async def test_warnings_during_a_run_are_kept(desk_and_client, monkeypatch):
    import logging

    desk, client = desk_and_client
    monkeypatch.setattr("desk.runner._now", lambda: NOW)
    real = desk.refresh_crypto

    async def noisy():
        logging.getLogger("desk.feeds.crypto").warning("No BTC price from Kraken or Deribit")
        await real()

    monkeypatch.setattr(desk, "refresh_crypto", noisy)
    await desk.tick()
    [run] = desk.ledger.recent_runs("2000-01-01")
    assert run["summary"]["warnings"] == ["WARNING desk.feeds.crypto: No BTC price from Kraken or Deribit"]
    assert not logging.getLogger("desk").handlers  # the capture is removed after the run


def test_skipped_bets_say_why(desk_and_client):
    desk, _ = desk_and_client
    desk.pool.update(desk.pool.total_equity(desk.accounts, {}), NOW)  # $200 pool: $6 per window
    t = "KXBTC15M-26OCT151200-00"
    desk.accounts["cover_arb"].apply_fill(t, Side.YES, 12, 0.5, 0)  # the window is full
    bet, why = desk.size(TradeIntent("longshot_fade", [Leg(t, Side.NO, 0.5, 100)], ""))
    assert bet is None and why == "window cap full"
    desk._skip(TradeIntent("longshot_fade", [Leg(t, Side.NO, 0.5, 100)], "fade"), why)
    row = desk.ledger._rows("SELECT outcome, reason FROM decisions")[0]
    assert (row["outcome"], row["reason"]) == ("window cap full", "fade")
    assert desk.journal.employees["longshot_fade"]["skipped: window cap full"] == 1


async def test_daily_stop_pulls_waiting_bids(desk_and_client, monkeypatch):
    desk, client = desk_and_client
    monkeypatch.setattr("desk.runner._now", lambda: NOW)
    desk.pool.update(200, NOW)
    desk.broker.place(TradeIntent("longshot_fade", [Leg("LS-1", Side.NO, 0.9, 2)], "", post_only=True,
                                  ttl_seconds=600), NOW)
    desk.accounts["cover_arb"].cash -= 25  # the pool is down 12.5% today
    snap = Snapshot.build(NOW, [], [], {}, {})
    await desk.run_strategies(snap)
    assert desk.pool.stopped and desk.broker.resting == []
    assert desk.ledger._rows("SELECT outcome FROM decisions")[0]["outcome"] == "bid pulled: daily stop"


async def test_ended_bids_are_recorded(desk_and_client, monkeypatch):
    desk, client = desk_and_client
    monkeypatch.setattr("desk.runner._now", lambda: NOW + timedelta(minutes=5))

    async def get_trades(ticker, **kw):
        return [{"created_time": (NOW + timedelta(minutes=1)).isoformat(), "taker_outcome_side": "yes",
                 "no_price_dollars": "0.9000", "yes_price_dollars": "0.1000", "count_fp": "1.00"}]

    client.get_trades = get_trades
    desk.broker.place(TradeIntent("longshot_fade", [Leg("LS-1", Side.NO, 0.95, 2)], "", post_only=True,
                                  ttl_seconds=120), NOW)
    await desk.match_resting()
    row = desk.ledger._rows("SELECT outcome, filled, count FROM decisions")[0]
    assert (row["outcome"], row["filled"], row["count"]) == ("bid expired, part filled", 1, 2)
