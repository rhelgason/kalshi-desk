"""Backtest engine on synthetic history (no network)."""

from datetime import datetime, timedelta, timezone

import pytest

from desk.backtest import Backtest, BacktestConfig, BacktestData, HistoricalMarket, SpotSeries
from desk.kalshi.models import Market
from desk.strategies import NickelNick, Sniper

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
ts0 = int(T0.timestamp())


def window(i: int, result: str, strike: float, yes_path: list[tuple[float, float]]) -> HistoricalMarket:
    """A 15-minute BTC up/down market with one candle per minute."""
    open_t = T0 + timedelta(minutes=15 * i)
    m = Market(ticker=f"KXBTC15M-W{i}", event_ticker=f"KXBTC15M-W{i}", strike_type="greater_or_equal",
               floor_strike=strike, open_time=open_t, close_time=open_t + timedelta(minutes=15),
               result=result, series_ticker="KXBTC15M")
    start = int(open_t.timestamp())
    candles = {start + 60 * (k + 1): (bid, ask, 100.0) for k, (bid, ask) in enumerate(yes_path)}
    return HistoricalMarket(m, candles)


def flat_spot(price: float, minutes: int = 600) -> SpotSeries:
    # Tiny wiggle so realized vol isn't zero
    return SpotSeries({ts0 - 300 * 60 + 60 * k: price * (1 + 0.0002 * ((-1) ** k)) for k in range(minutes)})


def test_spot_series_lookups():
    s = SpotSeries({ts0 + 60: 100.0, ts0 + 120: 101.0, ts0 + 240: 102.0})
    assert s.price(ts0 + 120) == 101.0
    assert s.price(ts0 + 180) == 101.0  # forward-filled gap
    assert s.momentum(ts0 + 240, (2,))[2] == pytest.approx(0.00995, abs=1e-4)
    assert s.price(ts0) is None


def test_nick_buys_favorite_and_gets_paid():
    # YES drifts up to 0.94-0.95 late in the window and resolves YES
    path = [(0.50, 0.52)] * 10 + [(0.94, 0.95)] * 5
    data = BacktestData(markets=[window(0, "yes", 100_000, path)], spot={"BTC": flat_spot(100_100)},
                        dvol={}, start=ts0, end=ts0 + 20 * 60)
    bt = Backtest(data, [NickelNick(max_hours=1, min_seconds=60, max_spread=0.02)], BacktestConfig())
    bt.run()
    nick = bt.accounts["nickel_picker"]
    assert nick.trades == 1 and nick.settled_wins == 1
    assert nick.realized_pnl > 0
    assert not nick.open_tickers


def test_fill_delay_misses_moving_price():
    # Price jumps right after the signal minute, so a delayed fill at the old limit fails
    path = [(0.50, 0.52)] * 10 + [(0.94, 0.95), (0.97, 0.98), (0.97, 0.98), (0.97, 0.98), (0.97, 0.98)]
    data = BacktestData(markets=[window(0, "yes", 100_000, path)], spot={"BTC": flat_spot(100_100)},
                        dvol={}, start=ts0, end=ts0 + 20 * 60)
    strat = NickelNick(max_hours=1, min_seconds=60, max_spread=0.02, max_price=0.95)
    instant = Backtest(data, [strat], BacktestConfig(fill_delay=0))
    instant.run()
    delayed = Backtest(data, [NickelNick(max_hours=1, min_seconds=60, max_spread=0.02, max_price=0.95)],
                       BacktestConfig(fill_delay=1))
    delayed.run()
    assert instant.accounts["nickel_picker"].trades == 1
    assert delayed.accounts["nickel_picker"].trades == 0


def test_sniper_uses_spot_vs_strike():
    # BTC sits 1% above the strike; YES offered at 0.90 with 4 minutes left
    path = [(0.70, 0.72)] * 11 + [(0.88, 0.90)] * 4
    data = BacktestData(markets=[window(0, "yes", 99_000, path)], spot={"BTC": flat_spot(100_000)},
                        dvol={}, start=ts0, end=ts0 + 20 * 60)
    bt = Backtest(data, [Sniper()], BacktestConfig())
    bt.run()
    assert bt.accounts["sniper"].settled_wins == 1


def test_candle_parsing_handles_live_and_archived_formats():
    from desk.backtest.data import _candle_tuple
    live = {"yes_bid": {"close_dollars": "0.45"}, "yes_ask": {"close_dollars": "0.47"}, "volume_fp": "10.00"}
    archived = {"yes_bid": {"close": "0.50"}, "yes_ask": {"close": "0.51"}, "volume": "90924.95"}
    assert _candle_tuple(live) == (0.45, 0.47, 10.0)
    assert _candle_tuple(archived) == (0.50, 0.51, 90924.95)
    assert _candle_tuple({"yes_bid": {}, "yes_ask": {}}) is None
