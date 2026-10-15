"""The run journal: a summary of every run, readable after Vercel's logs are gone."""

from datetime import datetime, timedelta, timezone

from desk.journal import RunJournal, format_runs, short_reason
from desk.paper.ledger import Ledger


def test_reasons_group_without_their_numbers():
    assert short_reason("insufficient cash ($3.10 < $9.80)") == "insufficient cash"
    assert short_reason("") == "not filled"


def test_warnings_are_deduplicated_and_capped():
    j = RunJournal()
    for i in range(40):
        j.warn("same")
        j.warn(f"different {i}")
    assert j.warnings.count("same") == 1 and len(j.warnings) == 25
    assert j.summary()["warnings"][-1] == "...and 16 more"


def test_runs_are_saved_read_back_and_pruned():
    led = Ledger(":memory:")
    old = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
    j = RunJournal()
    j.count("nickel_picker", "bets")
    j.skipped("sniper", "window cap full")
    j.info["pool"] = {"equity": 1000.0, "today": 0.0, "in_play": 10.0}
    led.record_run(j.summary(), ts=old)
    led.record_run(j.summary())
    assert len(led.recent_runs("2000-01-01")) == 2
    led.prune_runs(keep_days=14)
    runs = led.recent_runs("2000-01-01")
    assert len(runs) == 1 and runs[0]["summary"]["employees"]["sniper"] == {"skipped: window cap full": 1}
    text = format_runs(runs, verbose=True)
    assert "pool $1,000.00" in text and "skipped: window cap full 1" in text
