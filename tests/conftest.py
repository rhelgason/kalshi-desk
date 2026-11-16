import pytest

from desk import runner


@pytest.fixture(autouse=True)
def _no_recheck_wait(monkeypatch):
    """The live books' second look at Kalshi waits a few seconds; the fakes answer at once."""
    monkeypatch.setattr(runner, "RECHECK_SECONDS", 0.0)
