"""
HR: who works today, how big they bet, and the performance-review cycle.

Everything here is driven by two tables the website can edit:

  employees   per-employee record: status (active / suspended / fired),
              suspended_until, level, strikes, setting overrides, autotune on/off,
              control-group flag, award count
  settings    "desk" row: season, review rules, the desk reserve, autotune policy

Levels scale bet sizes. A promotion means bigger bets with the same strategy:

  0 Intern 0.5x · 1 Associate 1x · 2 Senior 1.5x · 3 VP 2x · 4 Partner 3x

Each review period (default 7 days) the review:
  - names an Employee of the Week/Month (best profit in the period) and pays a
    bonus from the desk reserve into their bankroll
  - promotes employees whose return beat `promote_roi`, demotes ones below
    `demote_roi`
  - gives a strike for a bad period at the Intern level; enough strikes and the
    employee is suspended for `suspend_days` (or fired, if auto_fire is on)
  - suspends anyone whose bankroll fell more than `max_drawdown_suspend` in the period
Control-group employees (the dart monkey, the long-shot buyer) are measured but
never promoted, demoted or suspended; they're the yardstick.
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from desk.paper.account import PaperAccount
from desk.paper.ledger import Ledger

logger = logging.getLogger(__name__)

LEVELS = [("Intern", 0.5), ("Associate", 1.0), ("Senior", 1.5), ("VP", 2.0), ("Partner", 3.0)]
CONTROL_GROUP = {"dart_monkey", "longshot_buy"}
# Employees that start at the bottom when first hired (unproven strategies)
START_AS_INTERN = {"breakout", "early_favorite", "nickel_maker", "early_maker", "breakout_maker", "favorite_sports", "market_maker"}

DEFAULT_POLICY: dict[str, Any] = {
    "season": 1,
    "review_days": 7,
    "min_settled": 20,  # settled bets needed in a period to be reviewed
    "promote_roi": 0.02,  # +2% of bankroll in the period
    # ...and the skill-or-luck confidence (season to date) must be at least this
    "promote_min_confidence": 0.8,
    "demote_roi": -0.03,
    "strikes_to_suspend": 2,
    "suspend_days": 7,
    "max_drawdown_suspend": 0.30,
    "auto_fire": False,
    "strikes_to_fire": 4,
    "award_bonus": 250.0,
    "reserve": 5000.0,  # paper money the desk can hand out as bonuses
    "last_review": None,
    # Backtests assume this many contracts at the best price; the background job
    # replaces it with the median depth measured in live paper fills
    "realism": {"depth": 100.0, "samples": 0, "measured_at": None},
    "autotune": {
        "enabled": True,
        "every_hours": 24,
        "lookback_days": 45,
        "min_test_bets": 30,
        "min_improvement": 10.0,  # test-period dollars a new setting must add
        "min_confidence": 0.6,  # test-period skill-or-luck confidence a new setting needs
        "requested_at": None,
        "last_run": None,
    },
}


def level_title(level: int) -> str:
    return LEVELS[max(0, min(level, len(LEVELS) - 1))][0]


def level_multiplier(level: int) -> float:
    return LEVELS[max(0, min(level, len(LEVELS) - 1))][1]


def award_name(review_days: float) -> str:
    return "Employee of the Month" if review_days >= 28 else "Employee of the Week" if review_days >= 6 else "Employee of the Day"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Policy and roster
# ---------------------------------------------------------------------------


def load_policy(ledger: Ledger) -> dict:
    saved = ledger.get_setting("desk") or {}
    policy = copy.deepcopy(DEFAULT_POLICY)
    for k, v in saved.items():
        if isinstance(v, dict) and isinstance(policy.get(k), dict):
            policy[k].update(v)
        else:
            policy[k] = v
    return policy


def save_policy(ledger: Ledger, policy: dict) -> None:
    ledger.set_setting("desk", policy)


@dataclass
class EmployeeRecord:
    key: str
    status: str = "active"  # active | suspended | fired
    suspended_until: Optional[str] = None
    level: int = 1
    strikes: int = 0
    params: dict = field(default_factory=dict)
    autotune: bool = True
    control: bool = False
    awards: int = 0
    note: Optional[str] = None

    @classmethod
    def new(cls, key: str) -> "EmployeeRecord":
        return cls(key, level=0 if key in START_AS_INTERN else 1, control=key in CONTROL_GROUP,
                   autotune=key not in CONTROL_GROUP)

    @classmethod
    def from_row(cls, r: dict) -> "EmployeeRecord":
        params = r.get("params") or "{}"
        return cls(
            key=r["key"], status=r.get("status") or "active", suspended_until=r.get("suspended_until"),
            level=int(r.get("level") or 0), strikes=int(r.get("strikes") or 0),
            params=json.loads(params) if isinstance(params, str) else dict(params),
            autotune=bool(r.get("autotune")), control=bool(r.get("control")),
            awards=int(r.get("awards") or 0), note=r.get("note"),
        )

    def to_row(self) -> dict:
        d = asdict(self)
        d["autotune"] = int(self.autotune)
        d["control"] = int(self.control)
        return d

    @property
    def multiplier(self) -> float:
        return level_multiplier(self.level)

    def is_working(self, now: Optional[datetime] = None) -> bool:
        if self.status == "fired":
            return False
        if self.status == "suspended":
            until = self.suspended_until and datetime.fromisoformat(self.suspended_until)
            return bool(until and until <= (now or _now()))
        return True


def load_roster(ledger: Ledger, keys: list[str]) -> dict[str, EmployeeRecord]:
    """HR records for these employees, creating defaults for new hires."""
    rows = {r["key"]: EmployeeRecord.from_row(r) for r in ledger.employee_rows()}
    for k in keys:
        if k not in rows:
            rows[k] = EmployeeRecord.new(k)
            ledger.upsert_employee(rows[k].to_row())
            ledger.record_event("hr", {"action": "hired", "level": level_title(rows[k].level)}, strategy=k)
    # Only the requested staff: retired employees keep their row but aren't on the floor
    return {k: rows[k] for k in keys}


def reinstate_expired(ledger: Ledger, roster: dict[str, EmployeeRecord], now: Optional[datetime] = None) -> list[str]:
    """Bring back anyone whose suspension has run out."""
    back = []
    for rec in roster.values():
        if rec.status == "suspended" and rec.is_working(now):
            rec.status, rec.suspended_until = "active", None
            ledger.upsert_employee(rec.to_row())
            ledger.record_event("hr", {"action": "reinstated", "why": "suspension ended"}, strategy=rec.key)
            back.append(rec.key)
    return back


def effective_strategy_config(base: dict[str, dict], roster: dict[str, EmployeeRecord]) -> dict[str, dict]:
    """desk.yaml settings with the website's overrides on top. Fired employees are left out."""
    out = {}
    keys = set(base) | set(roster)
    for k in keys:
        cfg = dict(base.get(k) or {})
        rec = roster.get(k)
        if rec:
            cfg.update(rec.params or {})
            if rec.status == "fired":
                cfg["enabled"] = False
        out[k] = cfg
    return out


