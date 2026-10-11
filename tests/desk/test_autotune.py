"""History store round trip and autotune decisions (synthetic data, no network)."""

import json
from datetime import datetime, timedelta, timezone

from desk import hr
from desk.autotune import SEARCH_SPACES, autotune_due, decide, run_autotune
from desk.backtest import BacktestConfig, BacktestData
from desk.backtest.store import coverage, load_from_store, save_markets
from desk.config import DeskConfig
from desk.paper.ledger import Ledger

from tests.desk.test_backtest import T0, flat_spot, window, ts0


def favorite_history(n=40):
    """n 15-minute windows where YES is offered at 0.87 and wins 95% of the time: a real edge."""
    out = []
    for i in range(n):
        result = "no" if i % 20 == 0 else "yes"
        out.append(window(i, result, 100_000, [(0.86, 0.87)] * 15))
    return out


def test_store_round_trip():
    led = Ledger(":memory:")
    hm = window(0, "yes", 100_000, [(0.5, 0.52)] * 15)
    m = hm.market
    raw = {"ticker": m.ticker, "event_ticker": m.event_ticker, "strike_type": m.strike_type,
           "floor_strike": m.floor_strike, "open_time": m.open_time.isoformat(),
           "close_time": m.close_time.isoformat(), "result": "yes"}
    save_markets(led, "KXBTC15M", [raw], {m.ticker: {t: list(v) for t, v in hm.candles.items()}})
    save_markets(led, "KXBTC15M", [raw], {m.ticker: {t: list(v) for t, v in hm.candles.items()}})  # idempotent
    led._write("INSERT INTO price_history(symbol, day, data) VALUES (?, ?, ?)",
               ("BTC", T0.strftime("%Y-%m-%d"), json.dumps({str(ts0 + 60 * k): 100_000.0 for k in range(1, 60)})))
    data = load_from_store(led, ["KXBTC15M"], T0 - timedelta(hours=1), T0 + timedelta(hours=2))
    assert len(data.markets) == 1 and data.markets[0].yes_value == 1.0
    assert data.markets[0].candles == hm.candles
    assert data.spot["BTC"].price(ts0 + 600) == 100_000.0
    assert coverage(led)[0]["markets"] == 1


def test_autotune_applies_only_validated_improvements():
    led = Ledger(":memory:")
    data = BacktestData(markets=favorite_history(), spot={"BTC": flat_spot(100_100, minutes=1200)}, dvol={},
                        start=ts0, end=ts0 + 40 * 15 * 60 + 600)
    policy = hr.load_policy(led)
    policy["autotune"]["min_test_bets"] = 3
    policy["autotune"]["min_improvement"] = 1.0
    # Current settings can't buy at 0.87 (band tops out at 0.85); the search can find one that does
    current = {"min_price": 0.80, "max_price": 0.85, "min_seconds": 600, "max_hours": 1, "max_spread": 0.02}
    d = decide("nickel_picker", current, data, BacktestConfig(), policy)
    assert d["tried"] == 27
    assert d["current"]["test"]["bets"] == 0
    assert d["applied"] and d["changes"]["min_price"] == 0.85 and d["changes"]["max_price"] >= 0.93


def test_run_autotune_respects_autotune_flag_and_logs(monkeypatch):
    led = Ledger(":memory:")
    data = BacktestData(markets=favorite_history(), spot={"BTC": flat_spot(100_100, minutes=1200)}, dvol={},
                        start=ts0, end=ts0 + 40 * 15 * 60 + 600)
    roster = hr.load_roster(led, list(SEARCH_SPACES))
    for k, rec in roster.items():
        rec.autotune = k == "nickel_picker"
        led.upsert_employee(rec.to_row())
    policy = hr.load_policy(led)
    policy["autotune"].update(min_test_bets=3, min_improvement=1.0, requested_at="2026-10-01T00:00:00+00:00")
    hr.save_policy(led, policy)
    cfg = DeskConfig(strategies={"nickel_picker": {"min_price": 0.80, "max_price": 0.85, "max_hours": 1,
                                                   "max_spread": 0.02}})
    decisions = run_autotune(led, cfg, data)
    assert [d["employee"] for d in decisions] == ["nickel_picker"]
    rec = hr.load_roster(led, ["nickel_picker"])["nickel_picker"]
    assert rec.params.get("max_price", 0) >= 0.93  # website-visible override written
    assert any(e["kind"] == "tune" for e in led.events_since())
    assert hr.load_policy(led)["autotune"]["requested_at"] is None


def test_autotune_due():
    p = hr.load_policy(Ledger(":memory:"))
    assert autotune_due(p)  # never run
    p["autotune"]["last_run"] = datetime.now(timezone.utc).isoformat()
    assert not autotune_due(p)
    p["autotune"]["requested_at"] = datetime.now(timezone.utc).isoformat()
    assert autotune_due(p)
