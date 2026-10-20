"""
The weekly bonus pot.

At each review, 10% of the week's office profit (nothing in a losing week) goes
into the pot, and the Employee of the Week gets to bet the pot ON TOP of their
normal bets the following week: each of their bets is up to twice its usual size
until the bonus is used up. Whatever they don't use goes back in the pot.

No money moves between accounts: bonus bets come out of the same shared pool as
every other bet (the window cap and real-money limits still apply), so the pool's
total only changes by what those bets win or lose. The pot is a budget, not cash.

A book's config sets the share and the pool size the pot waits for (`bonus_pot`:
real money starts at $500).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from desk.paper.ledger import Ledger

KEY = "_bonus_pot"  # status row


def load(ledger: Ledger) -> dict:
    s = ledger.get_status(KEY) or {}
    return {"pot": 0.0, "winner": None, "given": 0.0, "left": 0.0, "since": None, **s}


def save(ledger: Ledger, state: dict) -> None:
    ledger.set_status(KEY, state)


def hand_out(ledger: Ledger, settings: dict, office_pnl: float, pool: float, winner: Optional[str],
             now: datetime) -> dict:
    """Run at each review: last week's unused bonus returns, the week's share goes in, the winner gets it."""
    s = load(ledger)
    s["pot"] = round(s["pot"] + max(s["left"], 0.0), 2)
    s.update(winner=None, given=0.0, left=0.0, since=None)
    if pool >= float(settings.get("min_pool", 0)):
        added = round(float(settings.get("share", 0.1)) * max(office_pnl, 0.0), 2)
        s["pot"] = round(s["pot"] + added, 2)
        if winner and s["pot"] >= 0.01:
            s.update(winner=winner, given=s["pot"], left=s["pot"], pot=0.0, since=now.isoformat())
            ledger.record_event("bonus", {"amount": s["given"], "added": added}, strategy=winner)
    save(ledger, s)
    return s


def extra(state: dict, strategy: str, dollars: float) -> float:
    """Bonus dollars to add to this bet: up to doubling it, never more than what's left."""
    if state.get("winner") != strategy:
        return 0.0
    return max(0.0, min(dollars, float(state.get("left") or 0.0)))


def spend(ledger: Ledger, state: dict, dollars: float) -> None:
    """Take bonus dollars out (a bet or bid went out) or put them back (a bid expired: negative)."""
    if abs(dollars) < 1e-9 or not state.get("winner"):
        return
    state["left"] = round(min(max(float(state["left"]) - dollars, 0.0), float(state["given"])), 4)
    save(ledger, state)
