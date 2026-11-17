"""
The safety layer for real money. Every real order asks the guard first.

  Two keys      real orders need `trading: live` in desk.yaml AND the
                KALSHI_LIVE_TRADING=yes environment variable (set on the host),
                plus a Kalshi API key. Any one missing and nothing is sent.
  Kill switch   the `trading` row in settings: {"halted": true, ...}. The
                website's button sets it; so does the bot itself when something
                looks wrong (a loss limit, the books not matching Kalshi). While
                halted, no new orders go out and waiting ones are cancelled.
                Only a person can resume (website or `python -m desk resume`).
                A long pause ({"long": true}, or any halt older than a day)
                also turns the phone widget and the dashboard back to Training.
  Hard limits   independent of the pool's own rules, in desk.yaml `live:`:
                largest single order, orders per day, and the most the pool may
                lose in a day before trading halts (the pool's daily stop only
                pauses until midnight; this one waits for you).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from desk.paper.ledger import Ledger

logger = logging.getLogger(__name__)

SETTING = "trading"
BOOKS = "_live_books"  # status row: the reconciliation baseline, strikes and last result
ENV_SWITCH = "KALSHI_LIVE_TRADING"

DEFAULT_LIMITS = {
    "max_order_dollars": 40.0,  # no single order above this, whatever the pool says
    # ...or, when set, this share of the pool instead: only a seatbelt against a sizing bug, since levels cap a bet at
    # 2x bet_pct (11-04, owner: a dollar cap would refuse a promoted employee's bets as the pool grows)
    "max_order_pct": None,
    "max_orders_per_day": 300,
    "max_daily_loss": 150.0,  # dollars down since midnight: halt until resumed
    # ...or, when set, this share of the pool at midnight instead (11-04: a dollar limit goes stale as the pool grows)
    "max_daily_loss_pct": None,
    "max_drift": 2.0,  # dollars the books may differ from Kalshi's balance
}


def env_allows_live() -> bool:
    return os.getenv(ENV_SWITCH, "").strip().lower() in ("yes", "true", "1", "on")


def _now() -> datetime:
    return datetime.now(timezone.utc)


LOSS_HALT = "the pool lost"  # how the daily-loss halt's reason starts (check_loss lifts only its own)


class Guard:
    def __init__(self, ledger: Ledger, limits: Optional[dict] = None):
        self.ledger = ledger
        self.limits = {**DEFAULT_LIMITS, **(limits or {})}
        self.state: dict = {}
        self.refresh()

    # The kill switch -------------------------------------------------------

    def refresh(self) -> dict:
        """Re-read the switch (the website may have flipped it)."""
        self.state = self.ledger.get_setting(SETTING) or {"halted": False}
        return self.state

    @property
    def halted(self) -> bool:
        return bool(self.state.get("halted"))

    def halt(self, reason: str, by: str = "bot", long: bool = False) -> None:
        if self.halted:
            return
        self.state = {"halted": True, "reason": reason, "by": by, "at": _now().isoformat()}
        if long:
            self.state["long"] = True
        self.ledger.set_setting(SETTING, self.state)
        self.ledger.record_event("trading", {"action": "halted", "reason": reason, "by": by, "long": long})
        logger.error("REAL TRADING HALTED by %s: %s", by, reason)
        from desk import notify

        notify.paused(reason, by)

    def resume(self, by: str = "manager") -> None:
        """Trade again. The books are re-baselined against Kalshi on the next run."""
        self.state = {"halted": False, "resumed_by": by, "at": _now().isoformat()}
        self.ledger.set_setting(SETTING, self.state)
        self.save_books({})
        self.ledger.record_event("trading", {"action": "resumed", "by": by})
        logger.warning("Real trading resumed by %s", by)

    # Reconciliation memory ---------------------------------------------------

    def books(self) -> dict:
        return self.ledger.get_status(BOOKS) or {}

    def save_books(self, books: dict) -> None:
        self.ledger.set_status(BOOKS, books)

    # Per-order checks ------------------------------------------------------

    def orders_today(self) -> int:
        start = _now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        return int(self.ledger._rows("SELECT count(*) AS n FROM orders WHERE ts >= ?", (start,))[0]["n"])

    def max_order(self) -> float:
        pct, equity = self.limits.get("max_order_pct"), getattr(self, "equity", 0.0)
        return equity * float(pct) if pct and equity > 0 else float(self.limits["max_order_dollars"])

    def refuse(self, dollars: float) -> Optional[str]:
        """None if a real order of `dollars` may go out; otherwise why not."""
        if self.halted:
            return f"trading halted: {self.state.get('reason') or 'by the manager'}"
        limit = self.max_order()
        if dollars > limit + 1e-9:
            return f"order over the ${limit:,.2f} limit"
        if self.orders_today() >= int(self.limits["max_orders_per_day"]):
            return f"{int(self.limits['max_orders_per_day'])} orders today: the daily limit"
        return None

    def check_loss(self, equity: float, day_open: float, day: Optional[str] = None) -> None:
        """
        Halt if the pool has lost more than the hard daily limit. `day` (the pool's local date) makes the halt a
        daily one (11-17): it lifts itself when a new day starts, and a manager's resume the same day sticks (the
        pool's own daily stop still holds new bets until midnight). Without `day`: halt until resumed, as before.
        """
        if day:
            self.refresh()  # the switch as it is now: a resume from the site mid-run must not be written over
        if self.halted:
            if day and str(self.state.get("reason", "")).startswith(LOSS_HALT):
                if not self.state.get("day"):
                    self._mark_day(day)
                elif self.state["day"] != day:
                    self.resume(by=f"the daily-loss stop (a new day, {day})")
            return
        if day and self.state.get("resumed_by") and not self.state.get("day"):
            self._mark_day(day)
        lost = day_open - equity
        pct = self.limits.get("max_daily_loss_pct")
        limit = day_open * float(pct) if pct else float(self.limits["max_daily_loss"])
        if day_open > 0 and lost > limit:
            by = str(self.state.get("resumed_by") or "")
            if day and by and not by.startswith("the ") and self.state.get("day") == day:
                return  # the manager resumed after today's stop: their call (automatic resumes start "the ...")
            share = f"{float(pct):.0%} of the pool, " if pct else ""
            self.halt(f"{LOSS_HALT} ${lost:,.2f} today (limit {share}${limit:,.2f})")
            if day:
                self._mark_day(day)

    def _mark_day(self, day: str) -> None:
        """Note the day on the switch, unless someone flipped it since we read it (then theirs stands)."""
        now = self.ledger.get_setting(SETTING) or {"halted": False}
        if now.get("at") != self.state.get("at") or bool(now.get("halted")) != self.halted:
            self.state = now
            return
        self.state["day"] = day
        self.ledger.set_setting(SETTING, self.state)
