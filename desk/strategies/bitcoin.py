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
from desk.strategies.behavioral import BandBettor, NickelNick, SteadyStella

COIN = {"BTC": "bitcoin", "ETH": "ether", "SOL": "solana"}  # for the reason text


class BreakoutBetty(Strategy):
    key = "breakout"
    persona = Persona(
        "Wipeout", "Big-Wave Surfer", "🏄‍♀️",
        "Sees bitcoin swell and paddles like mad to catch it before Kalshi notices. Wipes out loudly.",
    )

    def __init__(self, min_move: float = 0.002, window: int = 15, min_seconds: float = 600,
                 max_seconds: float = 900, max_price: float = 0.60, max_spread: float = 0.03,
                 stake: float = 10.0, max_positions: int = 4, coins: Optional[list[str]] = None):
        self.min_move = min_move  # log return, 0.002 = 0.2%
        self.coins = coins  # e.g. ["BTC"]; None = every coin
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
            if not q or (self.coins and q.symbol not in self.coins):
                continue
            move = (q.momentum or {}).get(self.window)
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


def contracts(n: float) -> float:
    """Kalshi takes 0.01-contract steps: a $100 pool's $0.50 bet is about half a contract, not zero."""
    return math.floor(n * 100 + 1e-6) / 100


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
            count = contracts(leg.count * leg.limit_price / price)
            if count < 0.01:
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
        count = contracts(leg.count * leg.limit_price / price)
        if count < 0.01:
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
        "Wipeout's twin sister. Same waves, but she lies on an inflatable flamingo and waits for one to drift under her.",
    )
    backtestable = False

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        return self.patient(super().evaluate(snap, account), snap, account)


class SteadySadie(PatientTwin, SteadyStella):
    """
    Stella's picks (92-99c favorites, 5-9 minutes left), but a resting bid one tick over the
    best bid instead of paying the ask. Makers pay no fee on Kalshi's 15-minute coin markets,
    and a resting order has no per-order fee to round up to the cent: on a small pool's $1
    bets that rounding costs Stella more than her whole edge.
    """

    key = "heavy_maker"
    persona = Persona(
        "Steady Sadie", "Slow & Steady", "🐌",
        "Stella's twin. Same pennies, but she names her price and lets the market crawl over to her. Has never once hurried.",
    )
    backtestable = False

    def __init__(self, odds_margin: Optional[float] = None, **kw):
        # Skip a bid when the coin's own price gives her side worse odds than her bid + this margin
        # (None = never look). research/fast_coco/sadie_filters.py, Aug 25 - Oct 25 on 4 coins with an
        # exchange's spot and 4 hours of 1-minute vol: +1.23c -> +2.06c per $1 at 0, both halves, half the bets.
        # The bids she skips are the ones sellers hit because they know the coin just moved.
        self.odds_margin = odds_margin
        super().__init__(**kw)

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        bids = self.patient(super().evaluate(snap, account), snap, account)
        if self.odds_margin is None:
            return bids
        return [b for b in bids if not self.coin_says_no(snap, b)]

    def coin_says_no(self, snap: Snapshot, intent: TradeIntent) -> bool:
        leg = intent.legs[0]
        odds = side_odds(snap, snap.markets.get(leg.ticker), leg.side)
        return odds is not None and odds < leg.limit_price + self.odds_margin


def side_odds(snap: Snapshot, m: Optional[Market], side: Side) -> Optional[float]:
    """
    The chance `side` wins a 15-minute up/down market, from the coin's spot vs. the strike and its realized
    vol: the price drifts until the final minute, then Kalshi settles on that minute's average. None when
    any input is missing (callers then don't use it).
    """
    q = snap.underlying_for(m) if m else None
    secs = m.seconds_to_close(snap.now) if m else None
    if not q or not q.spot or not q.realized_vol or not m.floor_strike or secs is None \
            or not m.strike_type.startswith("greater"):
        return None
    per_sec = q.realized_vol / math.sqrt(365 * 24 * 3600)
    sd = per_sec * math.sqrt(max(secs - 60, 0) + 60 * 61 * 121 / 6 / 3600)
    up = 0.5 * (1 + math.erf(math.log(q.spot / m.floor_strike) / max(sd, 1e-12) / math.sqrt(2)))
    return up if side is Side.YES else 1 - up


class ClosingTimeCoco(PatientTwin, SteadyStella):
    """
    The last stretch of the window: 94-99c favorites with 2 to 5 minutes left, resting bids.
    research/stella_backtest (Dec 2025 - Oct 2026, BTC/ETH/SOL): picked on the first half
    (+1.33c per $1, t 8.8), held up on the second (+0.58c, t 4.7), up in all 11 months.
    Starts where Sadie stops (5 minutes left), so they rarely bid at the same moment.
    """

    key = "late_maker"
    persona = Persona(
        "Closing Time Coco", "Night Owl", "🦉",
        "Shows up as the lights go down. Bids on the sure thing in the last few minutes and never, ever pays the asking price.",
    )
    backtestable = False

    def __init__(self, min_price: float = 0.94, max_price: float = 0.99, min_seconds: float = 120,
                 max_seconds: float = 300, **kw):
        super().__init__(min_price=min_price, max_price=max_price, min_seconds=min_seconds,
                         max_seconds=max_seconds, **kw)

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        return self.patient(super().evaluate(snap, account), snap, account)


class SilverMedalSid(PatientTwin, SteadyStella):
    """
    The next tier down: 85-92c favorites with 5 to 13 minutes left, resting bids. Probation:
    +0.91c per $1 (t 2.3) in the first half of the backtest and +1.12c (t 3.6) in the second,
    up in 9 of 11 months, but he was chosen after seeing both halves, so Training only.
    """

    key = "runner_up_maker"
    persona = Persona(
        "Silver Medal Sid", "Eternal Runner-Up", "🥈",
        "Has finished second at everything since 1987 and made peace with it. Bets on the favorites nobody's quite sure of yet.",
    )
    backtestable = False

    def __init__(self, min_price: float = 0.85, max_price: float = 0.92, min_seconds: float = 300,
                 max_seconds: float = 780, **kw):
        super().__init__(min_price=min_price, max_price=max_price, min_seconds=min_seconds,
                         max_seconds=max_seconds, **kw)

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        return self.patient(super().evaluate(snap, account), snap, account)