# ---------------------------------------------------------------------------
# Performance review
# ---------------------------------------------------------------------------


@dataclass
class PeriodStats:
    key: str
    pnl: float
    settled: int
    wins: int
    capital: float
    worst_drawdown: float

    @property
    def roi(self) -> float:
        return self.pnl / self.capital if self.capital else 0.0


def period_stats(ledger: Ledger, accounts: dict[str, PaperAccount], since: datetime) -> dict[str, PeriodStats]:
    since_iso = since.isoformat()
    rows = ledger._rows(
        "SELECT strategy, SUM(pnl) AS pnl, COUNT(*) AS n, SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins"
        " FROM settlements WHERE season = ? AND ts >= ? GROUP BY strategy",
        (ledger.season, since_iso),
    )
    eq = ledger._rows(
        "SELECT strategy, MAX(equity) AS hi, MIN(equity) AS lo FROM equity"
        " WHERE season = ? AND ts >= ? GROUP BY strategy",
        (ledger.season, since_iso),
    )
    dd = {r["strategy"]: (1 - r["lo"] / r["hi"]) if r["hi"] else 0.0 for r in eq}
    out = {}
    for k, acct in accounts.items():
        r = next((x for x in rows if x["strategy"] == k), None)
        out[k] = PeriodStats(k, float(r["pnl"]) if r else 0.0, int(r["n"]) if r else 0,
                             int(r["wins"]) if r else 0, acct.capital, dd.get(k, 0.0))
    return out


def review_due(policy: dict, now: Optional[datetime] = None) -> bool:
    last = policy.get("last_review")
    if not last:
        return False  # the first review is scheduled when the season starts
    return (now or _now()) - datetime.fromisoformat(last) >= timedelta(days=float(policy["review_days"]))


