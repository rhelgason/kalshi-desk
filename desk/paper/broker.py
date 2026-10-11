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
from dataclasses import dataclass, field
from typing import Optional

from desk.kalshi.fees import FeeSchedule
from desk.kalshi.models import Fill, Level, Orderbook
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


@dataclass
class ExecutionResult:
    intent: TradeIntent
    filled: bool
    fills: list[LegFill] = field(default_factory=list)
    reason: str = ""

    @property
    def total_cost(self) -> float:
        return sum(f.count * f.avg_price + f.fee for f in self.fills)


class PaperBroker:
    def __init__(self, ledger: Ledger, accounts: dict[str, PaperAccount], liquidity_share: float = 0.5,
                 min_fill: float = 1.0):
        self.ledger = ledger
        self.accounts = accounts
        self.liquidity_share = liquidity_share
        self.min_fill = min_fill

    def _shrunk(self, book: Orderbook) -> Orderbook:
        """A copy of the book with only our share of each level's size."""
        if self.liquidity_share >= 1:
            return book

        def shrink(levels):
            return [Level(lv.price, math.floor(lv.size * self.liquidity_share * 100) / 100) for lv in levels]

        return Orderbook(book.ticker, shrink(book.yes_bids), shrink(book.no_bids), book.fetched_at)

    def execute(self, intent: TradeIntent, books: dict[str, Orderbook],
                fees: dict[str, FeeSchedule], ts: Optional[str] = None) -> ExecutionResult:
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
        if total > acct.cash + 1e-9:
            return ExecutionResult(intent, False, reason=f"insufficient cash (${acct.cash:.2f} < ${total:.2f})")

        result = ExecutionResult(intent, True)
        for leg, fill, fee in legs:
            acct.apply_fill(leg.ticker, leg.side, fill.count, fill.avg_price, fee)
            self.ledger.record_fill(
                intent.strategy, leg.ticker, leg.side, fill.count, fill.avg_price, fee,
                intent_id=intent.intent_id, model_prob=intent.model_prob,
                expected_edge=intent.expected_edge, reason=intent.reason, ts=ts,
            )
            result.fills.append(LegFill(leg.ticker, leg.side.value, fill.count, fill.avg_price, fee))
        return result

    def settle(self, ticker: str, yes_value: float, ts: Optional[str] = None) -> dict[str, float]:
        """Settle `ticker` in every account that holds it. Returns P&L by strategy."""
        out = {}
        for name, acct in self.accounts.items():
            if ticker in acct.positions:
                pnl = acct.settle(ticker, yes_value)
                self.ledger.record_settlement(name, ticker, yes_value, pnl, ts=ts)
                out[name] = pnl
        return out
