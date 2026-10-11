"""Fill reality check."""

import pytest

from desk.kalshi.fees import FeeSchedule
from desk.kalshi.models import Level, Orderbook, Side
from desk.paper.broker import PaperBroker
from desk.paper.ledger import Ledger
from desk.paper.realism import measured_depth, realism_from_fills, realism_report
from desk.strategies.base import Leg, TradeIntent


def test_broker_records_seen_price_and_depth():
    led = Ledger(":memory:")
    accounts = led.load_accounts(1000, ["s"])
    broker = PaperBroker(led, accounts, liquidity_share=0.5)
    # YES asks: 0.40 x 30, 0.41 x 50. The employee saw 0.41 and wants 20.
    book = Orderbook("KXBTC15M-X", yes_bids=[], no_bids=[Level(0.60, 30), Level(0.59, 50)])
    broker.execute(TradeIntent("s", [Leg("KXBTC15M-X", Side.YES, 0.41, 20)], ""), {"KXBTC15M-X": book},
                   {"KXBTC15M-X": FeeSchedule()})
    (f,) = led.fills("s")
    assert f["seen_price"] == 0.41 and f["book_depth"] == 80
    (r,) = realism_report(led, ["s"])
    assert r.slippage < 0  # filled partly at 0.40, better than the 0.41 it saw
    assert r.depth_share == pytest.approx(20 / 80)
    assert r.verdict_key == "realistic"
    assert measured_depth(led) == (80, 1)


def test_verdicts():
    big = [{"price": 0.5, "seen_price": 0.5, "count": 50, "book_depth": 60, "reason": ""}] * 5
    assert realism_from_fills("s", big).verdict_key == "too_big"
    slippy = [{"price": 0.53, "seen_price": 0.5, "count": 5, "book_depth": 100, "reason": ""}] * 5
    assert realism_from_fills("s", slippy).verdict_key == "slippy"
    maker = [{"price": 0.5, "seen_price": 0.5, "count": 5, "book_depth": 10, "reason": "maker fill: x"}] * 3
    assert realism_from_fills("s", maker).verdict_key == "maker"
    assert realism_from_fills("s", []).verdict_key == "none"
