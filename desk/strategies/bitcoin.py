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
from typing import Optional

from desk.kalshi.models import Market, Side
from desk.strategies.base import AccountView, Leg, Persona, Snapshot, Strategy, TradeIntent
from desk.strategies.behavioral import BandBettor


class BreakoutBetty(Strategy):
    key = "breakout"
    persona = Persona(
        "Breakout Betty", "Trend Rider", "🏄‍♀️",
        "Sees bitcoin running and jumps on before Kalshi catches up.",
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
                reason=f"bitcoin {'up' if move > 0 else 'down'} {abs(move) * 100:.2f}% in {self.window} min; "
                       f"{side.value.upper()} still only {price:.2f} with {secs / 60:.0f} min left",
            ))
        return out


class EarlyBirdEdie(BandBettor):
    key = "early_favorite"
    persona = Persona(
        "Early Bird Edie", "Morning Person", "🐦",
        "Picks the favorite the moment a window opens, before the price catches up.",
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
