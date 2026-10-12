from datetime import timedelta

from desk.feeds.crypto import UnderlyingQuote
from desk.kalshi.models import Side
from desk.strategies import BreakoutBetty, EarlyBirdEdie
from desk.strategies.base import Snapshot
from tests.desk.conftest import NOW, make_market


def btc15(yes_bid, yes_ask, left_min):
    return make_market(f"KXBTC15M-X{left_min}", yes_bid=yes_bid, yes_ask=yes_ask, series="KXBTC15M",
                       event=f"KXBTC15M-X{left_min}", close_in=timedelta(minutes=left_min))


def snap(*markets, move=None):
    q = UnderlyingQuote("BTC", spot=100_000, momentum={15: move} if move is not None else {})
    return Snapshot.build(NOW, [], list(markets), {"BTC": q})


class TestBreakoutBetty:
    def test_rides_a_strong_move_while_the_price_lags(self, account):
        intents = BreakoutBetty().evaluate(snap(btc15(0.53, 0.55, 13), move=0.003), account)
        assert len(intents) == 1 and intents[0].legs[0].side == Side.YES

    def test_rides_down_moves_with_no(self, account):
        intents = BreakoutBetty().evaluate(snap(btc15(0.45, 0.47, 13), move=-0.003), account)
        assert intents[0].legs[0].side == Side.NO

    def test_skips_small_moves_late_windows_and_priced_in_moves(self, account):
        b = BreakoutBetty()
        assert b.evaluate(snap(btc15(0.53, 0.55, 13), move=0.001), account) == []
        assert b.evaluate(snap(btc15(0.53, 0.55, 5), move=0.003), account) == []
        assert b.evaluate(snap(btc15(0.70, 0.72, 13), move=0.003), account) == []


class TestEarlyBirdEdie:
    def test_buys_an_early_favorite(self, account):
        intents = EarlyBirdEdie().evaluate(snap(btc15(0.78, 0.80, 12)), account)
        assert len(intents) == 1 and intents[0].legs[0].side == Side.YES

    def test_buys_the_no_favorite_too(self, account):
        intents = EarlyBirdEdie().evaluate(snap(btc15(0.18, 0.20, 12)), account)
        assert intents[0].legs[0].side == Side.NO

    def test_only_early_in_the_window(self, account):
        e = EarlyBirdEdie()
        assert e.evaluate(snap(btc15(0.78, 0.80, 8)), account) == []  # too late
        assert e.evaluate(snap(btc15(0.88, 0.90, 12)), account) == []  # Nick's zone
