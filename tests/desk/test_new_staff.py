"""Vega Vinny, The Sniper, Momentum Mo, Rubber Band Randy, Lenny, Nick, Walt."""

import math
from datetime import timedelta

import pytest

from desk.feeds.crypto import CryptoFeed, UnderlyingQuote
from desk.kalshi.models import Side
from desk.strategies import (
    LongshotFade, LongshotLenny, MomentumMo, NickelNick, RubberBandRandy, Sniper, VegaVinny,
    WhaleWatcherWalt, build_strategies, EVERYONE, REGISTRY,
)
from desk.strategies.base import Snapshot
from desk.strategies.fair_value import implied_vol
from desk.strategies.pricing import effective_years, prob_yes

from tests.desk.conftest import NOW, make_market


def snap_of(*markets, underlyings=None, trades=None) -> Snapshot:
    snap = Snapshot.build(NOW, [], list(markets), underlyings or {})
    snap.trades = trades or {}
    return snap


def btc(strike, yes_bid, yes_ask, close_in=timedelta(hours=1)):
    return make_market(f"KXBTCD-X-T{strike}", "greater", floor=strike, yes_bid=yes_bid, yes_ask=yes_ask,
                       series="KXBTCD", event="KXBTCD-X", close_in=close_in)


def fair_ladder(spot, vol, strikes, close_in=timedelta(hours=1), half_spread=0.01):
    """Strikes priced exactly by the model at `vol`, with a 2c spread."""
    years = effective_years(close_in.total_seconds())
    out = []
    for k in strikes:
        p = prob_yes(btc(k, 0, 0), spot, vol, years)
        out.append(btc(k, round(p - half_spread, 4), round(p + half_spread, 4), close_in))
    return out


def test_all_employees_registered_with_unique_names():
    staff = build_strategies({})
    assert len(staff) == len(REGISTRY) == 21
    everyone = build_strategies({}, EVERYONE)
    assert len({s.persona.name for s in everyone}) == len(EVERYONE) == 38


class TestVegaVinny:
    def test_implied_vol_roundtrip(self):
        m = btc(101_000, 0, 0)
        years = effective_years(3600)
        p = prob_yes(m, 100_000, 0.35, years)
        assert implied_vol(m, 100_000, p, years) == pytest.approx(0.35, rel=1e-4)

    def test_flags_the_strike_out_of_line_with_neighbors(self, account):
        spot, vol = 100_000.0, 0.30
        ladder = fair_ladder(spot, vol, [99_600, 99_800, 100_200, 100_400])
        # Same settle time, but this strike's YES is 10c too cheap relative to the curve
        fair = prob_yes(btc(100_100, 0, 0), spot, vol, effective_years(3600))
        odd = btc(100_100, round(fair - 0.12, 2), round(fair - 0.10, 2))
        # The feed's own vol estimate is wildly wrong; Vinny shouldn't care
        quote = UnderlyingQuote("BTC", spot, implied_vol=2.0, realized_vol=2.0)
        intents = VegaVinny().evaluate(snap_of(*ladder, odd, underlyings={"BTC": quote}), account)
        assert [i.legs[0].ticker for i in intents] == [odd.ticker]
        assert intents[0].legs[0].side is Side.YES

    def test_needs_enough_strikes(self, account):
        ladder = fair_ladder(100_000.0, 0.3, [99_800])
        quote = UnderlyingQuote("BTC", 100_000.0, realized_vol=0.3)
        vinny = VegaVinny()
        vinny.prepare(snap_of(*ladder, underlyings={"BTC": quote}))
        assert vinny.market_vols == {}  # one strike isn't enough to read the market's vol


class TestSniper:
    quote = UnderlyingQuote("BTC", 100_000.0, implied_vol=0.30, realized_vol=0.30)

    def test_shoots_near_certain_contract_in_final_minutes(self, account):
        # 3 minutes left, BTC 1% above the strike: YES is all but certain, yet offered at 0.90
        m = btc(99_000, 0.88, 0.90, close_in=timedelta(minutes=3))
        intents = Sniper().evaluate(snap_of(m, underlyings={"BTC": self.quote}), account)
        assert len(intents) == 1 and intents[0].legs[0].side is Side.YES
        assert intents[0].model_prob > 0.95

    def test_holds_fire_early_or_when_uncertain(self, account):
        early = btc(99_000, 0.88, 0.90, close_in=timedelta(minutes=30))
        coin_flip = btc(100_000, 0.30, 0.32, close_in=timedelta(minutes=3))
        assert Sniper().evaluate(snap_of(early, coin_flip, underlyings={"BTC": self.quote}), account) == []


class TestMomentum:
    def _quote(self, move):
        return UnderlyingQuote("BTC", 100_000.0, realized_vol=0.30, momentum={5: move, 15: move})

    def test_mo_and_randy_disagree_on_a_rally(self, account):
        m = btc(100_000, 0.49, 0.51)
        rally = self._quote(0.004)  # up 0.4% in the window
        mo = MomentumMo().model_prob(m, snap_of(m, underlyings={"BTC": rally}))
        randy = RubberBandRandy().model_prob(m, snap_of(m, underlyings={"BTC": rally}))
        assert mo > 0.55 and randy < 0.45

    def test_no_momentum_data_means_plain_model(self, account):
        m = btc(100_000, 0.49, 0.51)
        flat = UnderlyingQuote("BTC", 100_000.0, realized_vol=0.30)
        assert MomentumMo().model_prob(m, snap_of(m, underlyings={"BTC": flat})) == pytest.approx(0.5, abs=0.01)

    def test_feed_momentum_from_history(self):
        feed = CryptoFeed(("BTC",))
        feed._merge_history("BTC", [(NOW - timedelta(minutes=15), 100.0), (NOW - timedelta(minutes=5), 101.0)])
        mom = feed.momentum("BTC", NOW, 102.0)
        assert mom[15] == pytest.approx(math.log(1.02))
        assert mom[5] == pytest.approx(math.log(102 / 101))
        assert 60 not in mom  # no data that far back