def run_review(ledger: Ledger, roster: dict[str, EmployeeRecord], accounts: dict[str, PaperAccount],
               policy: dict, now: Optional[datetime] = None,
               evidence: Optional[dict[str, dict]] = None) -> list[dict]:
    """
    Apply the review rules. Mutates roster, accounts (bonuses) and policy; returns the actions taken.

    `evidence` maps employee -> skill-or-luck evidence (desk.paper.evidence). A good
    period only earns a promotion if the season's evidence clears
    `promote_min_confidence`; otherwise the employee is "held back" for more data.
    """
    evidence = evidence or {}
    now = now or _now()
    since = datetime.fromisoformat(policy["last_review"]) if policy.get("last_review") else now - timedelta(
        days=float(policy["review_days"]))
    stats = period_stats(ledger, accounts, since)
    actions: list[dict] = []

    def act(key: Optional[str], kind: str, **detail) -> None:
        actions.append({"strategy": key, "kind": kind, **detail})
        ledger.record_event(kind, detail, strategy=key)

    working = [k for k, r in roster.items() if r.status != "fired" and k in stats]
    eligible = [k for k in working if not roster[k].control and stats[k].settled >= policy["min_settled"]]

    # Award
    award = award_name(float(policy["review_days"]))
    candidates = sorted((k for k in eligible if stats[k].pnl > 0), key=lambda k: stats[k].pnl, reverse=True)
    if candidates:
        winner = candidates[0]
        bonus = min(float(policy["award_bonus"]), float(policy["reserve"]))
        roster[winner].awards += 1
        if bonus > 0:
            policy["reserve"] = float(policy["reserve"]) - bonus
            accounts[winner].apply_transfer(bonus)
            ledger.record_transfer(winner, bonus, f"{award} bonus")
        act(winner, "award", title=award, pnl=round(stats[winner].pnl, 2), bonus=bonus)

    for k in eligible:
        rec, st = roster[k], stats[k]
        if rec.status == "suspended":
            continue
        if st.worst_drawdown > float(policy["max_drawdown_suspend"]):
            _suspend(rec, now, float(policy["suspend_days"]))
            act(k, "hr", action="suspended", why=f"bankroll fell {st.worst_drawdown:.0%} this period",
                until=rec.suspended_until)
        elif st.roi >= float(policy["promote_roi"]) and rec.level < len(LEVELS) - 1:
            conf = float((evidence.get(k) or {}).get("confidence", 0.5))
            if conf >= float(policy.get("promote_min_confidence", 0.0)):
                rec.level += 1
                rec.strikes = 0
                act(k, "hr", action="promoted", to=level_title(rec.level), roi=round(st.roi, 4),
                    confidence=round(conf, 3))
            else:
                act(k, "hr", action="held back", roi=round(st.roi, 4), confidence=round(conf, 3),
                    why=f"good period, but only {conf:.0%} sure it isn't luck")
        elif st.roi <= float(policy["demote_roi"]):
            if rec.level > 0:
                rec.level -= 1
                act(k, "hr", action="demoted", to=level_title(rec.level), roi=round(st.roi, 4))
            else:
                rec.strikes += 1
                if policy.get("auto_fire") and rec.strikes >= int(policy["strikes_to_fire"]):
                    rec.status = "fired"
                    act(k, "hr", action="fired", why=f"{rec.strikes} bad reviews as an Intern")
                elif rec.strikes >= int(policy["strikes_to_suspend"]):
                    _suspend(rec, now, float(policy["suspend_days"]))
                    act(k, "hr", action="suspended", why=f"{rec.strikes} bad reviews as an Intern",
                        until=rec.suspended_until)
                else:
                    act(k, "hr", action="strike", strikes=rec.strikes, roi=round(st.roi, 4))

    act(None, "review", standings=[
        {"key": k, "pnl": round(stats[k].pnl, 2), "roi": round(stats[k].roi, 4), "settled": stats[k].settled}
        for k in sorted(working, key=lambda k: stats[k].pnl, reverse=True)
    ], period_start=since.isoformat())

    for rec in roster.values():
        ledger.upsert_employee(rec.to_row())
    policy["last_review"] = now.isoformat()
    save_policy(ledger, policy)
    return actions


def _suspend(rec: EmployeeRecord, now: datetime, days: float) -> None:
    rec.status = "suspended"
    rec.suspended_until = (now + timedelta(days=days)).isoformat()
