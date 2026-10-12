"""
Kalshi data models.

Kalshi's API (since the 2026 fixed-point migration) sends prices as dollar
strings like "0.4200" and contract counts as strings like "13.00" (fields
ending in `_dollars` and `_fp`). Everything here is parsed into floats in
dollars and contracts.

Every Kalshi market is a single book. A YES bid at $0.40 is the same thing
as a NO ask at $0.60, so the orderbook endpoint only returns bids for each
side. To buy YES you trade against NO bids, and vice versa.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class Side(str, Enum):
    YES = "yes"
    NO = "no"

    @property
    def other(self) -> "Side":
        return Side.NO if self is Side.YES else Side.YES


def _f(value, default: float = 0.0) -> float:
    """Parse a Kalshi fixed-point string (or number) into a float."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ts(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _series_from_event(event_ticker: str) -> str:
    # Event tickers are "<SERIES>-<suffix>", e.g. KXBTCD-26OCT1022
    return event_ticker.split("-", 1)[0] if event_ticker else ""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Markets and events
# ---------------------------------------------------------------------------


@dataclass
class Market:
    """One yes/no contract, e.g. "BTC above $82,900 at 10pm?"."""

    ticker: str
    event_ticker: str
    title: str = ""
    yes_sub_title: str = ""
    status: str = ""
    result: str = ""  # "yes" / "no" once determined, else ""

    # Strike structure: tells us which range of the underlying pays YES
    strike_type: str = ""  # greater, greater_or_equal, less, less_or_equal, between, ...
    floor_strike: Optional[float] = None
    cap_strike: Optional[float] = None

    # Top of book (dollars). 0 means "no quote".
    yes_bid: float = 0.0
    yes_ask: float = 0.0
    no_bid: float = 0.0
    no_ask: float = 0.0
    yes_bid_size: float = 0.0
    yes_ask_size: float = 0.0
    last_price: float = 0.0

    volume: float = 0.0
    volume_24h: float = 0.0
    open_interest: float = 0.0

    open_time: Optional[datetime] = None
    close_time: Optional[datetime] = None
    expected_expiration_time: Optional[datetime] = None

    settlement_value: Optional[float] = None
    expiration_value: str = ""
    rules_primary: str = ""
    tick_size: float = 0.01
    # Price ladder as (start, end, step), e.g. 0.1c steps under 10c and over 90c
    price_ranges: tuple = ()

    # Filled in from the parent event / series when known
    series_ticker: str = ""

    @classmethod
    def from_api(cls, d: dict, series_ticker: str = "") -> "Market":
        tick = 0.01
        ranges = d.get("price_ranges") or []
        if ranges:
            tick = _f(ranges[0].get("step"), 0.01) or 0.01
        ladder = tuple((_f(r.get("start")), _f(r.get("end")), _f(r.get("step"), 0.01)) for r in ranges)

        settlement = d.get("settlement_value_dollars")
        return cls(
            ticker=d.get("ticker", ""),
            event_ticker=d.get("event_ticker", ""),
            title=d.get("title", ""),
            yes_sub_title=d.get("yes_sub_title") or d.get("subtitle", ""),
            status=d.get("status", ""),
            result=d.get("result") or "",
            strike_type=d.get("strike_type") or "",
            floor_strike=d.get("floor_strike"),
            cap_strike=d.get("cap_strike"),
            yes_bid=_f(d.get("yes_bid_dollars")),
            yes_ask=_f(d.get("yes_ask_dollars")),
            no_bid=_f(d.get("no_bid_dollars")),
            no_ask=_f(d.get("no_ask_dollars")),
            yes_bid_size=_f(d.get("yes_bid_size_fp")),
            yes_ask_size=_f(d.get("yes_ask_size_fp")),
            last_price=_f(d.get("last_price_dollars")),
            volume=_f(d.get("volume_fp")),
            volume_24h=_f(d.get("volume_24h_fp")),
            open_interest=_f(d.get("open_interest_fp")),
            open_time=_ts(d.get("open_time")),
            close_time=_ts(d.get("close_time")),
            expected_expiration_time=_ts(d.get("expected_expiration_time")),
            settlement_value=_f(settlement) if settlement not in (None, "") else None,
            expiration_value=d.get("expiration_value") or "",
            rules_primary=d.get("rules_primary", ""),
            tick_size=tick,
            price_ranges=ladder,
            series_ticker=series_ticker or d.get("series_ticker") or _series_from_event(d.get("event_ticker", "")),
        )

    # -- convenience -------------------------------------------------------

    @property
    def is_tradeable(self) -> bool:
        return self.status in ("active", "open")

    @property
    def is_settled(self) -> bool:
        return self.result in ("yes", "no") or self.settlement_value is not None

    @property
    def mid(self) -> Optional[float]:
        """Midpoint of the YES quote, or None if one side is missing."""
        if 0 < self.yes_bid and 0 < self.yes_ask < 1:
            return (self.yes_bid + self.yes_ask) / 2
        return None

    def ask(self, side: Side) -> float:
        """Price to buy one contract of `side` right now (0 = can't)."""
        price = self.yes_ask if side is Side.YES else self.no_ask
        return price if 0 < price < 1 else 0.0

    def bid(self, side: Side) -> float:
        return self.yes_bid if side is Side.YES else self.no_bid

    def tick_at(self, price: float) -> float:
        """Smallest price step for an order at `price` (Kalshi's ladders can taper)."""
        for start, end, step in self.price_ranges:
            if start - 1e-9 <= price < end - 1e-9 and step > 0:
                return step
        return self.tick_size if not self.price_ranges else 0.01

    def seconds_to_close(self, now: Optional[datetime] = None) -> Optional[float]:
        if not self.close_time:
            return None
        return (self.close_time - (now or utcnow())).total_seconds()

    def yes_pays_at(self, value: float) -> Optional[bool]:
        """
        Does YES pay out if the underlying settles at `value`?

        Returns None for strike types we don't model (custom/structured).
        """
        lo, hi = self.floor_strike, self.cap_strike
        st = self.strike_type
        if st == "greater" and lo is not None:
            return value > lo
        if st == "greater_or_equal" and lo is not None:
            return value >= lo
        if st == "less" and hi is not None:
            return value < hi
        if st == "less_or_equal" and hi is not None:
            return value <= hi
        if st == "between" and lo is not None and hi is not None:
            return lo <= value <= hi
        return None

    @property
    def strikes(self) -> list[float]:
        return [s for s in (self.floor_strike, self.cap_strike) if s is not None]


