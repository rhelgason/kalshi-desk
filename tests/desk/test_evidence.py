"""Skill-or-luck confidence and the slippage cushion."""

import pytest

from desk.paper.accuracy import Bet
from desk.paper.evidence import MIN_BETS, evidence, evidence_from_stats


def bets(outcomes, price=0.5, fee=0.0, count=10, strategy="s"):
    return [Bet(strategy, f"T{i}", "yes", price, fee, count, None, o) for i, o in enumerate(outcomes)]


def test_few_bets_is_too_early_even_if_all_won():
    e = evidence(bets([1.0] * 10), "s")
    assert e.verdict_key == "too_early"
    assert e.bets == 10


def test_coin_flips_look_like_luck():
    e = evidence(bets([1.0, 0.0] * 50), "s")  # won exactly half at 50c: zero edge
    assert e.confidence == pytest.approx(0.5)
    assert e.verdict_key == "luck"


def test_consistent_edge_is_strong_evidence():
    # 60% win rate at 50c over 300 bets: +10c a contract
    e = evidence(bets(([1.0] * 3 + [0.0] * 2) * 60), "s")
    assert e.edge == pytest.approx(0.10)
    assert e.confidence > 0.99 and e.confidence_1c > 0.99
    assert e.verdict_key == "strong"
    assert e.pnl == pytest.approx(300 * 10 * 0.10)
    assert e.pnl_1c == pytest.approx(e.pnl - 0.01 * 3000)


def test_thin_edge_is_flagged_fragile():
    # Favorites at 95c that win 96% of the time over many bets: +1c edge, very consistent
    e = evidence(bets(([1.0] * 24 + [0.0]) * 400, price=0.95), "s")
    assert e.edge == pytest.approx(0.01)
    assert e.confidence > 0.95
    assert e.confidence_1c < 0.8
    assert e.verdict_key == "fragile"


def test_reliable_loser():
    e = evidence(bets(([1.0] * 2 + [0.0] * 3) * 60), "s")
    assert e.verdict_key == "losing"


def test_bets_needed_estimate():
    e = evidence_from_stats("s", n=MIN_BETS, mean=0.02, sd=0.4, contracts=300, pnl=6)
    assert e.bets_needed == pytest.approx((1.645 * 0.4 / 0.02) ** 2, rel=0.01)


def test_ledger_evidence_report_matches_bets():
    from desk.kalshi.models import Side
    from desk.paper.accuracy import evidence_report
    from desk.paper.ledger import Ledger

    led = Ledger(":memory:")
    for i in range(40):
        t = f"T{i}"
        led.record_fill("s", t, Side.YES, 10, 0.5, 0.0)
        led.record_settlement("s", t, 1.0 if i % 5 < 3 else 0.0, 0)
    (e,) = evidence_report(led, ["s"])
    assert e.bets == 40 and e.edge == pytest.approx(0.10)
