import math
from datetime import timedelta

import pytest

from desk.feeds.crypto import UnderlyingQuote, realized_vol_from_closes
from desk.kalshi.models import Event, Side
from desk.strategies import CoverArb, CryptoFairValue, DartMonkey, LongshotFade, PartitionArb, build_strategies
from desk.strategies.base import Snapshot
from desk.strategies.pricing import effective_years, kelly_fraction, payoff_range, prob_above, prob_yes

from tests.desk.conftest import NOW, make_market


# ---------------------------------------------------------------------------
# Pricing math
# ---------------------------------------------------------------------------


class TestPricing:
    def test_at_the_money_is_about_half(self):
        p = prob_above(100, 100, 0.5, 1 / 365)
        assert 0.49 < p < 0.5  # slightly under 0.5 from the -sigma^2/2 drift term

    def test_monotonic_in_strike(self):
        probs = [prob_above(100, k, 0.4, 0.01) for k in (90, 95, 100, 105, 110)]
        assert probs == sorted(probs, reverse=True)

    def test_expired_is_certain(self):
        assert prob_above(101, 100, 0.4, 0) == 1.0
        assert prob_above(99, 100, 0.4, 0) == 0.0

    def test_range_probabilities_sum_to_one(self):
        quote_spot, vol, yrs = 100.0, 0.4, 2 / 365
        legs = [
            make_market("L", "less", cap=95),
            make_market("B1", "between", floor=95, cap=100),
            make_market("B2", "between", floor=100, cap=105),
            make_market("G", "greater", floor=105),
        ]
        total = sum(prob_yes(m, quote_spot, vol, yrs) for m in legs)
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_averaging_window_reduces_effective_time(self):
        assert effective_years(60) == pytest.approx(20 / (365 * 24 * 3600))
        assert effective_years(3600) < 3600 / (365 * 24 * 3600)

    def test_kelly(self):
        assert kelly_fraction(0.6, 0.5) == pytest.approx(0.2)
        assert kelly_fraction(0.4, 0.5) == 0

    def test_realized_vol_flat_prices_is_zero(self):
        assert realized_vol_from_closes([100.0] * 30) == 0

    def test_payoff_range_for_ladder_pair(self):
        lo = make_market("LO", "greater", floor=100)
        hi = make_market("HI", "greater", floor=110)
        assert payoff_range([(lo, Side.YES), (hi, Side.NO)]) == (1, 2)
        # The wrong way round has a hole
        assert payoff_range([(hi, Side.YES), (lo, Side.NO)]) == (0, 1)


# ---------------------------------------------------------------------------
# Arbitrage
# ---------------------------------------------------------------------------


def snap_of(*markets, events=(), underlyings=None) -> Snapshot:
    return Snapshot.build(NOW, list(events), list(markets), underlyings or {})


