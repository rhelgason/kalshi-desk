from datetime import timedelta

from desk.feeds.crypto import UnderlyingQuote
from desk.kalshi.models import Side
from desk.paper.broker import RestingOrder
from desk.strategies import BreakoutBetty, BreakoutBonnie, EarlyBirdEdie, EarlyBirdEllie, NickelNora
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


LADDER = ((0.0, 0.1, 0.001), (0.1, 0.9, 0.01), (0.9, 1.0, 0.001))  # Kalshi's tapered deci-cent ladder


class TestPatientTwins:
    def test_ellie_bids_a_cent_over_the_bid_instead_of_paying_the_ask(self, account):
        m = btc15(0.77, 0.79, 12)
        m.price_ranges = LADDER
        [intent] = EarlyBirdEllie().evaluate(snap(m), account)
        leg = intent.legs[0]
        assert intent.post_only and intent.ttl_seconds > 0
        assert (leg.side, leg.limit_price) == (Side.YES, 0.78)
        assert leg.count == 12  # the same ~$9.50 Edie would spend for 12 at 79c

    def test_never_crosses_the_ask(self, account):
        m = btc15(0.78, 0.79, 12)  # 1-cent spread: improving would hit the ask, so join the bid
        m.price_ranges = LADDER
        [intent] = EarlyBirdEllie().evaluate(snap(m), account)
        assert intent.legs[0].limit_price == 0.78

    def test_nora_uses_tenth_of_a_cent_steps_above_90c(self, account):
        m = btc15(0.065, 0.08, 12)  # NO bid 0.92, NO ask 0.935
        m.price_ranges = LADDER
        [intent] = NickelNora(min_price=0.88, max_price=0.95).evaluate(snap(m), account)
        assert (intent.legs[0].side, intent.legs[0].limit_price) == (Side.NO, 0.921)

    def test_doesnt_double_up_while_a_bid_is_waiting(self, account):
        m = btc15(0.76, 0.79, 12)
        account.resting = [RestingOrder("o1", "early_maker", m.ticker, "yes", 0.77, 6, "", "")]
        assert EarlyBirdEllie().evaluate(snap(m), account) == []

    def test_bonnie_rides_bettys_waves_with_a_bid(self, account):
        m = btc15(0.53, 0.55, 13)
        m.price_ranges = LADDER
        [intent] = BreakoutBonnie().evaluate(snap(m, move=0.003), account)
        assert intent.post_only and (intent.legs[0].side, intent.legs[0].limit_price) == (Side.YES, 0.54)
