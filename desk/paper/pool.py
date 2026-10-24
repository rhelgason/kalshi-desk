"""
The office pool: one pot of money every employee (except the control group)
bets out of, the way one real Kalshi account would be.

Bet sizes follow the pool, not a fixed dollar amount:

  bet = pool equity x bet_pct x level multiplier (Intern 0.5x ... VP/Partner 2x)

so when the pool grows every bet grows with it, and when it shrinks they shrink.
Three guardrails keep one bad day from sinking the office:

  window cap   all employees together hold at most `window_cap` of the pool in
               any one market window (bets in the same 15 minutes win or lose together)
  daily stop   once the pool is down `daily_stop` since midnight, nobody starts a
               new bet until tomorrow (open bets still settle)
  slump brake  while the pool is more than `brake_drawdown` below its high, every
               bet is cut to `brake_factor` of its size, until it recovers

and `max_bet` (dollars, 0 = none) stops a grown pool's bets outgrowing what
these markets can fill: past it the pool still grows, the bets stop growing.

A 55-day replay of the patient twins (research/fast_bot/sizing*.py) picked the numbers:
1% per bet grew the pool if the backtests were even half right and lost ~5%
if there was no edge at all; at 2%+ a bad stretch could halve the pool.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from desk.paper.account import PaperAccount


def event_of(ticker: str) -> str:
    """KXBTC15M-26OCT140930-30 -> KXBTC15M-26OCT140930 (one window)."""
    return ticker.rsplit("-", 1)[0] if ticker.count("-") >= 2 else ticker


@dataclass
class PoolState:
    """What the pool remembers between runs."""

    day: Optional[str] = None  # local date that `day_open` belongs to
    day_open: float = 0.0  # pool equity at the start of that day
    peak: float = 0.0  # highest pool equity this season
    stopped_at: Optional[str] = None  # when today's daily stop kicked in
    capital: Optional[float] = None  # money put in, as of the last update

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "PoolState":
        return cls(**{k: v for k, v in (d or {}).items() if k in cls.__dataclass_fields__})


class Pool:
    def __init__(self, settings: dict, members: Iterable[str], state: Optional[PoolState] = None):
        self.settings = settings
        self.members = set(members)
        self.state = state or PoolState()
        self.equity = 0.0  # set by update() each tick

    # Money ---------------------------------------------------------------

    def total_equity(self, accounts: dict[str, PaperAccount], marks: dict[str, float]) -> float:
        return sum(a.equity(marks) for k, a in accounts.items() if k in self.members)

    def capital(self, accounts: dict[str, PaperAccount]) -> float:
        """Money put into the pool (starting cash plus any transfers)."""
        return sum(a.capital for k, a in accounts.items() if k in self.members)

    def free_cash(self, accounts: dict[str, PaperAccount], resting: list) -> float:
        cash = sum(a.cash for k, a in accounts.items() if k in self.members)
        held = sum(o.price * o.remaining for o in resting if o.strategy in self.members)
        return cash - held

    def exposure(self, event: str, accounts: dict[str, PaperAccount], resting: list) -> float:
        """Dollars the pool has riding on one window: bets held plus bids waiting."""
        held = sum(p.yes_cost + p.no_cost for k, a in accounts.items() if k in self.members
                   for t, p in a.positions.items() if event_of(t) == event)
        waiting = sum(o.price * o.remaining for o in resting
                      if o.strategy in self.members and event_of(o.ticker) == event)
        return held + waiting

    def in_play(self, accounts: dict[str, PaperAccount], resting: list) -> float:
        held = sum(a.cost_basis() for k, a in accounts.items() if k in self.members)
        return held + sum(o.price * o.remaining for o in resting if o.strategy in self.members)

    # The day, the high, and the guardrails --------------------------------

    def _today(self, now: datetime) -> str:
        return now.astimezone(ZoneInfo(self.settings.get("timezone") or "UTC")).date().isoformat()

    def update(self, equity: float, now: datetime, capital: Optional[float] = None) -> None:
        """
        Call once per tick with the pool's current equity (and the money put in). When money
        joins or leaves (someone hired or let go, a deposit), the day's start and the high move
        by the same amount, so it never counts as a gain or a loss.
        """
        self.equity = equity
        if capital is not None:
            if self.state.capital is not None and abs(capital - self.state.capital) > 1e-6:
                moved = capital - self.state.capital
                if self.state.day_open > 0:
                    self.state.day_open += moved
                if self.state.peak > 0:
                    self.state.peak += moved
            self.state.capital = capital
        today = self._today(now)
        if self.state.day != today:
            self.state.day, self.state.day_open, self.state.stopped_at = today, equity, None
        self.state.peak = max(self.state.peak, equity)
        if self.stopped and not self.state.stopped_at:
            self.state.stopped_at = now.isoformat()

    @property
    def today(self) -> float:
        """Change since midnight, as a share of the pool then."""
        return self.equity / self.state.day_open - 1 if self.state.day_open > 0 else 0.0

    @property
    def stopped(self) -> bool:
        return self.state.day_open > 0 and self.today <= -float(self.settings["daily_stop"])

    @property
    def braked(self) -> bool:
        return self.state.peak > 0 and self.equity < self.state.peak * (1 - float(self.settings["brake_drawdown"]))

    def bet_dollars(self, multiplier: float) -> float:
        """How much one bet should be at this level, right now."""
        size = max(self.equity, 0.0) * float(self.settings["bet_pct"]) * multiplier
        size = size * float(self.settings["brake_factor"]) if self.braked else size
        cap = float(self.settings.get("max_bet") or 0)
        return min(size, cap) if cap > 0 else size

    def window_room(self, event: str, accounts: dict[str, PaperAccount], resting: list) -> float:
        cap = max(self.equity, 0.0) * float(self.settings["window_cap"])
        return cap - self.exposure(event, accounts, resting)

    def summary(self, accounts: dict[str, PaperAccount], resting: list) -> dict:
        """For the dashboard."""
        capital = self.capital(accounts)
        return {
            "equity": round(self.equity, 2),
            "capital": round(capital, 2),
            "pnl": round(self.equity - capital, 2),
            "cash": round(self.free_cash(accounts, resting), 2),
            "in_play": round(self.in_play(accounts, resting), 2),
            "day_open": round(self.state.day_open, 2),
            "today": round(self.today, 4),
            "peak": round(self.state.peak, 2),
            "stopped": self.stopped,
            "stopped_at": self.state.stopped_at,
            "braked": self.braked,
            "bet": round(self.bet_dollars(1.0), 2),
            "window_cap": round(max(self.equity, 0.0) * float(self.settings["window_cap"]), 2),
            "settings": self.settings,
            "members": sorted(self.members),
        }


class PoolAccountView:
    """What a pool member's strategy sees: its own positions, but the pool's free cash."""

    def __init__(self, account: PaperAccount, cash: float):
        self._account = account
        self.cash = cash

    def __getattr__(self, name):
        return getattr(self._account, name)
