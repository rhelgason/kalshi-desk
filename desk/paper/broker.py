"""
Paper broker: fills TradeIntents against real orderbooks without spending money.

Realism knobs:
  - Fills walk the actual orderbook level by level, never above the limit price.
  - `liquidity_share` assumes we only get a fraction of the displayed size,
    because faster bots grab the rest. 0.5 = we get half of what's shown.
  - Taker fees are charged per order with Kalshi's formula, rounded up.
  - Multi-leg arbs (all_or_none) only fill if every leg can fill the same
    size; otherwise nothing happens.

Each strategy trades in its own universe: two strategies can both "take" the
same displayed liquidity on the same tick. That's fine for comparing them,
but it means combined results would overstate what one account could get.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from desk.kalshi.fees import FeeSchedule
from desk.kalshi.models import Fill, Level, Orderbook, Side
from desk.paper.account import PaperAccount
from desk.paper.ledger import Ledger
from desk.strategies.base import TradeIntent

logger = logging.getLogger(__name__)


@dataclass
class LegFill:
    ticker: str
    side: str
    count: float
    avg_price: float
    fee: float
    strategy: str = ""


@dataclass
class ExecutionResult:
    intent: TradeIntent
    filled: bool
    fills: list[LegFill] = field(default_factory=list)
    reason: str = ""

    @property
    def total_cost(self) -> float:
        return sum(f.count * f.avg_price + f.fee for f in self.fills)


@dataclass
class RestingOrder:
    """A paper maker order: a bid for `side` at `price`, waiting for sellers."""

    order_id: str
    strategy: str
    ticker: str
    side: str
    price: float
    count: float
    placed_at: str
    expires_at: str
    reason: str = ""
    filled: float = 0.0
    # The tape has been checked up to here: a trade already matched in one run
    # must not fill the bid again in the next (resting bids outlive a run)
    matched_until: Optional[str] = None
    # Live orders: Kalshi fill ids already applied to the books
    fill_ids: list = field(default_factory=list)
    # Share of the bid paid from the bonus pot (refunded if it expires unfilled)
    bonus: float = 0.0

    @property
    def remaining(self) -> float:
        return round(self.count - self.filled, 2)

    @property
    def checked_from(self) -> datetime:
        """Trades at or before this moment have already been matched against the bid."""
        return datetime.fromisoformat(self.matched_until or self.placed_at)


def _trade_time(t: dict) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(t.get("created_time", "")).replace("Z", "+00:00"))
    except ValueError:
        return None


class PaperBroker:
    def __init__(self, ledger: Ledger, accounts: dict[str, PaperAccount], liquidity_share: float = 0.5,
                 min_fill: float = 1.0, queue_share: float = 0.3):
        self.ledger = ledger
        self.accounts = accounts
        self.liquidity_share = liquidity_share
        self.min_fill = min_fill
        # A trade exactly at our price only partly reaches us: others were in line first
        self.queue_share = queue_share
        self.resting: list[RestingOrder] = []
        # Employees who bet out of the shared office pool (see desk.paper.pool)
        self.pool_members: set[str] = set()

    def free_cash(self, strategy: str) -> float:
        """Cash this employee can spend now: the pool's, for pool members, less bids already waiting."""
        group = self.pool_members if strategy in self.pool_members else {strategy}
        cash = sum(a.cash for k, a in self.accounts.items() if k in group)
        return cash - sum(o.price * o.remaining for o in self.resting if o.strategy in group)

    def _shrunk(self, book: Orderbook) -> Orderbook:
        """A copy of the book with only our share of each level's size."""
        if self.liquidity_share >= 1:
            return book

        def shrink(levels):
            return [Level(lv.price, math.floor(lv.size * self.liquidity_share * 100) / 100) for lv in levels]

        return Orderbook(book.ticker, shrink(book.yes_bids), shrink(book.no_bids), book.fetched_at)

    def execute(self, intent: TradeIntent, books: dict[str, Orderbook],
                fees: dict[str, FeeSchedule], ts: Optional[str] = None,
                signal_time: Optional[datetime] = None, context: Optional[dict] = None) -> ExecutionResult:
        acct = self.accounts[intent.strategy]
        shrunk = {}
        for leg in intent.legs:
            book = books.get(leg.ticker)
            if book is None:
                return ExecutionResult(intent, False, reason=f"no orderbook for {leg.ticker}")
            shrunk[leg.ticker] = self._shrunk(book)

        def plan(count_override: Optional[float] = None) -> list[tuple]:
            out = []
            for leg in intent.legs:
                want = count_override if count_override is not None else leg.count
                fill: Fill = shrunk[leg.ticker].walk(leg.side, want, leg.limit_price)
                fee_sched = fees.get(leg.ticker) or FeeSchedule()
                fee = fee_sched.taker(fill.avg_price, fill.count) if fill.count else 0.0
                out.append((leg, fill, fee))
            return out

        legs = plan()
        if intent.all_or_none:
            common = min(f.count for _, f, _ in legs)
            if common < self.min_fill:
                return ExecutionResult(intent, False, reason="not enough depth on every leg")
            common = math.floor(common)
            if any(f.count != common for _, f, _ in legs):
                legs = plan(common)
            # Re-check the arb still pays after real prices and rounded fees
            if intent.guaranteed_payout is not None:
                cost = sum(f.cost + fee for _, f, fee in legs)
                if cost >= intent.guaranteed_payout * common:
                    return ExecutionResult(intent, False, reason="edge vanished at fill prices")
        else:
            legs = [(leg, f, fee) for leg, f, fee in legs if f.count >= self.min_fill]
            if not legs:
                return ExecutionResult(intent, False, reason="no liquidity at limit price")

        total = sum(f.cost + fee for _, f, fee in legs)
        cash = self.free_cash(intent.strategy)
        if total > cash + 1e-9:
            return ExecutionResult(intent, False, reason=f"insufficient cash (${cash:.2f} < ${total:.2f})")

        result = ExecutionResult(intent, True)
        latency = None
        if signal_time is not None:
            latency = int((datetime.now(signal_time.tzinfo) - signal_time).total_seconds() * 1000)
        for leg, fill, fee in legs:
            acct.apply_fill(leg.ticker, leg.side, fill.count, fill.avg_price, fee)
            self.ledger.record_fill(
                intent.strategy, leg.ticker, leg.side, fill.count, fill.avg_price, fee,
                intent_id=intent.intent_id, model_prob=intent.model_prob,
                expected_edge=intent.expected_edge, reason=intent.reason, ts=ts,
                # Reality check: the price the employee saw, and how many contracts
                # were really on offer at or better than it (before our share haircut)
                seen_price=leg.limit_price, book_depth=books[leg.ticker].depth_at_or_better(leg.side, leg.limit_price),
                latency_ms=latency, context=context,
            )
            result.fills.append(LegFill(leg.ticker, leg.side.value, fill.count, fill.avg_price, fee))
        return result

    # ------------------------------------------------------------------
    # Resting (maker) orders
    # ------------------------------------------------------------------

    def place(self, intent: TradeIntent, now: datetime) -> list[RestingOrder]:
        """Rest each leg on the paper book, if the employee can cover it with free cash."""
        placed = []
        for leg in intent.legs:
            cost = leg.limit_price * leg.count
            if cost > self.free_cash(intent.strategy) + 1e-9:
                continue
            o = RestingOrder(
                order_id=uuid.uuid4().hex[:10], strategy=intent.strategy, ticker=leg.ticker, side=leg.side.value,
                price=leg.limit_price, count=leg.count, placed_at=now.isoformat(),
                expires_at=(now + timedelta(seconds=intent.ttl_seconds or 60)).isoformat(), reason=intent.reason,
            )
            self.resting.append(o)
            placed.append(o)
        self.sync_resting_views()
        return placed

    def match(self, trades: dict[str, list[dict]], fees: dict[str, FeeSchedule], now: datetime) -> list[LegFill]:
        """
        Fill resting bids from the real trade tape. A YES bid at p is hit when a
        taker sells YES (buys NO) at a YES price <= p. Trading through our price
        fills us fully (up to the trade size); trading exactly at it fills only
        `queue_share` of the size, since others were in line first.
        """
        fills = []
        for o in self.resting:
            if o.ticker not in trades:
                continue  # the tape couldn't be fetched: try again next run
            placed = datetime.fromisoformat(o.placed_at)
            start = o.checked_from
            until = min(now, datetime.fromisoformat(o.expires_at))
            for t in sorted(trades[o.ticker], key=lambda t: str(t.get("created_time", ""))):
                if o.remaining < 0.01:
                    break
                when = _trade_time(t)
                taker = t.get("taker_outcome_side") or t.get("taker_side")
                if not when or when <= start or when > until or taker == o.side:
                    continue
                price = float(t.get(f"{o.side}_price_dollars") or 1)
                size = float(t.get("count_fp") or 0)
                if price < o.price - 1e-9:
                    qty = size
                elif abs(price - o.price) < 1e-9:
                    qty = size * self.queue_share
                else:
                    continue
                qty = math.floor(min(qty, o.remaining) * 100) / 100
                if qty < 0.01:
                    continue
                fee = (fees.get(o.ticker) or FeeSchedule()).maker(o.price, qty)
                acct = self.accounts[o.strategy]
                acct.apply_fill(o.ticker, Side(o.side), qty, o.price, fee)
                self.ledger.record_fill(o.strategy, o.ticker, Side(o.side), qty, o.price, fee,
                                        intent_id=o.order_id, reason=f"maker fill: {o.reason}",
                                        seen_price=o.price, book_depth=size,
                                        latency_ms=int((when - placed).total_seconds() * 1000))
                o.filled = round(o.filled + qty, 2)
                fills.append(LegFill(o.ticker, o.side, qty, o.price, fee, strategy=o.strategy))
            o.matched_until = max(start, until).isoformat()
        self.resting = [o for o in self.resting if o.remaining >= 0.01]
        self.sync_resting_views()
        return fills

    def expire(self, now: datetime) -> list[RestingOrder]:
        """Take bids past their time off the book; returns them."""
        gone = [o for o in self.resting if datetime.fromisoformat(o.expires_at) <= now]
        self.resting = [o for o in self.resting if datetime.fromisoformat(o.expires_at) > now]
        self.sync_resting_views()
        return gone

    def cancel(self, strategies: set[str]) -> list[RestingOrder]:
        """Pull every waiting bid from these employees (e.g. when the daily stop kicks in)."""
        gone = [o for o in self.resting if o.strategy in strategies]
        self.resting = [o for o in self.resting if o.strategy not in strategies]
        self.sync_resting_views()
        return gone

    def sync_resting_views(self) -> None:
        for name, acct in self.accounts.items():
            acct.resting = [o for o in self.resting if o.strategy == name]

    def settle(self, ticker: str, yes_value: float, ts: Optional[str] = None) -> dict[str, float]:
        """Settle `ticker` in every account that holds it. Returns P&L by strategy."""
        out = {}
        for name, acct in self.accounts.items():
            if ticker in acct.positions:
                pnl = acct.settle(ticker, yes_value)
                self.ledger.record_settlement(name, ticker, yes_value, pnl, ts=ts)
                out[name] = pnl
        return out
