"""Parsing real Kalshi API responses (saved in fixtures/) and orderbook math."""

import pytest

from desk.kalshi.models import Event, Level, Market, Orderbook, Side


def test_parses_real_event_with_dollar_strings(fixture_json):
    event = Event.from_api(fixture_json("kxbtcd_event.json")["events"][0])
    assert event.series_ticker == "KXBTCD"
    assert event.mutually_exclusive is False
    assert len(event.markets) == 12
    m = event.markets[0]
    assert m.series_ticker == "KXBTCD"
    assert m.strike_type == "greater"
    assert m.floor_strike is not None
    assert 0 <= m.yes_bid <= 1 and 0 <= m.yes_ask <= 1
    assert m.close_time is not None and m.close_time.tzinfo is not None
    assert m.tick_size == pytest.approx(0.01)


def test_parses_range_event(fixture_json):
    event = Event.from_api(fixture_json("kxbtc_event.json")["events"][0])
    assert event.mutually_exclusive is True
    assert event.markets[0].strike_type in ("less", "between", "greater")


def test_parses_real_orderbook_best_first(fixture_json):
    ob = Orderbook.from_api("X", fixture_json("orderbook.json"))
    assert ob.yes_bids and ob.no_bids
    assert ob.yes_bids[0].price == max(lv.price for lv in ob.yes_bids)
    # YES ask comes from the best NO bid
    assert ob.best_ask(Side.YES) == pytest.approx(1 - ob.no_bids[0].price)
    # A single book can never offer YES + NO for less than $1
    assert ob.best_ask(Side.YES) + ob.best_ask(Side.NO) >= 1


def test_series_derived_from_event_ticker():
    m = Market.from_api({"ticker": "KXHIGHNY-26OCT10-T66", "event_ticker": "KXHIGHNY-26OCT10"})
    assert m.series_ticker == "KXHIGHNY"


def test_missing_quotes_are_zero_and_ask_ignores_bad_prices():
    m = Market.from_api({"ticker": "T", "yes_ask_dollars": "1.0000", "yes_bid_dollars": ""})
    assert m.yes_bid == 0
    assert m.ask(Side.YES) == 0  # $1.00 ask is not a real offer
    assert m.mid is None


@pytest.mark.parametrize(
    "strike_type, floor, cap, value, expected",
    [
        ("greater", 100, None, 100.01, True),
        ("greater", 100, None, 100, False),
        ("greater_or_equal", 100, None, 100, True),
        ("less", None, 100, 99.99, True),
        ("less", None, 100, 100, False),
        ("less_or_equal", None, 100, 100, True),
        ("between", 100, 110, 100, True),
        ("between", 100, 110, 110, True),
        ("between", 100, 110, 110.01, False),
        ("custom", None, None, 5, None),
    ],
)
def test_yes_pays_at(strike_type, floor, cap, value, expected):
    m = Market("T", "E", strike_type=strike_type, floor_strike=floor, cap_strike=cap)
    assert m.yes_pays_at(value) is expected


def test_walk_book_respects_limit_and_depth():
    ob = Orderbook("T", yes_bids=[], no_bids=[Level(0.60, 10), Level(0.58, 20)])
    # YES asks: 0.40 x10, 0.42 x20
    fill = ob.walk(Side.YES, 25, limit_price=0.42)
    assert fill.count == 25
    assert fill.cost == pytest.approx(10 * 0.40 + 15 * 0.42)
    partial = ob.walk(Side.YES, 25, limit_price=0.41)
    assert partial.count == 10
    assert ob.depth_at_or_better(Side.YES, 0.42) == 30