class TestCoverArb:
    def test_finds_inverted_ladder(self, account):
        # "Above 100" YES costs 0.50 while "above 110" NO costs 0.40: total 0.90 for a guaranteed $1
        lo = make_market("E-T100", "greater", floor=100, yes_bid=0.48, yes_ask=0.50)
        hi = make_market("E-T110", "greater", floor=110, yes_bid=0.60, yes_ask=0.62)
        intents = CoverArb().evaluate(snap_of(lo, hi), account)
        assert len(intents) == 1
        legs = {(l.ticker, l.side) for l in intents[0].legs}
        assert legs == {("E-T100", Side.YES), ("E-T110", Side.NO)}
        assert intents[0].all_or_none
        assert intents[0].guaranteed_payout == 1
        assert 0.05 < intents[0].expected_edge < 0.10

    def test_consistent_ladder_has_no_arb(self, account):
        lo = make_market("E-T100", "greater", floor=100, yes_bid=0.60, yes_ask=0.62)
        hi = make_market("E-T110", "greater", floor=110, yes_bid=0.30, yes_ask=0.32)
        assert CoverArb().evaluate(snap_of(lo, hi), account) == []

    def test_three_leg_cover_with_buckets(self, account):
        below = make_market("E-L", "less", cap=100, yes_bid=0.28, yes_ask=0.30)
        mid = make_market("E-B", "between", floor=100, cap=110, yes_bid=0.28, yes_ask=0.30)
        above = make_market("E-G", "greater", floor=110, yes_bid=0.28, yes_ask=0.30)
        intents = CoverArb().evaluate(snap_of(below, mid, above), account)
        assert len(intents) == 1 and len(intents[0].legs) == 3

    def test_fees_kill_tiny_edges(self, account):
        lo = make_market("E-T100", "greater", floor=100, yes_bid=0.48, yes_ask=0.50)
        hi = make_market("E-T110", "greater", floor=110, yes_bid=0.505, yes_ask=0.52)
        # Cost 0.50 + 0.495 = 0.995 before ~3.5c of fees
        assert CoverArb().evaluate(snap_of(lo, hi), account) == []

    def test_does_not_mix_different_players(self, account):
        a = make_market("G-PUKA-4", "greater", floor=3.5, yes_bid=0.85, yes_ask=0.90,
                        event="G", title="Puka Nacua: 4+ receptions")
        b = make_market("G-MUMP-4", "greater", floor=3.5, yes_bid=0.02, yes_ask=0.04,
                        event="G", title="Konata Mumpfield: 4+ receptions")
        assert CoverArb().evaluate(snap_of(a, b), account) == []

    def test_crypto_series_combine_across_events(self, account):
        above = make_market("KXBTCD-X-T100", "greater", floor=100, yes_bid=0.48, yes_ask=0.50,
                            series="KXBTCD", event="KXBTCD-X")
        bucket = make_market("KXBTC-X-B105", "between", floor=100.01, cap=110, yes_bid=0.0, yes_ask=0.02,
                             series="KXBTC", event="KXBTC-X")
        below = make_market("KXBTCD-X-T110", "greater", floor=110, yes_bid=0.60, yes_ask=0.62,
                            series="KXBTCD", event="KXBTCD-X")
        intents = CoverArb().evaluate(snap_of(above, bucket, below), account)
        assert intents, "should find a cover using markets from both BTC series"

    def test_suspiciously_large_edge_is_skipped(self, account):
        lo = make_market("E-T100", "greater", floor=100, yes_bid=0.08, yes_ask=0.10)
        hi = make_market("E-T110", "greater", floor=110, yes_bid=0.85, yes_ask=0.87)
        assert CoverArb().evaluate(snap_of(lo, hi), account) == []
        assert CoverArb(max_edge=1.0).evaluate(snap_of(lo, hi), account)


class TestPartitionArb:
    def _event(self, yes_bids):
        markets = [make_market(f"P-{i}", "custom", yes_bid=b, yes_ask=b + 0.02, event="P")
                   for i, b in enumerate(yes_bids)]
        return Event("P", "TEST", mutually_exclusive=True, markets=markets)

    def test_buys_all_no_when_yes_bids_sum_over_one(self, account):
        # YES bids sum to 1.20, so the NOs cost 3 - 1.20 = 1.80 and pay at least 2
        ev = self._event([0.40, 0.40, 0.40])
        intents = PartitionArb().evaluate(snap_of(events=[ev]), account)
        assert len(intents) == 1
        assert all(l.side is Side.NO for l in intents[0].legs)
        assert intents[0].guaranteed_payout == 2

    def test_fair_event_has_no_arb(self, account):
        ev = self._event([0.30, 0.30, 0.36])
        assert PartitionArb().evaluate(snap_of(events=[ev]), account) == []

    def test_wont_buy_all_yes_without_proof_of_exhaustive(self, account):
        # YES asks sum to 0.66 but nothing proves one of them must happen
        ev = self._event([0.20, 0.20, 0.20])
        assert all(i.legs[0].side is Side.NO for i in PartitionArb().evaluate(snap_of(events=[ev]), account))


# ---------------------------------------------------------------------------
# Model and behavioral strategies
# ---------------------------------------------------------------------------


