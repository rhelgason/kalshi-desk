"""
Strategies built on how people bet, not on a pricing model.

LongshotFade ("longshot_fade")
    The "favorite-longshot bias" is one of the most-studied patterns in betting:
    people overpay for long shots (lottery-ticket appeal). Research on Kalshi
    data has found that very cheap contracts win less often than their price
    implies (Burgi, Deng & Whelan, "Makers and Takers: The Economics of the
    Kalshi Prediction Market", 2025). So we take the other side: buy NO on
    contracts whose YES trades at a few cents.
    Shape of returns: many small wins, occasional painful loss. Needs lots of
    small, spread-out bets to work, and takes days to settle.

LongshotLenny ("longshot_buy")
    The mirror image: buys the long shots. Bill and Lenny can't both win; the
    scoreboard settles the favorite-longshot argument with our own data.

NickelNick ("nickel_picker")
    Buys 92-97c near-certainties that settle within hours.

WhaleWatcherWalt ("whale_follow")
    Follows unusually large trades on the tape.

DartMonkey ("dart_monkey")
    Picks random markets and random sides. It's the control group: any
    strategy that can't beat the monkey (after fees) isn't actually skilled.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from typing import Optional

from desk.kalshi.models import Market, Side
from desk.strategies.base import AccountView, Leg, Persona, Snapshot, Strategy, TradeIntent


class BandBettor(Strategy):
    """
    Shared machinery for "find markets in a price band and bet a fixed stake":
    filters for liquidity and time to close, spreads bets across events (outcomes
    inside one event tend to move together), and prefers the busiest markets.
    Subclasses implement pick(): which side to buy, if any.
    """

    def __init__(
        self,
        max_spread: float = 0.03,
        min_volume_24h: float = 200,
        max_hours: float = 7 * 24,
        min_seconds: float = 600,
        stake: float = 5.0,
        max_positions: int = 40,
        max_per_event: int = 1,
    ):
        self.max_spread = max_spread
        self.min_volume_24h = min_volume_24h
        self.max_hours = max_hours
        self.min_seconds = min_seconds
        self.stake = stake
        self.max_positions = max_positions
        self.max_per_event = max_per_event

    def pick(self, m: Market) -> Optional[Side]:
        raise NotImplementedError

    def describe(self, m: Market, side: Side, price: float) -> str:
        return f"{side.value.upper()} @ {price:.2f} on '{m.title[:60]}'"

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        held = account.open_tickers
        room = self.max_positions - len(held)
        if room <= 0:
            return []
        horizon = snap.now + timedelta(hours=self.max_hours)
        picks = []
        for m in snap.markets.values():
            if not m.is_tradeable or m.ticker in held or not m.close_time:
                continue
            if m.close_time > horizon or (m.seconds_to_close(snap.now) or 0) < self.min_seconds:
                continue
            if m.yes_ask - m.yes_bid > self.max_spread or m.volume_24h < self.min_volume_24h:
                continue
            side = self.pick(m)
            if side and m.ask(side) > 0:
                picks.append((m, side, m.ask(side)))

        picks.sort(key=lambda p: p[0].volume_24h, reverse=True)
        per_event: dict[str, int] = {}
        for t in held:
            ev = snap.markets[t].event_ticker if t in snap.markets else t.rsplit("-", 1)[0]
            per_event[ev] = per_event.get(ev, 0) + 1

        intents = []
        cash = account.cash
        for m, side, price in picks:
            if len(intents) >= room:
                break
            if per_event.get(m.event_ticker, 0) >= self.max_per_event:
                continue
            count = math.floor(min(self.stake, cash) / price)
            if count < 1:
                break
            per_event[m.event_ticker] = per_event.get(m.event_ticker, 0) + 1
            cash -= count * price
            intents.append(TradeIntent(
                strategy=self.key,
                legs=[Leg(m.ticker, side, price, count)],
                reason=self.describe(m, side, price),
            ))
        return intents


class LongshotFade(BandBettor):
    key = "longshot_fade"
    persona = Persona(
        "Buzzkill Bill", "Party Pooper", "🧊",
        "Bets against every long shot. Smug most days, devastated on others.",
    )

    def __init__(self, min_yes: float = 0.03, max_yes: float = 0.12, max_days: float = 7, **kw):
        kw.setdefault("max_hours", max_days * 24)
        super().__init__(**kw)
        self.min_yes = min_yes
        self.max_yes = max_yes

    def is_longshot(self, m: Market) -> bool:
        return self.min_yes <= m.yes_bid and m.yes_ask <= self.max_yes

    def pick(self, m: Market) -> Optional[Side]:
        return Side.NO if self.is_longshot(m) else None

    def describe(self, m, side, price):
        return f"fade long shot: YES at {m.yes_bid:.2f}-{m.yes_ask:.2f} on '{m.title[:60]}'"


class LongshotLenny(LongshotFade):
    """Bill's mirror image: buys the long shots Bill bets against. One of them is wrong."""

    key = "longshot_buy"
    persona = Persona(
        "Long Shot Lenny", "Dreamer", "🎰",
        "Buys every lottery ticket under 12 cents. 'It only has to hit once.'",
    )

    def __init__(self, stake: float = 2.0, **kw):
        super().__init__(stake=stake, **kw)

    def pick(self, m: Market) -> Optional[Side]:
        return Side.YES if self.is_longshot(m) else None

    def describe(self, m, side, price):
        return f"long shot! YES @ {price:.2f} on '{m.title[:60]}'"