class TestBandBettors:
    def test_lenny_is_bills_mirror(self, account):
        m = make_market("S-1", "custom", yes_bid=0.05, yes_ask=0.06, event="S1")
        bill = LongshotFade().evaluate(snap_of(m), account)[0].legs[0]
        lenny = LongshotLenny().evaluate(snap_of(m), account)[0].legs[0]
        assert (bill.side, lenny.side) == (Side.NO, Side.YES)
        assert lenny.limit_price == pytest.approx(0.06)

    def test_nick_buys_near_sure_things_closing_soon(self, account):
        soon = make_market("A-1", yes_bid=0.94, yes_ask=0.95, event="A", close_in=timedelta(hours=3))
        later = make_market("B-1", yes_bid=0.94, yes_ask=0.95, event="B", close_in=timedelta(days=3))
        no_side = make_market("C-1", yes_bid=0.05, yes_ask=0.06, event="C", close_in=timedelta(hours=3))
        intents = NickelNick().evaluate(snap_of(soon, later, no_side), account)
        got = {(i.legs[0].ticker, i.legs[0].side) for i in intents}
        assert got == {("A-1", Side.YES), ("C-1", Side.NO)}


class TestWhaleWalt:
    def _trade(self, tid, side, price, count, seconds_ago=30):
        return {
            "trade_id": tid, "taker_outcome_side": side, "count_fp": f"{count:.2f}",
            "yes_price_dollars": f"{price if side == 'yes' else 1 - price:.4f}",
            "no_price_dollars": f"{price if side == 'no' else 1 - price:.4f}",
            "created_time": (NOW - timedelta(seconds=seconds_ago)).isoformat(),
        }

    def test_follows_a_big_fresh_trade_once(self, account):
        m = make_market("W-1", yes_bid=0.40, yes_ask=0.42, event="W")
        walt = WhaleWatcherWalt()
        trades = {"W-1": [self._trade("t1", "yes", 0.41, 1000)]}
        intents = walt.evaluate(snap_of(m, trades=trades), account)
        assert len(intents) == 1 and intents[0].legs[0].side is Side.YES
        assert walt.evaluate(snap_of(m, trades=trades), account) == []  # already followed

    def test_ignores_small_stale_or_chased(self, account):
        m = make_market("W-1", yes_bid=0.50, yes_ask=0.52, event="W")
        trades = {"W-1": [
            self._trade("small", "yes", 0.51, 10),
            self._trade("stale", "yes", 0.51, 1000, seconds_ago=3600),
            self._trade("chased", "yes", 0.45, 1000),  # price has run from 0.45 to 0.52
        ]}
        assert WhaleWatcherWalt().evaluate(snap_of(m, trades=trades), account) == []


class TestFran:
    def test_backs_sports_favorites_only(self, account):
        from desk.strategies import FrontRunnerFran
        game = make_market("KXNFLGAME-26OCT12BUFLAR-BUF", yes_bid=0.80, yes_ask=0.81, event="KXNFLGAME-26OCT12BUFLAR",
                           series="KXNFLGAME", close_in=timedelta(hours=10))
        prop = make_market("KXNFLREC-26OCT12BUFLAR-X-4", yes_bid=0.80, yes_ask=0.81, event="KXNFLREC-26OCT12",
                           series="KXNFLREC", close_in=timedelta(hours=10))
        soon = make_market("KXMLBGAME-26OCT12-NYY", yes_bid=0.80, yes_ask=0.81, event="KXMLBGAME-26OCT12",
                           series="KXMLBGAME", close_in=timedelta(minutes=30))
        intents = FrontRunnerFran().evaluate(snap_of(game, prop, soon), account)
        assert [i.legs[0].ticker for i in intents] == [game.ticker]


class TestSam:
    def test_quotes_inside_wide_spreads_both_sides(self, account):
        from desk.strategies import SpreadSam
        wide = make_market("W-1", yes_bid=0.40, yes_ask=0.45, event="W", volume_24h=50_000)
        tight = make_market("T-1", yes_bid=0.40, yes_ask=0.41, event="T", volume_24h=50_000)
        intents = SpreadSam().evaluate(snap_of(wide, tight), account)
        assert len(intents) == 1 and intents[0].post_only
        legs = {(l.side, l.limit_price) for l in intents[0].legs}
        assert legs == {(Side.YES, 0.41), (Side.NO, 0.56)}  # 0.41 + 0.56 = 0.97: 3c if both fill

    def test_stops_adding_to_a_lopsided_position(self, account):
        from desk.strategies import SpreadSam
        m = make_market("W-1", yes_bid=0.40, yes_ask=0.45, event="W", volume_24h=50_000)
        account.apply_fill("W-1", Side.YES, 30, 0.41, 0)
        intents = SpreadSam().evaluate(snap_of(m), account)
        assert [l.side for l in intents[0].legs] == [Side.NO]
