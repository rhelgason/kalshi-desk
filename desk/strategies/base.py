"""
Shared types for strategies ("employees").

Each tick the desk builds a Snapshot of the market and hands it to every
strategy. A strategy looks at it and returns TradeIntents: "I'd like to buy
these contracts at no more than these prices". The broker (paper or live)
decides what actually fills.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol

from desk.feeds.crypto import UnderlyingQuote, underlying_for_series
from desk.kalshi.fees import FeeSchedule
from desk.kalshi.models import Event, Market, Side


@dataclass
class Snapshot:
    now: datetime
    markets: dict[str, Market] = field(default_factory=dict)
    events: dict[str, Event] = field(default_factory=dict)
    underlyings: dict[str, UnderlyingQuote] = field(default_factory=dict)
    fees: dict[str, FeeSchedule] = field(default_factory=dict)
    # Recent trades by ticker (only fetched when a strategy sets wants_trades)
    trades: dict[str, list[dict]] = field(default_factory=dict)

    def fee_for(self, market: Market) -> FeeSchedule:
        return self.fees.get(market.series_ticker) or FeeSchedule()

    def underlying_for(self, market: Market) -> Optional[UnderlyingQuote]:
        sym = underlying_for_series(market.series_ticker)
        return self.underlyings.get(sym) if sym else None

    @classmethod
    def build(
        cls,
        now: datetime,
        events: list[Event] = (),
        loose_markets: list[Market] = (),
        underlyings: Optional[dict[str, UnderlyingQuote]] = None,
        fees: Optional[dict[str, FeeSchedule]] = None,
    ) -> "Snapshot":
        snap = cls(now=now, underlyings=dict(underlyings or {}), fees=dict(fees or {}))
        for m in loose_markets:
            snap.markets[m.ticker] = m
        for e in events:
            snap.events[e.event_ticker] = e
            for m in e.markets:
                m.series_ticker = m.series_ticker or e.series_ticker
                snap.markets[m.ticker] = m
        return snap


@dataclass
class Leg:
    ticker: str
    side: Side
    limit_price: float  # max price per contract we'll pay
    count: float


@dataclass
class TradeIntent:
    strategy: str
    legs: list[Leg]
    reason: str
    # For single-leg model trades: our probability that the leg's side wins
    model_prob: Optional[float] = None
    # Expected profit per contract-set after fees, by the strategy's estimate
    expected_edge: float = 0.0
    # Multi-leg arbs must fill every leg in equal size or not at all
    all_or_none: bool = False
    # For arbs: the minimum payout per contract-set, whatever happens
    guaranteed_payout: Optional[float] = None
    intent_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def tickers(self) -> list[str]:
        return [leg.ticker for leg in self.legs]


@dataclass
class Persona:
    """Flavor for the future office UI."""

    name: str
    title: str
    emoji: str
    blurb: str


class AccountView(Protocol):
    """What a strategy may know about its own paper account."""

    cash: float

    def position(self, ticker: str) -> tuple[float, float]:
        """(yes contracts, no contracts) held in `ticker`."""
        ...

    @property
    def open_tickers(self) -> set[str]:
        ...


class Strategy:
    """Base class. Subclasses set `key`, `persona`, and implement evaluate()."""

    key: str = "base"
    persona: Persona = Persona("Nobody", "Unassigned", "?", "")
    # Set True to have the runner fetch recent trades into Snapshot.trades
    wants_trades: bool = False

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.key}>"