class NickelNick(BandBettor):
    """
    Buys near-sure things (92-97c) that settle within hours, collecting a few
    cents each time. Famously described as "picking up nickels in front of a
    steamroller": steady, until one surprise wipes out twenty wins.
    """

    key = "nickel_picker"
    persona = Persona(
        "Nickel Nick", "Penny Collector", "🪙",
        "Picks up nickels in front of a steamroller.",
    )

    def __init__(self, min_price: float = 0.92, max_price: float = 0.97, max_hours: float = 12,
                 stake: float = 10.0, max_spread: float = 0.02, **kw):
        super().__init__(max_hours=max_hours, stake=stake, max_spread=max_spread, **kw)
        self.min_price = min_price
        self.max_price = max_price

    def pick(self, m: Market) -> Optional[Side]:
        for side in (Side.YES, Side.NO):
            if self.min_price <= m.ask(side) <= self.max_price:
                return side
        return None

    def describe(self, m, side, price):
        return f"near-sure thing: {side.value.upper()} @ {price:.2f} on '{m.title[:60]}'"


class FrontRunnerFran(BandBettor):
    """
    Buys the favorite in sports match-winner markets ("Will X win?"), using the
    same lesson the 15-minute crypto markets taught: favorites are slightly
    underpriced, but not in the final minutes. Starts as an Intern; the
    performance reviews decide whether she earns bigger bets.
    """

    key = "favorite_sports"
    persona = Persona(
        "Front-Runner Fran", "Sports Bettor", "🏈",
        "Always bets on the favorite. Never the underdog. Never in the last hour.",
    )

    def __init__(self, min_price: float = 0.75, max_price: float = 0.92, min_seconds: float = 3600,
                 max_hours: float = 72, stake: float = 10.0, min_volume_24h: float = 500, **kw):
        super().__init__(min_seconds=min_seconds, max_hours=max_hours, stake=stake,
                         min_volume_24h=min_volume_24h, **kw)
        self.min_price = min_price
        self.max_price = max_price

    @staticmethod
    def is_sports_game(m: Market) -> bool:
        series = (m.series_ticker or m.event_ticker.split("-", 1)[0]).upper()
        return "GAME" in series and not series.startswith(("KXBTC", "KXETH", "KXSOL"))

    def pick(self, m: Market) -> Optional[Side]:
        if not self.is_sports_game(m):
            return None
        for side in (Side.YES, Side.NO):
            if self.min_price <= m.ask(side) <= self.max_price:
                return side
        return None

    def describe(self, m, side, price):
        return f"backing the favorite: {side.value.upper()} @ {price:.2f} on '{m.title[:60]}'"


