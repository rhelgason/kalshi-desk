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
    "max_orders_per_day": 300,
    "max_daily_loss": 150.0,  # dollars down since midnight: halt until resumed
    "max_drift": 2.0,  # dollars the books may differ from Kalshi's balance
}


def env_allows_live() -> bool:
    return os.getenv(ENV_SWITCH, "").strip().lower() in ("yes", "true", "1", "on")


def _now() -> datetime:
    return datetime.now(timezone.utc)


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

    def halt(self, reason: str, by: str = "bot") -> None:
        if self.halted:
            return
        self.state = {"halted": True, "reason": reason, "by": by, "at": _now().isoformat()}
        self.ledger.set_setting(SETTING, self.state)
        self.ledger.record_event("trading", {"action": "halted", "reason": reason, "by": by})
        logger.error("REAL TRADING HALTED by %s: %s", by, reason)

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

    def refuse(self, dollars: float) -> Optional[str]:
        """None if a real order of `dollars` may go out; otherwise why not."""
        if self.halted:
            return f"trading halted: {self.state.get('reason') or 'by the manager'}"
        if dollars > float(self.limits["max_order_dollars"]) + 1e-9:
            return f"order over the ${float(self.limits['max_order_dollars']):g} limit"
        if self.orders_today() >= int(self.limits["max_orders_per_day"]):
            return f"{int(self.limits['max_orders_per_day'])} orders today: the daily limit"
        return None

    def check_loss(self, equity: float, day_open: float) -> None:
        """Halt if the pool has lost more than the hard daily limit."""
        lost = day_open - equity
        if day_open > 0 and lost > float(self.limits["max_daily_loss"]):
            self.halt(f"the pool lost ${lost:,.2f} today (limit ${float(self.limits['max_daily_loss']):,.0f})")
