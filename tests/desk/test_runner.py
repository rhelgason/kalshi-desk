"""The full desk loop against a fake Kalshi client: discover, trade, settle."""

from datetime import timedelta

import pytest

from desk.config import DeskConfig
from desk.kalshi.fees import FeeSchedule
from desk.kalshi.models import Event
from desk.paper.ledger import Ledger
from desk.runner import Desk
from desk.strategies import CoverArb, LongshotFade

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
                     starting_cash=100)
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
    rec.status, rec.suspended_until = "suspended", (NOW + timedelta(days=3)).isoformat()
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
    unscaled = 5 // 0.95  # Bill's $5 stake at a 95c NO price
    assert bill.fills[0].count == pytest.approx(2 * unscaled)


async def test_reporting_failure_does_not_stop_trading(desk_and_client, monkeypatch):
    desk, client = desk_and_client
    monkeypatch.setattr("desk.runner._now", lambda: NOW)

    def boom():
        raise RuntimeError("broken summary")

    monkeypatch.setattr(desk, "publish_accuracy", boom)
    results = await desk.tick()  # must not raise
    assert any(r.filled for r in results)
    assert any(e["kind"] == "error" for e in desk.ledger.events_since())