class SpreadSam(Strategy):
    """
    A market maker. Instead of paying the asking price, Sam posts bids one cent
    better than the best YES bid and the best NO bid, then waits. If both fill,
    one YES plus one NO pays exactly $1, so he keeps the gap (the spread) minus
    his 2 cents of improvement. If only one side fills and the price keeps
    moving, he's holding a losing bet; that's the risk market makers take.
    Maker orders also pay much lower fees than taking.
    """

    key = "market_maker"
    persona = Persona(
        "Spread Sam", "Market Maker", "🤝",
        "Never pays the asking price. Waits for someone else to be in a hurry.",
    )
    backtestable = False  # fills depend on other traders; the desk feeds him the live trade tape

    def __init__(self, min_spread: float = 0.03, min_mid: float = 0.15, max_mid: float = 0.85,
                 min_volume_24h: float = 5000, min_seconds: float = 1800, stake: float = 10.0,
                 max_inventory: float = 30, max_markets: int = 6, ttl_seconds: float = 150, improve: float = 0.01):
        self.min_spread = min_spread
        self.min_mid = min_mid
        self.max_mid = max_mid
        self.min_volume_24h = min_volume_24h
        self.min_seconds = min_seconds
        self.stake = stake
        self.max_inventory = max_inventory
        self.max_markets = max_markets
        self.ttl_seconds = ttl_seconds
        self.improve = improve

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        resting = {o.ticker for o in getattr(account, "resting", [])}
        candidates = []
        for m in snap.markets.values():
            if not m.is_tradeable or m.ticker in resting or m.mid is None:
                continue
            if (m.seconds_to_close(snap.now) or 0) < self.min_seconds or m.volume_24h < self.min_volume_24h:
                continue
            spread = m.yes_ask - m.yes_bid
            if spread < self.min_spread or not (self.min_mid <= m.mid <= self.max_mid):
                continue
            candidates.append(m)
        candidates.sort(key=lambda m: m.volume_24h, reverse=True)

        intents = []
        for m in candidates[: self.max_markets]:
            yes_px = round(m.yes_bid + self.improve, 2)
            no_px = round(m.no_bid + self.improve, 2)
            if yes_px >= m.yes_ask or no_px >= m.no_ask:
                continue  # would cross the spread and become a taker
            pos_yes, pos_no = account.position(m.ticker)
            net = pos_yes - pos_no
            legs = []
            if net < self.max_inventory:
                legs.append(Leg(m.ticker, Side.YES, yes_px, math.floor(self.stake / yes_px)))
            if -net < self.max_inventory:
                legs.append(Leg(m.ticker, Side.NO, no_px, math.floor(self.stake / no_px)))
            legs = [leg for leg in legs if leg.count >= 1]
            if legs:
                intents.append(TradeIntent(
                    strategy=self.key, legs=legs, post_only=True, ttl_seconds=self.ttl_seconds,
                    reason=f"quoting {yes_px:.2f}/{no_px:.2f} (spread {m.yes_ask - m.yes_bid:.2f}) on '{m.title[:50]}'",
                    expected_edge=(1 - yes_px - no_px) / 2,
                ))
        return intents


