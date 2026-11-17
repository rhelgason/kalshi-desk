"""The prediction model (desk/forecast.py): the replay library's curves, the taper, blending, and determinism."""
import math

import pytest

from desk.forecast import (Book, Forecaster, Library, Staff, build_staff, synthetic_fill, _q)

POOL = {"bet_pct": 0.04, "window_cap": 0.16, "daily_stop": 0.15, "brake_drawdown": 0.25, "brake_factor": 0.5, "max_bet": 0}


@pytest.fixture(scope="module")
def fc():
    return Forecaster.load()


def tiny_library():
    caps = [5, 10, 20, 40]
    # one coin, two days, one window a day: fills flatten past $20 and the last dollars lose
    curve = [[5, 0.1], [10, 0.2], [18, 0.3], [20, 0.1]]
    return Library({"caps": caps, "coins": {"SOL": [[86400 + 900, 1, curve], [2 * 86400 + 900, 1, curve], [2 * 86400, 0]]}})


def test_curve_is_straight_between_sizes_and_flat_past_the_last():
    lib = tiny_library()
    assert lib.at(lib_curve := [[5, 0.1], [10, 0.2], [18, 0.3], [20, 0.1]], 2.5) == pytest.approx((2.5, 0.05))
    assert lib.at(lib_curve, 15) == pytest.approx((14, 0.25))
    assert lib.at(lib_curve, 1000) == (20, 0.1)
    assert lib.tape_edge["SOL"] == pytest.approx(0.02)  # the $10 column: 0.2 on 10


def test_blending_leans_on_real_bets_as_they_pile_up():
    lib = tiny_library()
    few = build_staff(lib, ["maker_sol"], {"maker_sol": 3}, {"maker_sol": {"bets": 30, "spent": 300, "pnl": -30}})[0]
    many = build_staff(lib, ["maker_sol"], {"maker_sol": 3}, {"maker_sol": {"bets": 3000, "spent": 30000, "pnl": -3000}})[0]
    assert few.edge > 0.005 and many.edge < -0.05  # 30 real bets barely move the tape's +2c; 3,000 at -10c win
    assert few.edge_sd > many.edge_sd > 0
    assert build_staff(lib, ["nobody"], {}, {}) == []


def test_synthetic_bets_fill_less_and_earn_less_as_they_grow():
    small, big = synthetic_fill("hourly_btc", 10), synthetic_fill("hourly_btc", 5000)
    assert small[0] / 10 > big[0] / 5000 and small[1] > big[1]


def real_like_book(equity=750.0, others=0.0):
    lib = Forecaster.load().lib
    staff = [Staff(key=k, level=3, edge=lib.tape_edge[c], edge_sd=0.005, tape_edge=lib.tape_edge[c])
             for k, c in [("maker_sol", "SOL"), ("maker_xrp", "XRP"), ("maker_doge", "DOGE"), ("maker_eth", "ETH")]]
    return Book(name="t", equity=equity, settings=dict(POOL), staff=staff, others=others)


def test_growth_tapers_as_the_pool_grows(fc):
    eng = fc.engine(real_like_book(), [300, 3000, 30000, 300000], samples=1)
    pct = [r["pct_day"] for r in eng]
    assert pct[0] > pct[1] > pct[2] > pct[3]
    assert eng[0]["pct_day"] > 0.01  # a small pool earns a few % a day on the tape
    # friends' money in the same markets: the same pool earns less a day
    shared = fc.engine(real_like_book(others=30000), [3000], samples=1)[0]
    assert shared["profit_day"] < eng[1]["profit_day"]


def test_futures_are_repeatable_and_ordered(fc):
    b = real_like_book()
    a1, a2 = fc.paths(b, n=6, days=10, seed=5), fc.paths(b, n=6, days=10, seed=5)
    assert a1["lines"] == a2["lines"]
    out = fc.run(b, n=12, deposits=(0, 500))
    last = out["fan"][-1]
    assert last["p10"] <= last["p50"] <= last["p90"]
    assert out["what_if"][1]["deposit"] == 500
    assert out["check"] is None  # no season history in a test book
    assert out["tested_pool"] == pytest.approx(60 / (0.04 * 2), rel=0.01)


def test_quantile():
    assert _q([1, 2, 3, 4, 5], 0.5) == 3 and _q([], 0.5) == 0 and math.isclose(_q([0, 10], 0.25), 2.5)
