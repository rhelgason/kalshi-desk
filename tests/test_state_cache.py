"""The server's local copy of the saved state (desk/cloud.py read_state/write_state, 11-23)."""
from desk import cloud
from desk.paper.ledger import Ledger


def test_local_copy_is_used_until_someone_else_changes_the_row(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud, "STATE_CACHE", str(tmp_path / "cache"))
    led = Ledger(str(tmp_path / "desk.db"))
    cloud.write_state(led, {"tick_count": 5})
    calls = []
    real_get = led.get_status
    monkeypatch.setattr(led, "get_status", lambda k: calls.append(k) or real_get(k))
    assert cloud.read_state(led) == {"tick_count": 5}
    assert calls == []  # the stamp matched: the row itself wasn't read
    led.set_status(cloud.STATE_KEY, {"tick_count": 9, "season": 2})  # e.g. the website started a season
    assert cloud.read_state(led) == {"tick_count": 9, "season": 2}
    assert calls == [cloud.STATE_KEY]


def test_without_a_cache_folder_it_reads_the_database(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud, "STATE_CACHE", "")
    led = Ledger(str(tmp_path / "desk.db"))
    cloud.write_state(led, {"a": 1})
    assert cloud.read_state(led) == {"a": 1}
    assert not any(tmp_path.glob("**/*.state.json"))
