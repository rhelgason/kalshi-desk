"""
The live broker: the paper broker's bookkeeping, with real Kalshi orders.

Same accounts, ledger rows and resting-bid list as the paper broker, so the
dashboard, reviews and pool rules all work unchanged. The differences:

  taker bets     an immediate-or-cancel limit order at the employee's price.
                 Whatever Kalshi fills is booked at Kalshi's own prices and fees
                 (read back from /portfolio/fills), nothing more.
  resting bids   a post-only order that expires on Kalshi at the bid's deadline.
                 Each run asks Kalshi how much filled; each fill is booked once.
  control group  Dart Monkey Dan and Lucky the Pigeon stay on paper: they're the
                 yardstick, not part of the real pool.

Every order is checked by the guard (desk/live/guard.py) and recorded in the
`orders` table, filled or not.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Optional

from desk.kalshi.client import KalshiAPIError, KalshiClient
from desk.kalshi.fees import FeeSchedule
from desk.kalshi.models import Orderbook, Side
from desk.live.guard import Guard
from desk.paper.account import PaperAccount
from desk.paper.broker import ExecutionResult, LegFill, PaperBroker, RestingOrder
from desk.paper.ledger import Ledger
from desk.strategies.base import TradeIntent

logger = logging.getLogger(__name__)

# client_order_id is derived from our own ids, so a retried request can't place a second order
_NAMESPACE = uuid.UUID("6f1f4a52-8e3b-4c55-9d43-3c7b2e0a9a11")


def client_order_id(intent_id: str, ticker: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{intent_id}:{ticker}"))


def parse_fill(f: dict, side: Side) -> tuple[str, float, float, float]:
    """(fill id, contracts, price paid per contract for `side`, fee) from a Kalshi fill."""
    count = float(f.get("count_fp") or f.get("count") or 0)
    price = float(f.get(f"{side.value}_price_dollars") or 0)
    if f.get("outcome_side") and f["outcome_side"] != side.value:
        logger.warning("Fill %s is for %s, expected %s", f.get("fill_id"), f["outcome_side"], side.value)
    return str(f.get("fill_id") or f.get("trade_id")), count, price, float(f.get("fee_cost") or 0)


class LiveBroker(PaperBroker):
    live = True

    def __init__(self, ledger: Ledger, accounts: dict[str, PaperAccount], client: KalshiClient, guard: Guard):
        super().__init__(ledger, accounts, liquidity_share=1.0)
        self.client = client
        self.guard = guard
        self.env = client.env

    def _real(self, strategy: str) -> bool:
        return strategy in self.pool_members

    # Taker bets ------------------------------------------------------------

    async def execute(self, intent: TradeIntent, books: dict[str, Orderbook], fees: dict[str, FeeSchedule],
                      ts: Optional[str] = None, signal_time: Optional[datetime] = None,
                      context: Optional[dict] = None) -> ExecutionResult:
        if not self._real(intent.strategy):
            return super().execute(intent, books, fees, ts=ts, signal_time=signal_time, context=context)
        if len(intent.legs) != 1:
            return ExecutionResult(intent, False, reason="multi-leg bets aren't traded with real money")
        leg = intent.legs[0]
        count = math.floor(leg.count * 100 + 1e-6) / 100
        dollars = count * leg.limit_price
        why = self.guard.refuse(dollars)
        if why:
            return ExecutionResult(intent, False, reason=why)
        fee_guess = (fees.get(leg.ticker) or FeeSchedule()).taker(leg.limit_price, count)
        cash = self.free_cash(intent.strategy)
        if dollars + fee_guess > cash + 1e-9:
            return ExecutionResult(intent, False, reason=f"insufficient cash (${cash:.2f} < ${dollars + fee_guess:.2f})")

        coid = client_order_id(intent.intent_id, leg.ticker)
        try:
            resp = await self.client.create_order(leg.ticker, leg.side, count, leg.limit_price,
                                                  time_in_force="immediate_or_cancel", client_order_id=coid)
        except KalshiAPIError as e:
            self.ledger.record_order(self.env, intent.strategy, leg.ticker, leg.side.value, "taker", leg.limit_price,
                                     count, "rejected", client_order_id=coid, error=str(e))
            logger.warning("Kalshi rejected %s's order on %s: %s", intent.strategy, leg.ticker, e)
            return ExecutionResult(intent, False, reason=f"Kalshi rejected the order ({e.status})")

        order_id = resp.get("order_id")
        filled = float(resp.get("fill_count") or 0)
        got: list[tuple[str, float, float, float]] = []
        if filled > 0:
            got = await self._fills(order_id, leg.side)
            if abs(sum(c for _, c, _, _ in got) - filled) > 0.005:
                # Kalshi said it filled but the fills aren't listed yet: book what the order reported,
                # at our limit (the most it could have cost); reconciliation will flag any difference
                logger.warning("Order %s filled %g but %d fills listed; booking at the limit price",
                               order_id, filled, len(got))
                fee = float(resp.get("average_fee_paid") or 0) * filled
                got = [(f"order:{order_id}", filled, leg.limit_price, fee)]
        n = sum(c for _, c, _, _ in got)
        fee_total = sum(f for _, _, _, f in got)
        self.ledger.record_order(self.env, intent.strategy, leg.ticker, leg.side.value, "taker", leg.limit_price,
                                 count, "executed" if n else "canceled", order_id=order_id, client_order_id=coid,
                                 filled=n, fees=fee_total)
        if n < 0.005:
            return ExecutionResult(intent, False, reason="no liquidity at limit price")

        avg = sum(c * p for _, c, p, _ in got) / n
        acct = self.accounts[intent.strategy]
        acct.apply_fill(leg.ticker, leg.side, n, avg, fee_total)
        latency = int((datetime.now(signal_time.tzinfo) - signal_time).total_seconds() * 1000) if signal_time else None
        book = books.get(leg.ticker)
        self.ledger.record_fill(
            intent.strategy, leg.ticker, leg.side, n, avg, fee_total, intent_id=intent.intent_id,
            model_prob=intent.model_prob, expected_edge=intent.expected_edge, reason=intent.reason, ts=ts,
            seen_price=leg.limit_price, book_depth=book.depth_at_or_better(leg.side, leg.limit_price) if book else None,
            latency_ms=latency, context={**(context or {}), "order_id": order_id, "env": self.env},
        )
        result = ExecutionResult(intent, True)
        result.fills.append(LegFill(leg.ticker, leg.side.value, n, avg, fee_total, strategy=intent.strategy))
        return result

    def match(self, trades, fees, now):
        """Paper bids (control group) still fill from the tape; real bids are polled instead."""
        real = [o for o in self.resting if self._real(o.strategy)]
        self.resting = [o for o in self.resting if not self._real(o.strategy)]
        try:
            return super().match(trades, fees, now)
        finally:
            self.resting += real
            self.sync_resting_views()

    async def _fills(self, order_id: str, side: Side) -> list[tuple[str, float, float, float]]:
        try:
            return [parse_fill(f, side) for f in await self.client.get_fills(order_id=order_id)]
        except KalshiAPIError as e:
            logger.warning("Couldn't read fills for order %s: %s", order_id, e)
            return []

    # Resting bids ----------------------------------------------------------

    async def place(self, intent: TradeIntent, now: datetime) -> list[RestingOrder]:
        if not self._real(intent.strategy):
            return super().place(intent, now)
        placed = []
        for leg in intent.legs:
            count = math.floor(leg.count * 100 + 1e-6) / 100
            dollars = count * leg.limit_price
            if self.guard.refuse(dollars) or dollars > self.free_cash(intent.strategy) + 1e-9:
                continue
            expires = int(now.timestamp() + (intent.ttl_seconds or 60))
            coid = client_order_id(intent.intent_id, leg.ticker)
            try:
                resp = await self.client.create_order(leg.ticker, leg.side, count, leg.limit_price,
                                                      time_in_force="good_till_canceled", post_only=True,
                                                      client_order_id=coid, expiration_ts=expires)
            except KalshiAPIError as e:
                self.ledger.record_order(self.env, intent.strategy, leg.ticker, leg.side.value, "maker",
                                         leg.limit_price, count, "rejected", client_order_id=coid, error=str(e))
                logger.warning("Kalshi rejected %s's bid on %s: %s", intent.strategy, leg.ticker, e)
                continue
            o = RestingOrder(
                order_id=resp["order_id"], strategy=intent.strategy, ticker=leg.ticker, side=leg.side.value,
                price=leg.limit_price, count=count, placed_at=now.isoformat(),
                expires_at=datetime.fromtimestamp(expires, now.tzinfo).isoformat(), reason=intent.reason,
            )
            self.ledger.record_order(self.env, intent.strategy, leg.ticker, leg.side.value, "maker", leg.limit_price,
                                     count, "resting", order_id=o.order_id, client_order_id=coid)
            self.resting.append(o)
            placed.append(o)
        self.sync_resting_views()
        return placed

    async def poll(self, now: datetime) -> list[LegFill]:
        """Ask Kalshi what became of each real resting bid; book new fills once."""
        out = []
        keep = []
        for o in self.resting:
            if not self._real(o.strategy):
                keep.append(o)  # paper bids are matched against the tape by match()
                continue
            fills, status = await self._check(o)
            out += fills
            if status == "resting" and o.remaining >= 0.01:
                keep.append(o)
        self.resting = keep
        self.sync_resting_views()
        return out

    async def _check(self, o: RestingOrder) -> tuple[list[LegFill], str]:
        """Book a real bid's new fills and return them with Kalshi's status for it ("resting" if unreadable)."""
        try:
            order = await self.client.get_order(o.order_id, o.ticker)
        except KalshiAPIError as e:
            logger.warning("Couldn't check bid %s on %s: %s", o.order_id, o.ticker, e)
            return [], "resting"
        out = []
        side = Side(o.side)
        filled = float(order.get("fill_count_fp") or 0)
        if filled > o.filled + 0.005:
            for fid, n, price, fee in await self._fills(o.order_id, side):
                if fid in o.fill_ids:
                    continue
                o.fill_ids.append(fid)
                self.accounts[o.strategy].apply_fill(o.ticker, side, n, price, fee)
                self.ledger.record_fill(o.strategy, o.ticker, side, n, price, fee, intent_id=o.order_id,
                                        reason=f"maker fill: {o.reason}", seen_price=o.price,
                                        context={"order_id": o.order_id, "env": self.env})
                o.filled = round(o.filled + n, 2)
                out.append(LegFill(o.ticker, o.side, n, price, fee, strategy=o.strategy))
        status = order.get("status") or "resting"
        fees = float(order.get("maker_fees_dollars") or 0) + float(order.get("taker_fees_dollars") or 0)
        missing = round(filled - o.filled, 2)
        if status != "resting" and missing >= 0.01:
            # Kalshi says it filled but hasn't listed the fills yet, and a finished order isn't looked at again:
            # book what the order reported at our price (2026-11-08: a DOGE fill never reached our books, $0.84 off)
            logger.warning("Bid %s filled %g but only %g listed; booking the rest at the bid price",
                           o.order_id, filled, o.filled)
            fee = fees * missing / filled if filled else 0.0
            self.accounts[o.strategy].apply_fill(o.ticker, side, missing, o.price, fee)
            self.ledger.record_fill(o.strategy, o.ticker, side, missing, o.price, fee, intent_id=o.order_id,
                                    reason=f"maker fill: {o.reason}", seen_price=o.price,
                                    context={"order_id": o.order_id, "env": self.env, "unlisted": True})
            o.fill_ids.append(f"order:{o.order_id}")
            o.filled = round(o.filled + missing, 2)
            out.append(LegFill(o.ticker, o.side, missing, o.price, fee, strategy=o.strategy))
        if status != "resting" or o.remaining < 0.01:
            self.ledger.update_order(o.order_id, o.filled, fees, status)
        return out, status

    async def repair(self, hours: float = 12.0) -> list[LegFill]:
        """
        Book the fills Kalshi lists for our bids that our books are missing (2026-11-09). Kalshi's fills list is
        the truth; every bid we place is in the orders table with its employee, and our fills carry its order id,
        so this matches order by order and never books one twice. Bids still waiting are poll()'s job.
        """
        try:
            fills = await self.client.get_fills(min_ts=int(time.time() - hours * 3600))  # every shard
        except KalshiAPIError as e:
            logger.warning("Couldn't read Kalshi's fills to repair our books: %s", e)
            return []
        waiting = {o.order_id for o in self.resting}
        by: dict[str, list[dict]] = defaultdict(list)
        for f in fills:
            if f.get("order_id") and f["order_id"] not in waiting:
                by[f["order_id"]].append(f)
        if not by:
            return []
        marks = ",".join("?" * len(by))
        ids = tuple(by)
        orders = {r["order_id"]: r for r in self.ledger._rows(
            f"SELECT order_id, strategy, ticker, side, kind, fees FROM orders WHERE order_id IN ({marks})", ids)}
        booked = {r["intent_id"]: float(r["n"]) for r in self.ledger._rows(
            f"SELECT intent_id, sum(count) AS n FROM fills WHERE intent_id IN ({marks}) GROUP BY intent_id", ids)}
        out = []
        for oid, fs in by.items():
            o = orders.get(oid)
            if o is None or o["kind"] != "maker" or o["strategy"] not in self.accounts:
                if o is None:
                    logger.warning("Kalshi lists a fill on %s for order %s, which isn't ours", fs[0].get("ticker"), oid)
                continue  # a taker's fills are booked when it's placed, from this same list
            side = Side(o["side"])
            got = [parse_fill(f, side) for f in fs]
            theirs = sum(n for _, n, _, _ in got)
            missing = round(theirs - booked.get(oid, 0.0), 2)
            if missing < 0.01:
                continue
            price = sum(n * p for _, n, p, _ in got) / theirs
            fee = sum(fe for *_, fe in got) * missing / theirs
            logger.warning("Kalshi filled %g of %s's bid on %s that our books missed: booking it", missing,
                           o["strategy"], o["ticker"])
            self.accounts[o["strategy"]].apply_fill(o["ticker"], side, missing, price, fee)
            self.ledger.record_fill(o["strategy"], o["ticker"], side, missing, price, fee, intent_id=oid,
                                    reason="maker fill (found in Kalshi's fills list later)", seen_price=price,
                                    context={"order_id": oid, "env": self.env, "repaired": True})
            self.ledger.update_order(oid, round(booked.get(oid, 0.0) + missing, 2), float(o["fees"] or 0) + fee,
                                     "executed")
            out.append(LegFill(o["ticker"], side.value, missing, price, fee, strategy=o["strategy"]))
        return out

    async def _cancel_real(self, o: RestingOrder) -> None:
        try:
            await self.client.cancel_order(o.order_id, o.ticker)
        except KalshiAPIError as e:
            if e.status != 404:  # already gone (filled or expired) is fine
                logger.warning("Couldn't cancel bid %s on %s: %s", o.order_id, o.ticker, e)
        # It may have filled since the last look (2026-10-27: a bid filled the second it went up, the kill
        # switch pulled it, and the fill never reached our books)
        await self._check(o)
        self.ledger.update_order(o.order_id, o.filled, 0.0, "canceled")

    async def expire(self, now: datetime) -> list[RestingOrder]:
        gone = [o for o in self.resting if datetime.fromisoformat(o.expires_at) <= now]
        for o in gone:
            if self._real(o.strategy):
                await self._cancel_real(o)  # Kalshi expires it too; this just makes sure
        self.resting = [o for o in self.resting if o not in gone]
        self.sync_resting_views()
        return gone

    async def cancel(self, strategies: set[str]) -> list[RestingOrder]:
        gone = [o for o in self.resting if o.strategy in strategies]
        for o in gone:
            if self._real(o.strategy):
                await self._cancel_real(o)
        self.resting = [o for o in self.resting if o not in gone]
        self.sync_resting_views()
        return gone

    async def cancel_everything(self) -> list[RestingOrder]:
        """The kill switch: every real bid off Kalshi (and the account-wide cancel, to be sure)."""
        gone = await self.cancel({o.strategy for o in self.resting if self._real(o.strategy)})
        try:
            await self.client.cancel_all_orders()
        except KalshiAPIError as e:
            logger.warning("Kalshi's cancel-all failed: %s", e)
        return gone
