"""Steady Stella and seeding a season from a replay (no network)."""

from datetime import timedelta

from desk.backtest import BacktestData
from desk.backtest.seed import REPLAY_TAG, SeasonReplay, write_season
from desk.paper.ledger import Ledger
from desk.strategies import SteadyStella
from tests.desk.conftest import NOW, make_market
from tests.desk.test_backtest import flat_spot, ts0, window

POOL = {"bet_pct": 0.01, "window_cap": 0.05, "daily_stop": 0.10, "brake_drawdown": 0.25, "brake_factor": 0.5,
        "timezone": "UTC"}


def test_stella_only_bets_mid_window(account):
    stella = SteadyStella()
    early = make_market("A", yes_bid=0.94, yes_ask=0.95, close_in=timedelta(minutes=12), event="E1")
    mid = make_market("B", yes_bid=0.94, yes_ask=0.95, close_in=timedelta(minutes=7), event="E2")
    late = make_market("C", yes_bid=0.94, yes_ask=0.95, close_in=timedelta(minutes=3), event="E3")
    cheap = make_market("D", yes_bid=0.88, yes_ask=0.89, close_in=timedelta(minutes=7), event="E4")
    from desk.strategies.base import Snapshot

    snap = Snapshot.build(NOW, [], [early, mid, late, cheap], {}, {})
    picks = {i.legs[0].ticker for i in stella.evaluate(snap, account)}
    assert picks == {"B"}


def _replay(path, result="yes", slippage=None):
    data = BacktestData(markets=[window(0, result, 100_000, path)], spot={"BTC": flat_spot(100_100)},
                        dvol={}, start=ts0, end=ts0 + 20 * 60)
    replay = SeasonReplay(data, [SteadyStella()], {"heavy_favorite"}, {"heavy_favorite": 1.0}, POOL,
                          pool_cash=1000, control_cash=1000, fees={}, slippage=slippage)
    replay.run()
    return replay


def test_replay_sizes_from_the_pool_and_tags_fills():
    # YES sits at 0.94-0.95 from 8 minutes left and resolves YES
    replay = _replay([(0.50, 0.52)] * 7 + [(0.94, 0.95)] * 8)
    acct = replay.accounts["heavy_favorite"]
    assert acct.trades == 1 and acct.settled_wins == 1
    fill = replay.ledger.fills()[0]
    assert fill["reason"].startswith(REPLAY_TAG)
    assert 9.0 <= fill["count"] * fill["price"] <= 10.0  # 1% of the $1,000 pool


def test_replay_slippage_costs_more():
    path = [(0.50, 0.52)] * 7 + [(0.94, 0.95)] * 8
    plain = _replay(path).ledger.fills()[0]["price"]
    slipped = _replay(path, slippage={"KXBTC15M": 0.01}).ledger.fills()[0]["price"]
    assert slipped == round(plain + 0.01, 4)


def test_write_season_copies_records_under_the_new_season():
    replay = _replay([(0.50, 0.52)] * 7 + [(0.94, 0.95)] * 8)
    dest = Ledger(":memory:")
    counts = write_season(replay, dest, season=5)
    assert counts["fills"] == 1 and counts["settlements"] == 1 and counts["equity"] >= 1
    assert dest._rows("SELECT DISTINCT season FROM fills")[0]["season"] == 5
    assert dest._rows("SELECT ts FROM fills")[0]["ts"] == replay.ledger.fills()[0]["ts"]  # original time kept


def _twin_replay(dip):
    from desk.strategies import SteadySadie

    hm = window(0, "yes", 100_000, [(0.50, 0.52)] * 7 + [(0.94, 0.95)] * 8)
    if dip:  # the bid dips under the twin's price for a moment, every minute from 8 minutes left
        hm.extremes = {t: (0.935, 0.95) for t, (bid, ask, _) in hm.candles.items() if bid == 0.94}
    data = BacktestData(markets=[hm], spot={"BTC": flat_spot(100_100)}, dvol={}, start=ts0, end=ts0 + 20 * 60)
    replay = SeasonReplay(data, [SteadySadie()], {"heavy_maker"}, {"heavy_maker": 1.0}, POOL,
                          pool_cash=1000, control_cash=1000, fees={})
    replay.run()
    return replay


def test_replay_fills_a_patient_twins_bid_when_the_bid_dips_through_it():
    replay = _twin_replay(dip=True)
    [fill] = replay.ledger.fills()
    assert fill["reason"].startswith("maker fill: " + REPLAY_TAG) and fill["fee"] == 0
    assert fill["price"] <= 0.94 and 9.0 <= fill["count"] * fill["price"] <= 10.0
    assert replay.accounts["heavy_maker"].settled_wins == 1 and not replay.broker.resting


def test_replay_never_fills_a_bid_without_stored_dips():
    replay = _twin_replay(dip=False)  # history stored before bid lows were kept
    assert replay.ledger.fills() == [] and replay.stats["bids"] >= 1
