"""HR: roster defaults, website overrides, suspensions, reviews, bonuses, seasons."""

from datetime import datetime, timedelta, timezone

import pytest

from desk import hr
from desk.kalshi.models import Side
from desk.paper.account import PaperAccount
from desk.paper.ledger import Ledger

NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


def test_new_hires_get_sensible_defaults():
    led = Ledger(":memory:")
    roster = hr.load_roster(led, ["sniper", "dart_monkey", "market_maker"])
    assert roster["sniper"].level == 1 and not roster["sniper"].control
    assert roster["dart_monkey"].control and not roster["dart_monkey"].autotune
    assert roster["market_maker"].level == 0  # unproven strategies start as interns
    assert [e["kind"] for e in led.events_since()].count("hr") == 3


def test_website_overrides_layer_on_yaml_and_fired_are_excluded():
    roster = {"a": hr.EmployeeRecord("a", params={"min_edge": 0.09}),
              "b": hr.EmployeeRecord("b", status="fired")}
    cfg = hr.effective_strategy_config({"a": {"min_edge": 0.04, "max_bet": 25}, "b": {}}, roster)
    assert cfg["a"] == {"min_edge": 0.09, "max_bet": 25}
    assert cfg["b"]["enabled"] is False


def test_suspension_expires():
    led = Ledger(":memory:")
    rec = hr.EmployeeRecord("x", status="suspended", suspended_until=(NOW + timedelta(days=1)).isoformat())
    assert not rec.is_working(NOW)
    assert rec.is_working(NOW + timedelta(days=2))
    roster = {"x": rec}
    assert hr.reinstate_expired(led, roster, NOW + timedelta(days=2)) == ["x"]
    assert roster["x"].status == "active"


def test_transfers_are_capital_not_profit():
    led = Ledger(":memory:")
    led.ensure_account("a", 1000)
    led.record_transfer("a", 250, "bonus")
    acct = led.load_accounts(1000, ["a"])["a"]
    assert acct.cash == 1250 and acct.capital == 1250
    from desk.paper.scoreboard import scoreboard_rows
    assert scoreboard_rows({"a": acct}, led)[0].pnl == 0


def _settle(led, key, pnl, n=1, ts=None):
    for _ in range(n):
        led.record_settlement(key, f"T-{key}", 1.0, pnl / n, ts=ts)


def test_review_awards_promotes_demotes_and_suspends():
    led = Ledger(":memory:")
    keys = ["star", "ok", "bad_senior", "bad_intern", "dart_monkey"]
    roster = hr.load_roster(led, keys)
    roster["bad_senior"].level = 2
    roster["bad_intern"].level, roster["bad_intern"].strikes = 0, 1
    accounts = {k: PaperAccount(k, 1000) for k in keys}
    policy = hr.load_policy(led)
    policy["last_review"] = (NOW - timedelta(days=7)).isoformat()
    when = (NOW - timedelta(days=1)).isoformat()
    _settle(led, "star", 80, n=25, ts=when)
    _settle(led, "ok", 5, n=25, ts=when)
    _settle(led, "bad_senior", -50, n=25, ts=when)
    _settle(led, "bad_intern", -50, n=25, ts=when)
    _settle(led, "dart_monkey", 500, n=25, ts=when)  # control group: never rewarded

    actions = hr.run_review(led, roster, accounts, policy, NOW)
    kinds = {(a["strategy"], a["kind"], a.get("action")) for a in actions}
    assert ("star", "award", None) in kinds
    assert accounts["star"].cash == 1250 and policy["reserve"] == 4750
    assert roster["star"].level == 2  # promoted
    assert roster["ok"].level == 1  # unchanged
    assert roster["bad_senior"].level == 1  # demoted
    assert roster["bad_intern"].status == "suspended"  # second strike at Intern
    assert roster["dart_monkey"].level == 1 and roster["dart_monkey"].awards == 0
    assert hr.load_policy(led)["last_review"] == NOW.isoformat()


def test_review_skips_employees_with_too_few_bets():
    led = Ledger(":memory:")
    roster = hr.load_roster(led, ["a"])
    policy = hr.load_policy(led)
    policy["last_review"] = (NOW - timedelta(days=7)).isoformat()
    _settle(led, "a", 100, n=3, ts=(NOW - timedelta(days=1)).isoformat())
    actions = hr.run_review(led, roster, {"a": PaperAccount("a", 1000)}, policy, NOW)
    assert [a["kind"] for a in actions] == ["review"]


def test_drawdown_suspension():
    led = Ledger(":memory:")
    roster = hr.load_roster(led, ["a"])
    policy = hr.load_policy(led)
    policy["last_review"] = (NOW - timedelta(days=7)).isoformat()
    when = (NOW - timedelta(days=1)).isoformat()
    _settle(led, "a", 10, n=25, ts=when)
    led.record_equity("a", 1000, 1000, ts=when)
    led.record_equity("a", 600, 600, ts=when)
    hr.run_review(led, roster, {"a": PaperAccount("a", 1000)}, policy, NOW)
    assert roster["a"].status == "suspended"


def test_new_season_starts_fresh_but_keeps_history():
    led = Ledger(":memory:")
    led.ensure_account("a", 1000)
    led.record_fill("a", "T", Side.YES, 10, 0.5, 0.1)
    assert led.load_accounts(1000, ["a"])["a"].cash == pytest.approx(994.9)
    led.set_setting("desk", {"season": 2})
    assert led.refresh_season() == 2
    assert led.load_accounts(1000, ["a"])["a"].cash == 1000
    assert led.fills() == []
    assert len(led._rows("SELECT * FROM fills")) == 1  # season 1 kept
