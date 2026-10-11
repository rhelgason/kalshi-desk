"""
Structural arbitrage: trades that pay out no matter what happens.

CoverArb ("cover_arb")
    Many Kalshi markets are strike ladders on the same number at the same time:
    "BTC above $82,500?", "above $83,000?", plus range buckets like
    "$82,500 to $82,999.99?". Each YES or NO contract pays $1 on some stretch of
    possible prices. If we can cover *every* possible price with contracts that
    cost less than $1 in total (after fees), we are guaranteed a profit.

    Example: YES "above $82,500" at 60c + NO "above $83,000" at 35c = 95c.
    Below $82,500 the NO pays; above $83,000 the YES pays; in between both pay.
    Minimum payout $1, cost 95c -> 5c locked in.

    We find the cheapest cover with a small shortest-path search over the
    sorted strike points, which also finds 3+ leg combos, not just pairs.

PartitionArb ("bucket_arb")
    In a mutually exclusive event (at most one outcome can be YES, e.g. "Which
    range will CPI land in?"), buying NO on all n outcomes pays at least n - 1.
    If those NOs cost less than n - 1 in total, that's free money.
    (Buying YES on everything is only safe if the outcomes are also exhaustive,
    which we can only prove for numeric strike ranges.)
"""

from __future__ import annotations

import bisect
import math
import re
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from desk.feeds.crypto import underlying_for_series
from desk.kalshi.models import Market, Side
from desk.strategies.base import AccountView, Leg, Persona, Snapshot, Strategy, TradeIntent
from desk.strategies.pricing import outcome_points, payoff_range

logger = logging.getLogger(__name__)


_STRIKE_CHARS = re.compile(r"[\d<>=≤≥°$,.%+\-–]+")


def _title_shape(title: str) -> str:
    """Title with numbers and comparison symbols removed."""
    return " ".join(_STRIKE_CHARS.sub(" ", title.lower()).split())


def _group_key(m: Market) -> tuple:
    """
    Markets that settle on the same number at the same moment.

    Crypto ladders from different series (e.g. KXBTCD above/below and KXBTC
    ranges) share one key when they settle at the same time. Otherwise markets
    must share an event, a close time, AND the same title once strike numbers
    are stripped. That keeps "Puka Nacua: 4+ receptions" away from
    "Tyler Higbee: 5+ receptions", and "Barcelona wins by more than 1.5 goals"
    away from "Galatasaray wins by more than 1.5 goals", both of which are
    in the same event but measure different things.
    """
    sym = underlying_for_series(m.series_ticker)
    when = m.close_time.isoformat() if m.close_time else ""
    if sym:
        return (sym, when)
    return (m.event_ticker, _title_shape(m.title), when)


def _available(m: Market, side: Side) -> float:
    """Contracts offered at the best ask, from the market summary."""
    # yes_bid_size is the size of the best YES bid = best NO ask
    return m.yes_ask_size if side is Side.YES else m.yes_bid_size


@dataclass
class _Candidate:
    market: Market
    side: Side
    lo: int  # first covered outcome-point index
    hi: int  # last covered outcome-point index
    price: float
    unit_cost: float  # price + per-contract fee estimate


def _coverage(m: Market, side: Side, pts: list[float]) -> Optional[tuple[int, int]]:
    """Index range of outcome points where this leg pays, if contiguous."""
    n = len(pts)
    st, lo, hi = m.strike_type, m.floor_strike, m.cap_strike
    if st in ("greater", "greater_or_equal") and lo is not None:
        first = bisect.bisect_right(pts, lo) if st == "greater" else bisect.bisect_left(pts, lo)
        return (first, n - 1) if side is Side.YES else (0, first - 1)
    if st in ("less", "less_or_equal") and hi is not None:
        last = (bisect.bisect_left(pts, hi) if st == "less" else bisect.bisect_right(pts, hi)) - 1
        return (0, last) if side is Side.YES else (last + 1, n - 1)
    if st == "between" and lo is not None and hi is not None and side is Side.YES:
        return bisect.bisect_left(pts, lo), bisect.bisect_right(pts, hi) - 1
    return None  # NO on a range bucket covers two separate stretches


