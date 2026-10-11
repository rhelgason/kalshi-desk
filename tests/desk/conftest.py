import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from desk.feeds.crypto import UnderlyingQuote
from desk.kalshi.models import Level, Market, Orderbook
from desk.paper.account import PaperAccount

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 11, 1, 0, tzinfo=timezone.utc)


@pytest.fixture
def fixture_json():
    def load(name: str) -> dict:
        return json.loads((FIXTURES / name).read_text())
    return load


def make_market(
    ticker: str,
    strike_type: str = "greater",
    floor: float | None = None,
    cap: float | None = None,
    yes_bid: float = 0.40,
    yes_ask: float = 0.42,
    size: float = 100.0,
    event: str = "EVT-1",
    series: str = "TEST",
    close_in: timedelta = timedelta(hours=1),
    title: str = "Test market",
    status: str = "active",
    volume_24h: float = 1000.0,
) -> Market:
    return Market(
        ticker=ticker,
        event_ticker=event,
        title=title,
        status=status,
        strike_type=strike_type,
        floor_strike=floor,
        cap_strike=cap,
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        no_bid=round(1 - yes_ask, 4),
        no_ask=round(1 - yes_bid, 4),
        yes_bid_size=size,
        yes_ask_size=size,
        volume_24h=volume_24h,
        close_time=NOW + close_in,
        series_ticker=series,
    )


def book_for(market: Market, size: float | None = None) -> Orderbook:
    """Orderbook consistent with a market's top-of-book quote."""
    s = size if size is not None else market.yes_ask_size
    yes_bids = [Level(market.yes_bid, s)] if market.yes_bid > 0 else []
    no_bids = [Level(round(1 - market.yes_ask, 4), s)] if 0 < market.yes_ask < 1 else []
    return Orderbook(market.ticker, yes_bids, no_bids)


@pytest.fixture
def account():
    return PaperAccount("test", 1000.0)


@pytest.fixture
def btc_quote():
    return UnderlyingQuote("BTC", spot=100_000.0, implied_vol=0.40, realized_vol=0.40)
