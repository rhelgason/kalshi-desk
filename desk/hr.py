"""
HR: who works today, how big they bet, and the performance-review cycle.

Everything here is driven by two tables the website can edit:

  employees   per-employee record: status (active / suspended / fired),
              suspended_until, level, strikes, setting overrides, autotune on/off,
              control-group flag, award count
  settings    "desk" row: season, review rules, the desk reserve, autotune policy

Everyone except the control group trades out of one office pool, and every bet
is a share of it (`pool.bet_pct`, 1% for an Associate) times their level:

  0 Intern 0.5x · 1 Associate 1x · 2 Senior 1.5x · 3 VP 2x · 4 Partner 2x

So a promotion means bigger bets with the same strategy, and as the pool grows
or shrinks every bet grows or shrinks with it. Desk-wide guardrails (runner.py):
at most `pool.window_cap` of the pool in any one 15-minute window, nobody bets
after the pool loses `pool.daily_stop` in a day, and bets are halved while the
pool is more than `pool.brake_drawdown` below its high.

Each review period (default 7 days) the review:
  - names an Employee of the Week/Month (best profit in the period); a bonus is
    only paid if `award_bonus` is set (off with the pool: it would be money from nowhere)
  - judges the period by profit per dollar bet: promotes employees above
    `promote_roi` (if the season's evidence says it isn't luck), demotes ones
    below `demote_roi` (unless the season's evidence still says they have an edge)
  - gives a strike for a bad period at the Intern level; enough strikes and the
    employee is suspended for `suspend_days` (or fired, if auto_fire is on)
  - suspends anyone who alone lost more than `max_loss_suspend` of the pool in the period
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
from desk.paper.evidence import MIN_BETS
from desk.paper.ledger import Ledger

logger = logging.getLogger(__name__)

LEVELS = [("Intern", 0.5), ("Associate", 1.0), ("Senior", 1.5), ("VP", 2.0), ("Partner", 2.0)]
CONTROL_GROUP = {"dart_monkey", "longshot_buy"}
# The patient twins: same picks as a sibling, but they post a bid and wait instead
# of paying the ask. They follow the sibling's settings (including autotune's
# changes), so the only difference between the two is how they buy.
TWINS = {"nickel_maker": "nickel_picker", "early_maker": "early_favorite", "breakout_maker": "breakout",
         "heavy_maker": "heavy_favorite"}
# Employees that start at the bottom when first hired (unproven strategies)
START_AS_INTERN = {"breakout", "early_favorite", "nickel_maker", "early_maker", "breakout_maker", "favorite_sports", "market_maker",
                   "runner_up_maker"}

DEFAULT_POLICY: dict[str, Any] = {
    "season": 1,
    "review_days": 7,
    "min_settled": 20,  # settled bets needed in a period to be reviewed
    "promote_roi": 0.02,  # +2 cents per $1 bet in the period
    # ...and the skill-or-luck confidence (season to date) must be at least this
    "promote_min_confidence": 0.8,
    "demote_roi": -0.03,  # -3 cents per $1 bet in the period
    # ...unless the season's evidence is still at least this sure of an edge
    "demote_max_confidence": 0.5,
    "strikes_to_suspend": 2,
    "suspend_days": 7,
    "max_loss_suspend": 0.10,  # one employee losing 10% of the pool in a period
    "auto_fire": False,
    "strikes_to_fire": 4,
    "award_bonus": 0.0,
    "reserve": 0.0,  # paper money the desk can hand out as bonuses
    # The office pool: how much of it each bet and each window may use
    "pool": {
        "bet_pct": 0.01,  # an Associate's bet; levels scale it (Intern 0.5%, VP/Partner 2%)
        "window_cap": 0.03,  # all employees together, in any one 15-minute window
        "daily_stop": 0.10,  # no new bets once the pool is down this much since midnight
        "brake_drawdown": 0.25,  # this far below the pool's high...
        "brake_factor": 0.5,  # ...every bet is cut to this
        "timezone": "America/Vancouver",  # whose midnight starts the day
    },
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
    """
    desk.yaml settings with the website's overrides on top. Fired employees are
    left out. A twin starts from its sibling's settings (desk.yaml plus the
    sibling's overrides, e.g. from autotune), then its own on top.
    """
    out = {}
    keys = set(base) | set(roster)
    for k in keys:
        cfg = {}
        sibling = TWINS.get(k)
        if sibling:
            cfg.update({p: v for p, v in (base.get(sibling) or {}).items() if p != "enabled"})
        cfg.update(base.get(k) or {})
        if sibling and roster.get(sibling):
            cfg.update(roster[sibling].params or {})
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
    wagered: float = 0.0  # dollars bet on the markets that settled in the period

    @property
    def roi(self) -> float:
        """Profit per dollar bet (bet sizes follow the pool, so this is the fair yardstick)."""
        return self.pnl / self.wagered if self.wagered else 0.0


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
    bet = ledger._rows(
        "SELECT f.strategy, SUM(f.count * f.price + f.fee) AS wagered FROM fills f"
        " JOIN settlements s ON s.strategy = f.strategy AND s.ticker = f.ticker AND s.season = f.season"
        " WHERE s.season = ? AND s.ts >= ? GROUP BY f.strategy",
        (ledger.season, since_iso),
    )
    dd = {r["strategy"]: (1 - r["lo"] / r["hi"]) if r["hi"] else 0.0 for r in eq}
    wagered = {r["strategy"]: float(r["wagered"] or 0) for r in bet}
    out = {}
    for k, acct in accounts.items():
        r = next((x for x in rows if x["strategy"] == k), None)
        out[k] = PeriodStats(k, float(r["pnl"]) if r else 0.0, int(r["n"]) if r else 0,
                             int(r["wins"]) if r else 0, acct.capital, dd.get(k, 0.0), wagered.get(k, 0.0))
    return out


def review_due(policy: dict, now: Optional[datetime] = None) -> bool:
    last = policy.get("last_review")
    if not last:
        return False  # the first review is scheduled when the season starts
    return (now or _now()) - datetime.fromisoformat(last) >= timedelta(days=float(policy["review_days"]))


def run_review(ledger: Ledger, roster: dict[str, EmployeeRecord], accounts: dict[str, PaperAccount],
               policy: dict, now: Optional[datetime] = None,
               evidence: Optional[dict[str, dict]] = None, pool: Optional[float] = None) -> list[dict]:
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
    if pool is None:  # the office pool's capital: everyone but the control group
        pool = sum(a.capital for k, a in accounts.items() if not (roster.get(k) and roster[k].control))
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
        ev = evidence.get(k) or {}
        # Under MIN_BETS the score is "too early to tell": it neither earns a
        # promotion nor protects from a demotion
        conf = float(ev.get("confidence", 0.5)) if int(ev.get("bets", 0)) >= MIN_BETS else 0.5
        if pool and -st.pnl > float(policy["max_loss_suspend"]) * pool:
            _suspend(rec, now, float(policy["suspend_days"]))
            act(k, "hr", action="suspended", why=f"lost {-st.pnl / pool:.0%} of the office pool this period",
                until=rec.suspended_until)
        elif st.roi >= float(policy["promote_roi"]) and rec.level < len(LEVELS) - 1:
            if conf >= float(policy.get("promote_min_confidence", 0.0)):
                rec.level += 1
                rec.strikes = 0
                act(k, "hr", action="promoted", to=level_title(rec.level), roi=round(st.roi, 4),
                    confidence=round(conf, 3))
            elif int(ev.get("bets", 0)) < MIN_BETS:
                act(k, "hr", action="held back", roi=round(st.roi, 4), confidence=round(conf, 3),
                    why=f"good period, but only {int(ev.get('bets', 0))} of {MIN_BETS} bets so far: too early to tell")
            else:
                act(k, "hr", action="held back", roi=round(st.roi, 4), confidence=round(conf, 3),
                    why=f"good period, but only {conf:.0%} sure it isn't luck")
        elif st.roi <= float(policy["demote_roi"]):
            if conf > float(policy.get("demote_max_confidence", 1.0)):
                act(k, "hr", action="kept", roi=round(st.roi, 4), confidence=round(conf, 3),
                    why=f"bad period, but still {conf:.0%} sure of an edge overall")
            elif rec.level > 0:
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


def run_award(ledger: Ledger, roster: dict[str, EmployeeRecord], accounts: dict[str, PaperAccount],
              policy: dict, now: Optional[datetime] = None) -> list[dict]:
    """
    The award part of a review, alone: for a book without automatic HR (real money).
    Same rule as run_review (best positive earner with enough settled bets, never
    the control group), no bonus, no level changes. Schedules the next one.
    """
    now = now or _now()
    since = datetime.fromisoformat(policy["last_review"]) if policy.get("last_review") else now - timedelta(
        days=float(policy["review_days"]))
    stats = period_stats(ledger, accounts, since)
    eligible = [k for k, r in roster.items() if r.status != "fired" and not r.control and k in stats
                and stats[k].settled >= policy["min_settled"] and stats[k].pnl > 0]
    actions = []
    if eligible:
        winner = max(eligible, key=lambda k: stats[k].pnl)
        roster[winner].awards += 1
        ledger.upsert_employee(roster[winner].to_row())
        detail = {"title": award_name(float(policy["review_days"])), "pnl": round(stats[winner].pnl, 2), "bonus": 0.0}
        ledger.record_event("award", detail, strategy=winner)
        actions.append({"strategy": winner, "kind": "award", **detail})
    policy["last_review"] = now.isoformat()
    save_policy(ledger, policy)
    return actions


def _suspend(rec: EmployeeRecord, now: datetime, days: float) -> None:
    rec.status = "suspended"
    rec.suspended_until = (now + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# A new season
# ---------------------------------------------------------------------------


def start_season(ledger: Ledger, staff: list[str], pool_cash: float, control_cash: float,
                 levels: Optional[dict[str, int]] = None, why: str = "", now: Optional[datetime] = None) -> dict:
    """
    Start everyone fresh: split `pool_cash` evenly across the office pool's members
    (the staff minus the control group), give each control employee `control_cash`,
    optionally re-level people, and schedule the first review a period from now.
    Old seasons' rows stay in the records.
    """
    now = now or _now()
    roster = load_roster(ledger, staff)
    members = [k for k in staff if not roster[k].control]
    for k in staff:
        ledger.set_starting_cash(k, pool_cash / len(members) if k in members else control_cash)
    for k, level in (levels or {}).items():
        rec = roster[k]
        if rec.level != level:
            ledger.record_event("hr", {"action": "re-leveled", "from": level_title(rec.level),
                                       "to": level_title(level), "why": why}, strategy=k)
        rec.level, rec.strikes = level, 0
        ledger.upsert_employee(rec.to_row())
    policy = load_policy(ledger)
    policy["season"] = int(policy.get("season") or 1) + 1
    policy["last_review"] = now.isoformat()
    policy["award_bonus"], policy["reserve"] = 0.0, 0.0  # bonuses would be money from nowhere
    save_policy(ledger, policy)
    ledger.refresh_season()
    detail = {"action": "new season", "season": policy["season"], "pool": pool_cash, "members": members}
    ledger.record_event("season", detail)
    return detail
