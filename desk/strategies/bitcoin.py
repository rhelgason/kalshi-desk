"""
Employees built for the 15-minute bitcoin up/down markets (KXBTC15M), hired
for Season 3 after studying ~4 months of those markets (Jun-Oct 2026):

  * Kalshi's prices are close to fair: blindly buying any band of prices
    loses to fees, and a textbook pricing model (spot vs. strike with
    realized vol) loses at every threshold we tried.
  * Two small, repeatable leans showed up, worth testing with real money
    rules (fees, a 1-minute delay, limited size):

BreakoutBetty ("breakout")
    When bitcoin has moved sharply over the last 15 minutes and the window
    has just opened, Kalshi sometimes still prices the "keeps going" side
    under 60c. She buys it. Historically about +1 to +3c per $1 bet.

EarlyBirdEdie ("early_favorite")
    Early in a window (10-13 minutes left), clear favorites priced 75-85c
    have won a bit more often than their price says. She buys them before
    Nickel Nick's 85-95c zone. Historically about +2c per $1, noisy.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Optional

from desk.kalshi.models import Market, Side
from desk.strategies.base import AccountView, Leg, Persona, Snapshot, Strategy, TradeIntent
from desk.strategies.behavioral import BandBettor, NickelNick

COIN = {"BTC": "bitcoin", "ETH": "ether", "SOL": "solana"}  # for the reason text


class BreakoutBetty(Strategy):
    key = "breakout"
    persona = Persona(
        "Breakout Betty", "Big-Wave Surfer", "🏄‍♀️",
        "Sees bitcoin swell and paddles like mad to catch it before Kalshi notices. Wipes out loudly.",
    )

    def __init__(self, min_move: float = 0.002, window: int = 15, min_seconds: float = 600,
                 max_seconds: float = 900, max_price: float = 0.60, max_spread: float = 0.03,
                 stake: float = 10.0, max_positions: int = 4):
        self.min_move = min_move  # log return, 0.002 = 0.2%
        self.window = window
        self.min_seconds = min_seconds
        self.max_seconds = max_seconds
        self.max_price = max_price
        self.max_spread = max_spread
        self.stake = stake
        self.max_positions = max_positions

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        held = account.open_tickers
        if len(held) >= self.max_positions:
            return []
        out = []
        cash = account.cash
        for m in snap.markets.values():
            if not m.is_tradeable or m.ticker in held or not m.close_time:
                continue
            secs = m.seconds_to_close(snap.now) or 0
            if not (self.min_seconds <= secs <= self.max_seconds) or m.yes_ask - m.yes_bid > self.max_spread:
                continue
            q = snap.underlying_for(m)
            move = (q.momentum or {}).get(self.window) if q else None
            if move is None or abs(move) < self.min_move:
                continue
            side = Side.YES if move > 0 else Side.NO
            price = m.ask(side)
            if not (0 < price <= self.max_price):
                continue
            count = math.floor(min(self.stake, cash) / price)
            if count < 1:
                break
            cash -= count * price
            out.append(TradeIntent(
                strategy=self.key, legs=[Leg(m.ticker, side, price, count)],
                reason=f"{COIN.get(q.symbol, q.symbol)} {'up' if move > 0 else 'down'} {abs(move) * 100:.2f}% in {self.window} min; "
                       f"{side.value.upper()} still only {price:.2f} with {secs / 60:.0f} min left",
            ))
        return out


class EarlyBirdEdie(BandBettor):
    key = "early_favorite"
    persona = Persona(
        "Early Bird Edie", "The Rooster", "🐓",
        "In at 5am, three coffees deep. Grabs the favorite the second a window opens, at full volume.",
    )

    def __init__(self, min_price: float = 0.75, max_price: float = 0.85, min_seconds: float = 600,
                 max_seconds: float = 780, stake: float = 10.0, max_spread: float = 0.03, **kw):
        super().__init__(min_seconds=min_seconds, stake=stake, max_spread=max_spread, max_hours=1, **kw)
        self.min_price = min_price
        self.max_price = max_price
        self.max_seconds = max_seconds

    def pick(self, m: Market) -> Optional[Side]:
        for side in (Side.YES, Side.NO):
            if self.min_price <= m.ask(side) <= self.max_price:
                return side
        return None

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        # Only the first few minutes of a window count as "early"
        early = {t: m for t, m in snap.markets.items() if (m.seconds_to_close(snap.now) or 0) <= self.max_seconds}
        return super().evaluate(Snapshot(now=snap.now, markets=early, events=snap.events,
                                         underlyings=snap.underlyings, fees=snap.fees, trades=snap.trades), account)

    def describe(self, m, side, price):
        return f"early favorite: {side.value.upper()} @ {price:.2f} on '{m.title[:60]}'"


def patient_price(m: Market, side: Side, ticks: int = 1) -> Optional[float]:
    """A bid `ticks` steps above the best bid for `side`, but never at or above the ask."""
    bid, ask = m.bid(side), m.ask(side)
    if not (0 < bid < ask < 1):
        return None

    def step(p: float) -> float:  # ladders are set on the YES price
        return m.tick_at(p if side is Side.YES else 1 - p)

    price = min(bid + ticks * step(bid), ask - step(ask - 1e-6))
    return round(max(price, bid), 4)


class PatientTwin:
    """Turns an employee's buy-at-the-ask bets into resting bids (maker orders)."""

    improve_ticks: int = 1
    wait_seconds: float = 110  # gone before the next look, 2 minutes later

    def patient(self, intents: list[TradeIntent], snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        waiting = {o.ticker for o in getattr(account, "resting", [])}
        out = []
        for intent in intents:
            leg = intent.legs[0]
            m = snap.markets.get(leg.ticker)
            if not m or leg.ticker in waiting:
                continue
            price = patient_price(m, leg.side, self.improve_ticks)
            if not price:
                continue
            count = math.floor(leg.count * leg.limit_price / price)
            if count < 1:
                continue
            out.append(replace(
                intent, legs=[Leg(leg.ticker, leg.side, price, count)], post_only=True,
                ttl_seconds=self.wait_seconds,
                reason=f"bid {price:.3f} instead of paying {leg.limit_price:.3f}: {intent.reason}",
            ))
        return out

    def reprice(self, intent: TradeIntent, seen: Market, live: Market) -> Optional[TradeIntent]:
        """
        Re-price a bid against the live order book just before posting. The market
        list (`seen`) can lag the book by several cents, and a bid priced off it can
        sit above the real ask: Kalshi would reject that post-only order, and the
        paper tape would "fill" it at a price nobody had to pay. Never bid more than
        a tick under what the sibling would have paid (the ask they saw).
        """
        leg = intent.legs[0]
        price = patient_price(live, leg.side, self.improve_ticks)
        seen_ask = seen.ask(leg.side)
        if not price or not seen_ask:
            return None
        price = min(price, round(seen_ask - seen.tick_at(seen_ask if leg.side is Side.YES else 1 - seen_ask), 4))
        if price <= 0 or price >= live.ask(leg.side):
            return None
        count = math.floor(leg.count * leg.limit_price / price)
        if count < 1:
            return None
        return replace(intent, legs=[Leg(leg.ticker, leg.side, price, count)])


class NickelNora(PatientTwin, NickelNick):
    key = "nickel_maker"
    persona = Persona(
        "Nickel Nora", "Coupon Queen", "🏷️",
        "Nick's twin sister. Has never paid full price in her life: names her price and waits for the market to blink.",
    )
    backtestable = False  # fills depend on other traders

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        return self.patient(super().evaluate(snap, account), snap, account)


class EarlyBirdEllie(PatientTwin, EarlyBirdEdie):
    key = "early_maker"
    persona = Persona(
        "Early Bird Ellie", "Tea & Knitting", "🧶",
        "Edie's calm twin. Spots the same favorites, posts her price, and knits until someone sells.",
    )
    backtestable = False

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        return self.patient(super().evaluate(snap, account), snap, account)


class BreakoutBonnie(PatientTwin, BreakoutBetty):
    key = "breakout_maker"
    persona = Persona(
        "Breakout Bonnie", "Pool Floater", "🛟",
        "Betty's twin. Same waves, but she lies on an inflatable flamingo and waits for one to drift under her.",
    )
    backtestable = False

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        return self.patient(super().evaluate(snap, account), snap, account)
