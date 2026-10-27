import math
from dataclasses import replace
from datetime import timedelta

from desk.feeds.crypto import UnderlyingQuote
from desk.kalshi.models import Side
from desk.paper.broker import RestingOrder
from desk.strategies import (
    BreakoutBetty, BreakoutBonnie, ClosingTimeCoco, EarlyBirdEdie, EarlyBirdEllie, NickelNora, SilverMedalSid, SteadySadie,
)
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

    def test_sticks_to_her_coins(self, account):
        eth = make_market("KXETH15M-X13", yes_bid=0.53, yes_ask=0.55, series="KXETH15M",
                          event="KXETH15M-X13", close_in=timedelta(minutes=13))
        q = {"BTC": UnderlyingQuote("BTC", spot=100_000, momentum={15: 0.004}),
             "ETH": UnderlyingQuote("ETH", spot=4_000, momentum={15: 0.004})}
        intents = BreakoutBetty(coins=["BTC"]).evaluate(Snapshot.build(NOW, [], [btc15(0.53, 0.55, 13), eth], q), account)
        assert [i.legs[0].ticker for i in intents] == ["KXBTC15M-X13"]


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
        assert leg.count == 12.15  # the same $9.48 Edie would spend for 12 at 79c, in Kalshi's 0.01 steps

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

    def test_sadie_bids_on_stellas_heavy_favorites(self, account):
        m = btc15(0.950, 0.953, 7)  # 95.3c ask, 7 minutes left: Stella's zone
        m.price_ranges = LADDER
        [intent] = SteadySadie().evaluate(snap(m), account)
        leg = intent.legs[0]
        assert intent.post_only and (leg.side, leg.limit_price) == (Side.YES, 0.951)  # a tenth of a cent over the bid
        assert SteadySadie().evaluate(snap(btc15(0.950, 0.953, 12)), account) == []  # too early for Stella

    def test_sadie_skips_a_bid_the_coins_price_says_is_too_dear(self, account):
        def look(spot, rv=0.5, yes=True):
            m = btc15(0.950, 0.953, 7) if yes else btc15(0.047, 0.050, 7)
            m.price_ranges, m.strike_type, m.floor_strike = LADDER, "greater_or_equal", 100_000
            q = UnderlyingQuote("BTC", spot=spot, realized_vol=rv)
            return SteadySadie(odds_margin=0.0).evaluate(Snapshot.build(NOW, [], [m], {"BTC": q}), account)
        # 7 minutes left at 50% a year: bitcoin 0.3% over the strike is ~96% to finish over it, above her 95.1c bid
        assert len(look(100_300)) == 1
        assert look(100_200) == []                       # 0.2% over is only ~87%: whoever sells at 95c knows that
        assert len(look(99_700, yes=False)) == 1 and look(99_800, yes=False) == []   # the same for NO
        assert len(look(100_200, rv=None)) == 1          # no vol, no opinion: she bids as before
        assert len(SteadySadie().evaluate(snap(btc15(0.950, 0.953, 7)), account)) == 1  # off unless set

    def test_coco_bids_only_in_the_last_few_minutes(self, account):
        m = btc15(0.960, 0.962, 3)
        m.price_ranges = LADDER
        [intent] = ClosingTimeCoco().evaluate(snap(m), account)
        assert intent.post_only and intent.legs[0].limit_price == 0.961
        assert ClosingTimeCoco().evaluate(snap(btc15(0.960, 0.962, 7)), account) == []  # Sadie's time
        assert ClosingTimeCoco().evaluate(snap(btc15(0.930, 0.932, 3)), account) == []  # under 94c

    def test_sid_bids_on_the_next_tier_of_favorites(self, account):
        m = btc15(0.87, 0.89, 10)
        m.price_ranges = LADDER
        [intent] = SilverMedalSid().evaluate(snap(m), account)
        assert intent.post_only and intent.legs[0].limit_price == 0.88  # a cent over the bid (1c steps under 90c)
        assert SilverMedalSid().evaluate(snap(btc15(0.950, 0.953, 10)), account) == []  # Sadie's price

    def test_a_small_pools_bet_under_one_contract_still_bids(self, account):
        m = btc15(0.950, 0.953, 7)
        m.price_ranges = LADDER
        [intent] = SteadySadie().evaluate(snap(m), account)
        small = replace(intent, legs=[replace(intent.legs[0], count=0.52)])  # a $100 pool's $0.50 bet
        leg = SteadySadie().reprice(small, m, m).legs[0]
        assert leg.count == 0.52 and leg.limit_price == 0.951

    def test_reprices_against_the_live_book_when_the_list_lags(self, account):
        seen = btc15(0.53, 0.55, 13)  # the market list says YES 53/55...
        seen.price_ranges = LADDER
        [intent] = BreakoutBonnie().evaluate(snap(seen, move=0.003), account)
        live = replace(seen, yes_bid=0.47, yes_ask=0.49)  # ...but the book has already dropped to 47/49
        leg = BreakoutBonnie().reprice(intent, seen, live).legs[0]
        assert leg.limit_price == 0.48  # not 0.54, which would sit above the real ask
        assert leg.count == math.floor(intent.legs[0].count * 0.54 / 0.48 * 100) / 100

    def test_never_bids_more_than_the_sibling_would_pay(self, account):
        seen = btc15(0.53, 0.55, 13)
        seen.price_ranges = LADDER
        [intent] = BreakoutBonnie().evaluate(snap(seen, move=0.003), account)
        live = replace(seen, yes_bid=0.58, yes_ask=0.61)  # price ran away: Betty's 55c limit wouldn't fill
        assert BreakoutBonnie().reprice(intent, seen, live).legs[0].limit_price == 0.54
        crossed = replace(seen, yes_bid=0.52, yes_ask=0.53)
        assert BreakoutBonnie().reprice(intent, seen, crossed).legs[0].limit_price == 0.52
