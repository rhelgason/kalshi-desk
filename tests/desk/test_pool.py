"""The office pool: bet sizes follow the pool, and the guardrails hold."""

from datetime import datetime, timedelta, timezone

import pytest

from desk import hr
from desk.kalshi.models import Side
from desk.paper.account import PaperAccount
from desk.paper.broker import PaperBroker, RestingOrder
from desk.paper.ledger import Ledger
from desk.paper.pool import Pool, PoolAccountView, event_of
from desk.strategies.base import Leg, TradeIntent
from tests.desk.conftest import book_for, make_market

NOON = datetime(2026, 10, 15, 19, 0, tzinfo=timezone.utc)  # noon in Vancouver
SETTINGS = dict(hr.DEFAULT_POLICY["pool"])


def office(cash=(500.0, 500.0)):
    accounts = {f"e{i}": PaperAccount(f"e{i}", c) for i, c in enumerate(cash)}
    accounts["monkey"] = PaperAccount("monkey", 1000)  # control group: not in the pool
    pool = Pool(SETTINGS, [k for k in accounts if k != "monkey"])
    pool.update(pool.total_equity(accounts, {}), NOON)
    return pool, accounts


def test_bets_are_a_share_of_the_pool_scaled_by_level():
    pool, accounts = office()
    assert pool.equity == 1000  # the control group's money isn't the office's
    assert pool.bet_dollars(1.0) == pytest.approx(10)  # Associate: 1%
    assert pool.bet_dollars(0.5) == pytest.approx(5)  # Intern
    assert pool.bet_dollars(2.0) == pytest.approx(20)  # VP


def test_max_bet_stops_bets_outgrowing_the_market():
    accounts = {"e0": PaperAccount("e0", 18_000)}
    pool = Pool({**SETTINGS, "max_bet": 10}, ["e0"])
    pool.update(pool.total_equity(accounts, {}), NOON)
    assert pool.bet_dollars(1.0) == pytest.approx(10)  # 1% would be $180
    assert pool.bet_dollars(0.5) == pytest.approx(10)
    pool.settings["max_bet"] = 0  # 0 = no cap
    assert pool.bet_dollars(1.0) == pytest.approx(180)


def test_window_cap_counts_everyone_in_the_same_window():
    pool, accounts = office()
    t = "KXBTC15M-26OCT151200-00"
    accounts["e0"].apply_fill(t, Side.YES, 20, 0.5, 0)  # $10 held
    resting = [RestingOrder("o", "e1", t, "no", 0.4, 25, "", "")]  # $10 waiting
    assert event_of(t) == "close 26OCT151200"
    assert pool.window_room(event_of(t), accounts, resting) == pytest.approx(30 - 20)
    assert pool.window_room(event_of("KXBTC15M-26OCT151215-15"), accounts, resting) == pytest.approx(30)


def test_every_coin_and_hourly_ladder_closing_together_shares_one_window():
    # 11-17: XRP, ZEC and two of Hazel's hourly bets all lost at 11:00 ET, each under its own cap
    pool, accounts = office()
    accounts["e0"].apply_fill("KXXRP15M-26NOV171100-00", Side.YES, 20, 0.5, 0)        # $10
    accounts["e1"].apply_fill("KXBTCD-26NOV1711-T64099.99", Side.YES, 20, 0.5, 0)     # $10
    resting = [RestingOrder("o", "e1", "KXZEC15M-26NOV171100-00", "no", 0.5, 10, "", "")]  # $5
    window = event_of("KXETH15M-26NOV171100-00")
    assert window == event_of("KXBTCD-26NOV1711-T64299.99") == "close 26NOV171100"
    assert pool.window_room(window, accounts, resting) == pytest.approx(30 - 25)
    assert event_of("KXBTCD-26NOV1712-T64099.99") != window  # the next hour is its own
    assert event_of("KXHIGHNY-26NOV17-B54.5") == "KXHIGHNY-26NOV17"  # weather keeps its own
    assert event_of("KXBTC15M-26NOV010100EST-00") == event_of("KXBTCD-26NOV0101EST-T60000") != event_of("KXBTC15M-26NOV010100-00")


def test_daily_stop_after_losing_a_tenth_since_midnight():
    pool, accounts = office()
    pool.update(905, NOON + timedelta(hours=1))
    assert not pool.stopped
    pool.update(899, NOON + timedelta(hours=2))
    assert pool.stopped and pool.state.stopped_at
    pool.update(899, NOON + timedelta(hours=12))  # past midnight in Vancouver: a fresh day
    assert not pool.stopped and pool.state.day_open == 899


def test_slump_brake_halves_bets_until_the_pool_recovers():
    pool, _ = office()
    pool.update(1200, NOON + timedelta(days=1))
    pool.update(890, NOON + timedelta(days=5))  # 26% below the high
    assert pool.braked and pool.bet_dollars(1.0) == pytest.approx(890 * 0.01 * 0.5)
    pool.update(950, NOON + timedelta(days=6))
    assert not pool.braked


def test_members_see_and_spend_the_pools_cash():
    pool, accounts = office(cash=(30.0, 970.0))
    broker = PaperBroker(Ledger(":memory:"), accounts, liquidity_share=1.0)
    broker.pool_members = pool.members
    assert PoolAccountView(accounts["e0"], broker.free_cash("e0")).cash == 1000
    m = make_market("T", yes_bid=0.49, yes_ask=0.50)
    r = broker.execute(TradeIntent("e0", [Leg("T", Side.YES, 0.5, 80)], ""), {"T": book_for(m)}, {})
    assert r.filled and accounts["e0"].cash < 0  # one pot: e0's own share can go below zero
    assert broker.free_cash("e1") == pytest.approx(1000 - 40 - r.fills[0].fee)
    assert broker.free_cash("monkey") == 1000


def test_money_joining_or_leaving_isnt_a_gain_or_loss():
    """The 2026-10-18 false halt: two employees left the pool mid-day and it looked like a 25% loss."""
    pool, accounts = office((250.0,) * 4)
    pool.update(1000, NOON, capital=1000)
    pool.update(750, NOON + timedelta(minutes=2), capital=750)  # two of four let go, their money with them
    assert pool.today == pytest.approx(0) and not pool.stopped and not pool.braked
    pool.update(1750, NOON + timedelta(minutes=4), capital=1750)  # a $1,000 deposit
    assert pool.today == pytest.approx(0) and pool.state.peak == pytest.approx(1750)
    pool.update(1700, NOON + timedelta(minutes=6), capital=1750)  # a real loss still counts
    assert pool.today == pytest.approx(-50 / 1750)