class CoverArb(Strategy):
    key = "cover_arb"
    backtestable = False  # needs strike ladders; 15-minute markets are single contracts
    persona = Persona(
        "Risk-Free Rick", "Arbitrage Analyst", "🧮",
        "Only bets when the math guarantees a profit. Mostly drinks coffee and waits.",
    )

    def __init__(self, min_edge: float = 0.01, max_contracts: float = 50, max_legs: int = 4,
                 max_cost_per_trade: float = 100.0, max_edge: float = 0.25):
        self.min_edge = min_edge  # dollars per $1 payout, after fees
        # Real arbs are small. A huge "guaranteed" edge almost always means we've
        # misread what the markets measure, so we skip it instead of betting.
        self.max_edge = max_edge
        self.max_contracts = max_contracts
        self.max_legs = max_legs
        self.max_cost_per_trade = max_cost_per_trade

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        groups: dict[tuple, list[Market]] = defaultdict(list)
        for m in snap.markets.values():
            if m.is_tradeable and m.strikes and m.strike_type:
                groups[_group_key(m)].append(m)

        intents = []
        for members in groups.values():
            if len(members) >= 2:
                intent = self._best_cover(members, snap)
                if intent:
                    intents.append(intent)
        return intents

    def _best_cover(self, members: list[Market], snap: Snapshot) -> Optional[TradeIntent]:
        pts = outcome_points(members)
        n = len(pts)
        cands: list[_Candidate] = []
        for m in members:
            fee = snap.fee_for(m)
            for side in (Side.YES, Side.NO):
                price = m.ask(side)
                if price <= 0 or _available(m, side) <= 0:
                    continue
                cov = _coverage(m, side, pts)
                if not cov or cov[0] > cov[1]:
                    continue
                cands.append(_Candidate(m, side, cov[0], cov[1], price, price + fee.taker_per_contract(price)))

        # Shortest path: dp[f] = cheapest cost to cover points [0, f)
        INF = math.inf
        dp = [INF] * (n + 1)
        back: list[Optional[tuple[int, _Candidate]]] = [None] * (n + 1)
        legs_used = [0] * (n + 1)
        dp[0] = 0.0
        cands.sort(key=lambda c: c.lo)
        for f in range(n):
            if dp[f] == INF:
                continue
            for c in cands:
                if c.lo > f:
                    break
                if c.hi < f or legs_used[f] >= self.max_legs:
                    continue
                nxt = c.hi + 1
                cost = dp[f] + c.unit_cost
                if cost < dp[nxt] - 1e-12:
                    dp[nxt], back[nxt], legs_used[nxt] = cost, (f, c), legs_used[f] + 1

        if dp[n] >= 1 - self.min_edge:
            return None

        chosen: list[_Candidate] = []
        f = n
        while f > 0:
            prev, c = back[f]
            chosen.append(c)
            f = prev
        chosen.reverse()

        legs = [(c.market, c.side) for c in chosen]
        rng = payoff_range(legs)
        if not rng or rng[0] < 1:
            return None  # safety net: never trade a "cover" that has a hole

        price_sum = sum(c.price for c in chosen)
        count = min(
            self.max_contracts,
            min(_available(c.market, c.side) for c in chosen),
            self.max_cost_per_trade / max(price_sum, 0.01),
        )
        count = math.floor(count)
        if count < 1:
            return None
        fees = sum(snap.fee_for(c.market).taker(c.price, count) for c in chosen)
        edge = (rng[0] - price_sum) - fees / count
        if edge < self.min_edge:
            return None
        if edge > self.max_edge:
            logger.warning("Suspicious cover arb skipped (edge %.2f): %s", edge,
                           [c.market.ticker for c in chosen])
            return None

        desc = " + ".join(f"{c.side.value.upper()} {c.market.ticker}@{c.price:.2f}" for c in chosen)
        return TradeIntent(
            strategy=self.key,
            legs=[Leg(c.market.ticker, c.side, c.price, count) for c in chosen],
            reason=f"cover pays >= ${rng[0]:.0f}, costs ${price_sum:.2f} + fees: {desc}",
            expected_edge=edge,
            all_or_none=True,
            guaranteed_payout=rng[0],
        )


class PartitionArb(Strategy):
    key = "bucket_arb"
    backtestable = False
    persona = Persona(
        "Sudoku Sue", "Bucket Specialist", "🧩",
        "Checks whether a 'pick one' event's prices add up. They usually do.",
    )

    def __init__(self, min_edge: float = 0.01, max_outcomes: int = 30, max_contracts: float = 50,
                 max_cost_per_trade: float = 200.0):
        self.min_edge = min_edge
        self.max_outcomes = max_outcomes
        self.max_contracts = max_contracts
        self.max_cost_per_trade = max_cost_per_trade

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        intents = []
        for event in snap.events.values():
            if not event.mutually_exclusive:
                continue
            members = [snap.markets.get(m.ticker, m) for m in event.markets]
            if not (2 <= len(members) <= self.max_outcomes):
                continue
            if not all(m.is_tradeable for m in members):
                continue
            for side in (Side.NO, Side.YES):
                intent = self._check(members, side, snap)
                if intent:
                    intents.append(intent)
        return intents

    def _check(self, members: list[Market], side: Side, snap: Snapshot) -> Optional[TradeIntent]:
        n = len(members)
        prices = [m.ask(side) for m in members]
        if any(p <= 0 for p in prices):
            return None
        if side is Side.NO:
            guaranteed = n - 1  # at most one YES, so at least n - 1 NOs pay
        else:
            rng = payoff_range([(m, Side.YES) for m in members])
            if not rng or rng[0] < 1:
                return None  # can't prove some outcome must happen
            guaranteed = rng[0]

        price_sum = sum(prices)
        approx = guaranteed - price_sum - sum(snap.fee_for(m).taker_per_contract(p) for m, p in zip(members, prices))
        if approx < self.min_edge:
            return None
        count = math.floor(min(
            self.max_contracts,
            min(_available(m, side) for m in members),
            self.max_cost_per_trade / price_sum,
        ))
        if count < 1:
            return None
        fees = sum(snap.fee_for(m).taker(p, count) for m, p in zip(members, prices))
        edge = guaranteed - price_sum - fees / count
        if edge < self.min_edge:
            return None
        return TradeIntent(
            strategy=self.key,
            legs=[Leg(m.ticker, side, p, count) for m, p in zip(members, prices)],
            reason=f"{side.value.upper()} on all {n} outcomes of {members[0].event_ticker}: "
                   f"pays >= ${guaranteed:.0f}, costs ${price_sum:.2f} + fees",
            expected_edge=edge,
            all_or_none=True,
            guaranteed_payout=guaranteed,
        )
