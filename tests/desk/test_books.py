"""Two books side by side: the real-money pool and the pretend pool never share records."""

import re
from pathlib import Path

import pytest

from desk.config import DeskConfig
from desk.paper.ledger import BOOK_TABLES, SCHEMA, SHARED_TABLES, TABLES, qualify

ROOT = Path(__file__).resolve().parents[2]


def test_qualify_points_book_tables_at_the_schema():
    assert qualify("SELECT * FROM fills f JOIN settlements s ON fills.id = s.id", "real") == \
        "SELECT * FROM real.fills f JOIN real.settlements s ON fills.id = s.id"
    assert qualify("INSERT INTO settings(key) VALUES (?) ON CONFLICT(key) DO NOTHING", "real") == \
        "INSERT INTO real.settings(key) VALUES (?) ON CONFLICT(key) DO NOTHING"
    assert qualify("CREATE INDEX IF NOT EXISTS equity_season_ts ON equity(season, ts)", "real").endswith(
        "ON real.equity(season, ts)")
    assert qualify("ALTER TABLE status ENABLE ROW LEVEL SECURITY", "real") == \
        "ALTER TABLE real.status ENABLE ROW LEVEL SECURITY"
    # Shared market data, look-alike names and the default book are left alone
    assert qualify("SELECT data FROM market_history", "real") == "SELECT data FROM market_history"
    assert qualify("SELECT 1 FROM fills_strategy", "real") == "SELECT 1 FROM fills_strategy"
    assert qualify("SELECT * FROM fills", None) == qualify("SELECT * FROM fills", "public") == "SELECT * FROM fills"