class WhaleWatcherWalt(Strategy):
    """
    Watches the trade tape for big market orders ("whales") and follows them,
    on the theory that someone betting hundreds of dollars at once might know
    something. Only follows if the price hasn't already run away.
    """

    key = "whale_follow"
    persona = Persona(
        "Whale Watcher Walt", "Tape Reader", "🐋",
        "Sees a big bet go through and yells 'follow that whale!'",
    )
    wants_trades = True
    backtestable = False

    def __init__(self, min_notional: float = 250.0, lookback_seconds: float = 120, max_chase: float = 0.02,
                 min_price: float = 0.10, max_price: float = 0.90, stake: float = 10.0, max_positions: int = 30):
        self.min_notional = min_notional
        self.lookback_seconds = lookback_seconds
        self.max_chase = max_chase
        self.min_price = min_price
        self.max_price = max_price
        self.stake = stake
        self.max_positions = max_positions
        self._followed: set[str] = set()

    def get_state(self) -> Optional[dict]:
        # Trades older than the lookback are ignored anyway; keep the list short
        return {"followed": list(self._followed)[-2000:]}

    def set_state(self, state: dict) -> None:
        self._followed = set(state.get("followed", []))

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        held = account.open_tickers
        intents = []
        for ticker, trades in snap.trades.items():
            m = snap.markets.get(ticker)
            if not m or not m.is_tradeable or ticker in held:
                continue
            if len(held) + len(intents) >= self.max_positions:
                break
            for t in trades:
                tid = t.get("trade_id", "")
                if tid in self._followed:
                    continue
                created = _parse_ts(t.get("created_time"))
                if not created or (snap.now - created).total_seconds() > self.lookback_seconds:
                    continue
                side_raw = t.get("taker_outcome_side") or t.get("taker_side")
                if side_raw not in ("yes", "no"):
                    continue
                side = Side(side_raw)
                paid = float(t.get(f"{side.value}_price_dollars") or 0)
                notional = float(t.get("count_fp") or 0) * paid
                if notional < self.min_notional:
                    continue
                self._followed.add(tid)
                price = m.ask(side)
                if not (self.min_price <= price <= self.max_price) or price > paid + self.max_chase:
                    continue
                count = math.floor(min(self.stake, account.cash) / price)
                if count < 1:
                    continue
                intents.append(TradeIntent(
                    strategy=self.key,
                    legs=[Leg(ticker, side, price, count)],
                    reason=f"whale bought ${notional:,.0f} of {side.value.upper()} @ {paid:.2f}; following @ {price:.2f}",
                ))
                break
        return intents


def _parse_ts(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class DartMonkey(Strategy):
    key = "dart_monkey"
    persona = Persona(
        "Dart Monkey Dan", "Intern", "🐒",
        "Throws darts at the board. If you can't beat Dan, you're not skilled.",
    )

    def __init__(self, bets_per_tick: float = 0.2, stake: float = 3.0, max_positions: int = 30,
                 seed: int | None = None, min_price: float = 0.05, max_price: float = 0.95,
                 max_hours: float | None = None):
        self.max_hours = max_hours
        self.bets_per_tick = bets_per_tick
        self.stake = stake
        self.max_positions = max_positions
        self.min_price = min_price
        self.max_price = max_price
        self.rng = random.Random(seed)

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        if len(account.open_tickers) >= self.max_positions or self.rng.random() > self.bets_per_tick:
            return []
        options = [
            (m, side)
            for m in snap.markets.values()
            if m.is_tradeable and m.ticker not in account.open_tickers
            and (self.max_hours is None or (m.seconds_to_close(snap.now) or 0) <= self.max_hours * 3600)
            for side in (Side.YES, Side.NO)
            if self.min_price <= m.ask(side) <= self.max_price
        ]
        if not options:
            return []
        m, side = self.rng.choice(options)
        price = m.ask(side)
        count = math.floor(min(self.stake, account.cash) / price)
        if count < 1:
            return []
        return [TradeIntent(
            strategy=self.key,
            legs=[Leg(m.ticker, side, price, count)],
            reason=f"dart landed on {side.value.upper()} {m.ticker} @ {price:.2f}",
            model_prob=price,  # the monkey "believes" the market price
        )]
