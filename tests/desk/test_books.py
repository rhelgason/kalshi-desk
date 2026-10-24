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
    assert real.trading == "live" and not real.auto_hr and pretend.trading == "paper" and pretend.auto_hr
    assert real.crypto_series == ["KXBTC15M"]
    # One employee switched off without dropping their settings or anyone else's
    assert real.strategies["dart_monkey"]["enabled"] is False
    assert real.strategies["dart_monkey"]["stake"] == pretend.strategies["dart_monkey"]["stake"]
    # Training switched its old staff off (Season 5); the real book switches its own people back on
    for k in ("nickel_maker", "sniper", "nickel_picker"):
        assert pretend.strategies[k]["enabled"] is False and real.strategies[k]["enabled"] is True
        assert {p: v for p, v in real.strategies[k].items() if p != "enabled"} == \
            {p: v for p, v in pretend.strategies[k].items() if p != "enabled"}
    assert real.strategies["heavy_favorite"]["enabled"] is False and "max_seconds" in pretend.strategies["heavy_favorite"]
    assert real.strategies["breakout_maker"]["enabled"] is False and "breakout" in pretend.strategies


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