class TestFairValue:
    def _btc_market(self, strike, yes_bid, yes_ask, close_in=timedelta(hours=1)):
        return make_market(f"KXBTCD-X-T{strike}", "greater", floor=strike, yes_bid=yes_bid, yes_ask=yes_ask,
                           series="KXBTCD", event="KXBTCD-X", close_in=close_in)

    def test_buys_underpriced_yes(self, account, btc_quote):
        # Spot == strike so the model says ~50%; YES offered at 0.30
        m = self._btc_market(100_000, 0.28, 0.30)
        intents = CryptoFairValue().evaluate(snap_of(m, underlyings={"BTC": btc_quote}), account)
        assert len(intents) == 1
        leg = intents[0].legs[0]
        assert leg.side is Side.YES and leg.limit_price == 0.30
        assert 0.45 < intents[0].model_prob < 0.55
        assert leg.count * leg.limit_price <= 25.0 + 1e-9  # max_bet cap

    def test_buys_no_when_yes_overpriced(self, account, btc_quote):
        m = self._btc_market(100_000, 0.70, 0.72)
        intents = CryptoFairValue().evaluate(snap_of(m, underlyings={"BTC": btc_quote}), account)
        assert intents and intents[0].legs[0].side is Side.NO

    def test_skips_fair_prices_and_missing_data(self, account, btc_quote):
        fair = self._btc_market(100_000, 0.48, 0.50)
        assert CryptoFairValue().evaluate(snap_of(fair, underlyings={"BTC": btc_quote}), account) == []
        assert CryptoFairValue().evaluate(snap_of(self._btc_market(100_000, 0.28, 0.30)), account) == []

    def test_skips_too_close_to_expiry(self, account, btc_quote):
        m = self._btc_market(100_000, 0.28, 0.30, close_in=timedelta(seconds=60))
        assert CryptoFairValue().evaluate(snap_of(m, underlyings={"BTC": btc_quote}), account) == []

    def test_one_bet_per_settlement(self, account, btc_quote):
        a = self._btc_market(100_000, 0.28, 0.30)
        b = self._btc_market(100_100, 0.20, 0.22)
        intents = CryptoFairValue().evaluate(snap_of(a, b, underlyings={"BTC": btc_quote}), account)
        assert len(intents) == 1
        assert len(CryptoFairValue(max_per_settlement=2).evaluate(
            snap_of(a, b, underlyings={"BTC": btc_quote}), account)) == 2

    def test_skips_markets_already_held(self, account, btc_quote):
        m = self._btc_market(100_000, 0.28, 0.30)
        account.apply_fill(m.ticker, Side.YES, 1, 0.3, 0.01)
        assert CryptoFairValue().evaluate(snap_of(m, underlyings={"BTC": btc_quote}), account) == []


class TestLongshotFade:
    def test_buys_no_on_cheap_yes(self, account):
        m = make_market("S-1", "custom", yes_bid=0.05, yes_ask=0.06, event="S1")
        intents = LongshotFade().evaluate(snap_of(m), account)
        assert len(intents) == 1
        leg = intents[0].legs[0]
        assert leg.side is Side.NO and leg.limit_price == pytest.approx(0.95)

    def test_filters(self, account):
        too_pricey = make_market("A-1", yes_bid=0.30, yes_ask=0.31, event="A")
        illiquid = make_market("B-1", yes_bid=0.05, yes_ask=0.06, event="B", volume_24h=10)
        wide = make_market("C-1", yes_bid=0.03, yes_ask=0.10, event="C")
        far = make_market("D-1", yes_bid=0.05, yes_ask=0.06, event="D", close_in=timedelta(days=30))
        assert LongshotFade().evaluate(snap_of(too_pricey, illiquid, wide, far), account) == []

    def test_one_bet_per_event(self, account):
        a = make_market("S-1", yes_bid=0.05, yes_ask=0.06, event="S")
        b = make_market("S-2", yes_bid=0.05, yes_ask=0.06, event="S")
        assert len(LongshotFade().evaluate(snap_of(a, b), account)) == 1


class TestDartMonkey:
    def test_seeded_and_deterministic(self, account):
        markets = [make_market(f"M-{i}", event=f"M{i}") for i in range(10)]
        a = DartMonkey(bets_per_tick=1.0, seed=7).evaluate(snap_of(*markets), account)
        b = DartMonkey(bets_per_tick=1.0, seed=7).evaluate(snap_of(*markets), account)
        assert a[0].legs[0].ticker == b[0].legs[0].ticker
        assert a[0].model_prob == a[0].legs[0].limit_price


def test_build_strategies_respects_config():
    strategies = build_strategies({"dart_monkey": {"enabled": False}, "sniper": {"min_edge": 0.02}})
    keys = [s.key for s in strategies]
    assert "dart_monkey" not in keys
    assert next(s for s in strategies if s.key == "sniper").min_edge == 0.02


def test_market_weight_blends_toward_price(account, btc_quote):
    m = make_market("KXBTCD-X-T100000", "greater", floor=100_000, yes_bid=0.29, yes_ask=0.31,
                    series="KXBTCD", event="KXBTCD-X")
    snap = snap_of(m, underlyings={"BTC": btc_quote})
    raw = CryptoFairValue().model_prob(m, snap)
    blended = CryptoFairValue(market_weight=0.8).model_prob(m, snap)
    assert blended == pytest.approx(0.8 * 0.30 + 0.2 * raw)
    # The raw model sees a ~20c edge; blended toward the market it's ~4c, under the 4c bar after fees
    assert CryptoFairValue().evaluate(snap, account)
    assert not CryptoFairValue(market_weight=0.8).evaluate(snap, account)
