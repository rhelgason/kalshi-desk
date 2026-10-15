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


def _settle(led, key, pnl, n=1, ts=None, stake=10.0):
    """n settled $10 bets that made `pnl` in total."""
    for i in range(n):
        led.record_fill(key, f"T-{key}-{i}", Side.YES, stake / 0.5, 0.5, 0.0, ts=ts)
        led.record_settlement(key, f"T-{key}-{i}", 1.0, pnl / n, ts=ts)


def test_review_awards_promotes_demotes_and_suspends():
    led = Ledger(":memory:")
    keys = ["star", "ok", "bad_senior", "bad_intern", "dart_monkey"]
    roster = hr.load_roster(led, keys)
    roster["bad_senior"].level = 2
    roster["bad_intern"].level, roster["bad_intern"].strikes = 0, 1
    accounts = {k: PaperAccount(k, 1000) for k in keys}
    policy = hr.load_policy(led)
    policy["last_review"] = (NOW - timedelta(days=7)).isoformat()
    policy["award_bonus"], policy["reserve"] = 250.0, 5000.0  # bonuses are off by default with the pool
    when = (NOW - timedelta(days=1)).isoformat()
    _settle(led, "star", 80, n=25, ts=when)
    _settle(led, "ok", 2, n=25, ts=when)  # +0.8c per $1: neither
    _settle(led, "bad_senior", -50, n=25, ts=when)
    _settle(led, "bad_intern", -50, n=25, ts=when)
    _settle(led, "dart_monkey", 500, n=25, ts=when)  # control group: never rewarded

    actions = hr.run_review(led, roster, accounts, policy, NOW, evidence={"star": {"confidence": 0.9, "bets": 60}})
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


def test_losing_a_tenth_of_the_pool_alone_means_suspension():
    led = Ledger(":memory:")
    roster = hr.load_roster(led, ["a", "b"])
    policy = hr.load_policy(led)
    policy["last_review"] = (NOW - timedelta(days=7)).isoformat()
    when = (NOW - timedelta(days=1)).isoformat()
    _settle(led, "a", -110, n=25, ts=when)  # $110 of a $1,000 pool
    _settle(led, "b", -90, n=25, ts=when)
    accounts = {"a": PaperAccount("a", 500), "b": PaperAccount("b", 500)}
    hr.run_review(led, roster, accounts, policy, NOW)
    assert roster["a"].status == "suspended"
    assert roster["b"].status == "active" and roster["b"].level == 0  # demoted instead


def test_a_bad_week_doesnt_demote_a_proven_employee():
    led = Ledger(":memory:")
    roster = hr.load_roster(led, ["pro"])
    policy = hr.load_policy(led)
    policy["last_review"] = (NOW - timedelta(days=7)).isoformat()
    _settle(led, "pro", -20, n=25, ts=(NOW - timedelta(days=1)).isoformat())
    actions = hr.run_review(led, roster, {"pro": PaperAccount("pro", 1000)}, policy, NOW,
                            evidence={"pro": {"confidence": 0.9, "bets": 60}})
    assert roster["pro"].level == 1
    assert any(a.get("action") == "kept" for a in actions)


def test_reviews_judge_profit_per_dollar_bet():
    led = Ledger(":memory:")
    roster = hr.load_roster(led, ["big", "small"])
    policy = hr.load_policy(led)
    policy["last_review"] = (NOW - timedelta(days=7)).isoformat()
    when = (NOW - timedelta(days=1)).isoformat()
    _settle(led, "big", 30, n=25, ts=when, stake=100)  # +1.2c per $1 on big bets: not enough
    _settle(led, "small", 10, n=25, ts=when)  # +4c per $1
    hr.run_review(led, roster, {k: PaperAccount(k, 1000) for k in roster}, policy, NOW,
                  evidence={"big": {"confidence": 0.9, "bets": 60}, "small": {"confidence": 0.9, "bets": 60}})
    assert (roster["big"].level, roster["small"].level) == (1, 2)


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


def test_good_period_without_evidence_is_held_back():
    led = Ledger(":memory:")
    roster = hr.load_roster(led, ["lucky"])
    policy = hr.load_policy(led)
    policy["last_review"] = (NOW - timedelta(days=7)).isoformat()
    _settle(led, "lucky", 80, n=25, ts=(NOW - timedelta(days=1)).isoformat())
    actions = hr.run_review(led, roster, {"lucky": PaperAccount("lucky", 1000)}, policy, NOW,
                            evidence={"lucky": {"confidence": 0.62, "bets": 60}})
    assert roster["lucky"].level == 1
    held = [a for a in actions if a.get("action") == "held back"]
    assert held and "62%" in held[0]["why"]
    # Still wins the award: that's about the period, not proof of skill
    assert any(a["kind"] == "award" for a in actions)


def test_new_season_splits_the_pool_and_relevels():
    led = Ledger(":memory:")
    hr.load_roster(led, ["a", "b", "dart_monkey"])
    detail = hr.start_season(led, ["a", "b", "dart_monkey"], 1000, 500, levels={"a": 2}, why="track record", now=NOW)
    assert detail["season"] == 2 and led.season == 2 and detail["members"] == ["a", "b"]
    accounts = led.load_accounts(0, ["a", "b", "dart_monkey"])
    assert (accounts["a"].cash, accounts["b"].cash, accounts["dart_monkey"].cash) == (500, 500, 500)
    assert hr.load_roster(led, ["a"])["a"].level == 2
    policy = hr.load_policy(led)
    assert policy["award_bonus"] == 0 and policy["last_review"] == NOW.isoformat()
    assert any("re-leveled" in str(e) for e in led.events_since())


def test_too_few_bets_neither_promote_nor_protect():
    # 92% sure, but on 12 bets: the score itself says "too early to tell"
    led = Ledger(":memory:")
    roster = hr.load_roster(led, ["new", "slump"])
    roster["slump"].level = 2
    policy = hr.load_policy(led)
    policy["last_review"] = (NOW - timedelta(days=7)).isoformat()
    when = (NOW - timedelta(days=1)).isoformat()
    _settle(led, "new", 80, n=25, ts=when)
    _settle(led, "slump", -50, n=25, ts=when)
    actions = hr.run_review(led, roster, {k: PaperAccount(k, 1000) for k in roster}, policy, NOW,
                            evidence={"new": {"confidence": 0.92, "bets": 12}, "slump": {"confidence": 0.92, "bets": 12}})
    assert roster["new"].level == 1 and roster["slump"].level == 1  # held back; demoted
    held = next(a for a in actions if a.get("action") == "held back")
    assert "12 of 30 bets" in held["why"]


def test_twins_follow_their_siblings_settings():
    base = {"nickel_picker": {"min_price": 0.88, "stake": 10}, "nickel_maker": {"min_price": 0.88},
            "breakout": {"min_move": 0.002}}
    roster = {k: hr.EmployeeRecord(k) for k in ("nickel_picker", "nickel_maker", "breakout", "breakout_maker")}
    roster["nickel_picker"].params = {"min_price": 0.85}  # autotune moved Nick
    roster["breakout_maker"].params = {"max_price": 0.55}  # set on purpose for Bonnie
    cfg = hr.effective_strategy_config(base, roster)
    assert cfg["nickel_maker"] == {"min_price": 0.85, "stake": 10}
    assert cfg["breakout_maker"] == {"min_move": 0.002, "max_price": 0.55}
    roster["nickel_picker"].status = "fired"
    assert "enabled" not in hr.effective_strategy_config(base, roster)["nickel_maker"]  # Nora keeps working