@dataclass
class Event:
    """A group of related markets, e.g. every BTC strike for 10pm tonight."""

    event_ticker: str
    series_ticker: str
    title: str = ""
    sub_title: str = ""
    category: str = ""
    mutually_exclusive: bool = False
    strike_date: Optional[datetime] = None
    markets: list[Market] = field(default_factory=list)

    @classmethod
    def from_api(cls, d: dict) -> "Event":
        series = d.get("series_ticker", "")
        return cls(
            event_ticker=d.get("event_ticker", ""),
            series_ticker=series,
            title=d.get("title", ""),
            sub_title=d.get("sub_title", ""),
            category=d.get("category", ""),
            mutually_exclusive=bool(d.get("mutually_exclusive")),
            strike_date=_ts(d.get("strike_date")),
            markets=[Market.from_api(m, series) for m in d.get("markets") or []],
        )


# ---------------------------------------------------------------------------
# Orderbook
# ---------------------------------------------------------------------------


@dataclass
class Level:
    price: float
    size: float


@dataclass
class Fill:
    """Result of walking the book: how much we'd get and at what prices."""

    count: float
    cost: float  # total dollars paid for contracts (fees excluded)
    levels: list[Level] = field(default_factory=list)

    @property
    def avg_price(self) -> float:
        return self.cost / self.count if self.count else 0.0


@dataclass
class Orderbook:
    """
    Resting bids for each side, best (highest) price first.

    Buying YES means hitting NO bids: a NO bid at p is a YES ask at 1 - p.
    """

    ticker: str
    yes_bids: list[Level] = field(default_factory=list)
    no_bids: list[Level] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=utcnow)

    @classmethod
    def from_api(cls, ticker: str, d: dict) -> "Orderbook":
        ob = d.get("orderbook_fp", d)

        def levels(raw) -> list[Level]:
            out = [Level(_f(p), _f(q)) for p, q in (raw or [])]
            out = [lv for lv in out if lv.size > 0 and 0 < lv.price < 1]
            # The API sorts ascending (best bid last); we want best first.
            out.sort(key=lambda lv: lv.price, reverse=True)
            return out

        return cls(
            ticker=ticker,
            yes_bids=levels(ob.get("yes_dollars")),
            no_bids=levels(ob.get("no_dollars")),
        )

    def bids(self, side: Side) -> list[Level]:
        return self.yes_bids if side is Side.YES else self.no_bids

    def asks(self, side: Side) -> list[Level]:
        """Prices at which we can buy `side`, cheapest first."""
        return [Level(round(1 - lv.price, 6), lv.size) for lv in self.bids(side.other)]

    def best_bid(self, side: Side) -> float:
        bids = self.bids(side)
        return bids[0].price if bids else 0.0

    def best_ask(self, side: Side) -> float:
        asks = self.asks(side)
        return asks[0].price if asks else 0.0

    def depth_at_or_better(self, side: Side, limit_price: float) -> float:
        """Contracts of `side` buyable at prices <= limit_price."""
        return sum(lv.size for lv in self.asks(side) if lv.price <= limit_price + 1e-9)

    def walk(self, side: Side, count: float, limit_price: float = 1.0) -> Fill:
        """
        Simulate a marketable buy of `count` contracts of `side`, never paying
        more than `limit_price`. Partial fills are possible.
        """
        remaining = count
        cost = 0.0
        taken: list[Level] = []
        for lv in self.asks(side):
            if remaining <= 1e-9 or lv.price > limit_price + 1e-9:
                break
            qty = min(remaining, lv.size)
            # Kalshi supports 0.01-contract granularity
            qty = math.floor(qty * 100 + 1e-6) / 100
            if qty <= 0:
                break
            taken.append(Level(lv.price, qty))
            cost += qty * lv.price
            remaining -= qty
        return Fill(count=round(count - remaining, 2), cost=cost, levels=taken)