def test_every_table_in_the_schema_is_qualified():
    created = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SCHEMA)
    assert set(created) == set(TABLES)
    assert set(BOOK_TABLES) | set(SHARED_TABLES) == set(TABLES)
    script = qualify(SCHEMA, "real")
    for t in BOOK_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS real.{t} " in script or f"CREATE TABLE IF NOT EXISTS real.{t}(" in script
        assert not re.search(rf"\bON {t}\(", script), f"index on {t} not moved to the real schema"


def test_real_book_config_inherits_and_overrides():
    pretend = DeskConfig.load(ROOT / "desk.yaml")
    real = DeskConfig.load(ROOT / "desk.real.yaml")
    assert pretend.book == "pretend" and pretend.schema == "public" and pretend.real_book == "desk.real.yaml"
    assert real.book == "real" and real.schema == "real" and real.real_book is None
    assert real.trading == "live" and real.auto_hr and pretend.trading == "paper" and pretend.auto_hr  # 11-09: both run themselves
    assert real.crypto_series == ["KXBTC15M", "KXETH15M", "KXSOL15M", "KXXRP15M", "KXDOGE15M",
                                  "KXNEAR15M", "KXBNB15M", "KXZEC15M"]  # bitcoin back 11-01; three thinner coins 11-02
    # One employee switched off without dropping their settings or anyone else's
    assert real.strategies["dart_monkey"]["enabled"] is False
    assert real.strategies["dart_monkey"]["stake"] == pretend.strategies["dart_monkey"]["stake"]
    # Only Sadie trades real money, and she is Training's only pool member too (2026-10-26)
    for k in ("heavy_favorite", "late_maker", "runner_up_maker"):
        assert real.strategies[k]["enabled"] is False and pretend.strategies[k]["enabled"] is False
    assert real.strategies["longshot_buy"]["enabled"] is False and pretend.strategies["longshot_buy"].get("enabled", True)
    # Sadie retired 10-31 (her bets went to the coin specialists) but her settings still reach them
    assert real.strategies["heavy_maker"]["enabled"] is False and pretend.strategies["heavy_maker"]["enabled"] is False
    assert "max_seconds" in real.strategies["heavy_favorite"]  # Stella's settings still reach her twin

def test_bad_book_or_schema_is_refused(tmp_path):
    (tmp_path / "x.yaml").write_text("book: imaginary\n")
    with pytest.raises(ValueError):
        DeskConfig.load(tmp_path / "x.yaml")
    from desk.paper.ledger import Ledger

    with pytest.raises(ValueError):
        Ledger(":memory:", "real; DROP TABLE fills")


def test_two_books_in_postgres(tmp_path):
    """Needs the optional `pgserver` package (a throwaway Postgres); skipped without it."""
    pgserver = pytest.importorskip("pgserver")
    from desk.kalshi.models import Side
    from desk.paper.ledger import Ledger

    srv = pgserver.get_server(str(tmp_path / "pg"), cleanup_mode="stop")
    url = srv.get_uri()
    pretend, real = Ledger(url), Ledger(url, "real")
    pretend.record_fill("dart_monkey", "KXBTC15M-X-1", Side.YES, 2, 0.5, 0.01)
    real.record_fill("nickel_maker", "KXBTC15M-X-1", Side.NO, 1, 0.9, 0.0)
    real.set_setting("trading", {"halted": True})
    assert [r["strategy"] for r in pretend._rows("SELECT strategy FROM fills")] == ["dart_monkey"]
    assert [r["strategy"] for r in real._rows("SELECT strategy FROM fills")] == ["nickel_maker"]
    assert pretend.get_setting("trading") is None and real.get_setting("trading") == {"halted": True}


async def test_hosted_run_does_real_book_first_and_survives_its_failure(monkeypatch, tmp_path):
    import desk.cloud as cloud

    (tmp_path / "desk.yaml").write_text("real_book: desk.real.yaml\n")
    (tmp_path / "desk.real.yaml").write_text("extends: desk.yaml\nbook: real\nschema: real\nreal_book: null\n")
    calls = []

    async def fake_tick(config_path=None, **kw):
        calls.append(Path(config_path).name)
        if config_path.endswith("desk.real.yaml"):
            raise RuntimeError("no Kalshi API key")
        return {"ok": True}

    monkeypatch.setattr(cloud, "run_cloud_tick", fake_tick)
    monkeypatch.setenv("KALSHI_LIVE_TRADING", "yes")
    out = await cloud.run_all_books(str(tmp_path / "desk.yaml"))
    assert calls == ["desk.real.yaml", "desk.yaml"]
    assert out["pretend"] == {"ok": True}
    assert out["real"]["ok"] is False and "no Kalshi API key" in out["real"]["error"]
    assert out["ok"] is False

    # Not set up on the host yet: the real book waits quietly
    monkeypatch.delenv("KALSHI_LIVE_TRADING")
    (tmp_path / "desk.real.yaml").write_text("extends: desk.yaml\nbook: real\nschema: real\nreal_book: null\ntrading: live\n")
    calls.clear()
    out = await cloud.run_all_books(str(tmp_path / "desk.yaml"))
    assert calls == ["desk.yaml"] and out["ok"] and "isn't set" in out["real"]["skipped"]

    (tmp_path / "desk.yaml").write_text("real_book: null\n")
    calls.clear()
    assert (await cloud.run_all_books(str(tmp_path / "desk.yaml")))["ok"] and calls == ["desk.yaml"]


def test_real_book_builds_sadies_coin_specialists():
    """Since 2026-10-31 the specialists bet the pool on Sadie's rules; Sadie herself is retired."""
    from desk.strategies import build_strategies

    real = DeskConfig.load(ROOT / "desk.real.yaml")
    staff = {s.key: s for s in build_strategies(hr_config(real))}
    assert set(staff) == {"maker_btc", "maker_eth", "maker_sol", "maker_xrp", "maker_doge", "maker_near", "maker_bnb", "maker_zec",
                          "weather_maker"}
    # Weather Wendell joined 2026-11-03 on Training's rules, with his six cities' markets
    w = staff["weather_maker"]
    assert (w.min_price, w.max_price, w.end_hour) == (0.92, 0.995, 6) and set(real.other_series) == set(w.series)
    for k, coin in (("maker_btc", "BTC"), ("maker_eth", "ETH"), ("maker_sol", "SOL"), ("maker_xrp", "XRP"), ("maker_doge", "DOGE"),
                    ("maker_near", "NEAR"), ("maker_bnb", "BNB"), ("maker_zec", "ZEC")):
        s = staff[k]
        assert s.coins == [coin] and s.odds_margin == 0.0
        assert (s.min_price, s.max_price, s.min_seconds, s.max_seconds) == (0.92, 0.99, 300, 540)
    pretend = {s.key for s in build_strategies(hr_config(DeskConfig.load(ROOT / "desk.yaml")))}
    assert {"maker_btc", "maker_eth", "maker_sol", "maker_xrp", "maker_doge"} <= pretend and "heavy_maker" not in pretend
    # The thinner coins (2026-11-02) are Training only, and Training watches their markets and prices
    assert {"maker_hype", "maker_bnb", "maker_near", "maker_zec"} <= pretend
    pretend_cfg = DeskConfig.load(ROOT / "desk.yaml")
    assert {"KXHYPE15M", "KXBNB15M", "KXNEAR15M", "KXZEC15M"} <= set(pretend_cfg.crypto_series)
    assert {"HYPE", "BNB", "NEAR", "ZEC"} <= set(pretend_cfg.crypto_symbols)


def hr_config(cfg):
    from desk import hr

    return hr.effective_strategy_config(cfg.strategies, {})


def test_hiring_onto_the_real_book_needs_no_new_season(tmp_path):
    """2026-11-09: `python -m desk hire` puts a Training employee on real money mid-season, markets and all."""
    from dataclasses import replace

    from desk import hr
    from desk.paper.ledger import Ledger
    from desk.runner import Desk

    real = replace(DeskConfig.load(ROOT / "desk.real.yaml"), db_path=str(tmp_path / "d.db"), use_database_url=False,
                   trading="paper")  # the real roster and lists, paper orders
    led = Ledger(real.db_path)
    desk = Desk(real, client=None, strategies=None, ledger=led)
    desk.sync_hr()
    assert "hourly_btc" not in {s.key for s in desk.strategies} and "KXBTCD" not in real.other_series

    assert hr.hire(led, "hourly_btc", why="test") and not hr.hire(led, "hourly_btc")
    desk.sync_hr()
    assert "hourly_btc" in {s.key for s in desk.strategies} and "hourly_btc" in desk.pool.members
    assert desk.roster["hourly_btc"].level == 0  # starts as an Intern
    assert "KXBTCD" in real.other_series and "KXHIGHNY" in real.other_series  # the yaml's list is kept
    assert "KXBTC15M" in real.crypto_series

    led.upsert_employee(replace(desk.roster["hourly_btc"], status="fired").to_row())
    desk.sync_hr()
    assert "hourly_btc" not in {s.key for s in desk.strategies}  # firing still wins over the hired list


def test_commodity_specialists_are_training_only():
    """2026-11-09: gold, oil and silver on Sadie's rules, 97c+ only; the real book must leave them out."""
    from desk.strategies import build_strategies

    pretend = {s.key: s for s in build_strategies(hr_config(DeskConfig.load(ROOT / "desk.yaml")))}
    for k, coin in (("maker_gold", "GOLD"), ("maker_wti", "WTI"), ("maker_silver", "SILVER")):
        assert pretend[k].coins == [coin] and pretend[k].min_price == 0.97 and pretend[k].max_seconds == 540
    real = {s.key for s in build_strategies(hr_config(DeskConfig.load(ROOT / "desk.real.yaml")))}
    assert not real & {"maker_gold", "maker_wti", "maker_silver"}
