"""
Employees for markets other than the 15-minute coins (Training only, hired 2026-10-28).

research/other_markets replayed Sadie's idea (a resting bid on a heavy favorite) on Kalshi's trade tape
in 22 other series over 60 days, on a clock that can't see the result. Two places held up:

WeatherWendy ("weather_maker")
    The daily-high markets in 6 cities: 92-99.5c favorites, bids from midnight to 11 am city time on the
    day itself. +3.8c per $1 at 92-97c (t 5.0, 56 of 60 days up, both halves) and +1.5c at 97-99.5c,
    about 3-5 bets a day. Weather charges makers no fee. Free forecasts lost badly against these
    prices (research/other_markets/wx.py), so she doesn't try to out-forecast anyone.

FinalWhistleFiona ("sports_closer")
    Football, baseball and basketball winner markets once a game is all but decided: 97-99.5c, from
    3 hours before Kalshi's scheduled end to 2 hours after it. +1.2 to +1.7c per $1 and no losses in
    ~350 replayed bets, but only a few bets a day, and sports charge makers a small fee.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from desk.kalshi.models import Market, Side
from desk.strategies.base import AccountView, Leg, Persona, Snapshot, Strategy, TradeIntent
from desk.strategies.bitcoin import PatientTwin, contracts, patient_price

MONTHS = {m: i for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}


class FavoriteBidder(PatientTwin, Strategy):
    """Resting bids on whichever side of a market is a favorite in [min_price, max_price), in its series and hours."""

    scope = "other"  # sees the desk's other_series markets, not the coins
    series: tuple[str, ...] = ()
    one_per_event: bool = False  # game markets come in mirror pairs ("A wins" / "B wins")
    backtestable = False

    def __init__(self, min_price: float, max_price: float, stake: float = 10.0):
        self.min_price = min_price
        self.max_price = max_price
        self.stake = stake

    def in_hours(self, m: Market, now: datetime) -> bool:
        raise NotImplementedError

    def describe(self, m: Market, side: Side, price: float) -> str:
        return f"{side.value.upper()} favorite @ {price:.2f} on '{m.title[:60]}'"

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        busy = set(account.open_tickers) | {o.ticker for o in getattr(account, "resting", [])}
        picks = []
        for m in snap.markets.values():
            if m.series_ticker not in self.series or not m.is_tradeable or m.ticker in busy:
                continue
            if not self.in_hours(m, snap.now):
                continue
            for side in (Side.YES, Side.NO):
                price = patient_price(m, side, self.improve_ticks)
                if price and self.min_price <= price < self.max_price:
                    picks.append((m, side, price))
                    break
        picks.sort(key=lambda p: p[0].volume_24h, reverse=True)
        events = {t.rsplit("-", 1)[0] for t in busy} if self.one_per_event else set()
        out = []
        for m, side, price in picks:
            if self.one_per_event and m.event_ticker in events:
                continue
            events.add(m.event_ticker)
            out.append(TradeIntent(
                strategy=self.key, legs=[Leg(m.ticker, side, price, contracts(self.stake / price))],
                post_only=True, ttl_seconds=self.wait_seconds, reason=self.describe(m, side, price),
            ))
        return out

    def reprice(self, intent: TradeIntent, seen: Market, live: Market) -> Optional[TradeIntent]:
        bid = super().reprice(intent, seen, live)
        return bid if bid and bid.legs[0].limit_price >= self.min_price else None


class WeatherWendy(FavoriteBidder):
    key = "weather_maker"
    persona = Persona(
        "Weather Wendell", "Chief Meteorologist", "🐸",
        "A frog in a sou'wester who lives in a jar on the windowsill. Never forecasts a thing: he just bets the "
        "favorite is a little too cheap before the flies wake up.",
    )
    series = ("KXHIGHNY", "KXHIGHLAX", "KXHIGHCHI", "KXHIGHMIA", "KXHIGHAUS", "KXHIGHDEN")
    ZONES = {"KXHIGHNY": "America/New_York", "KXHIGHLAX": "America/Los_Angeles", "KXHIGHCHI": "America/Chicago",
             "KXHIGHMIA": "America/New_York", "KXHIGHAUS": "America/Chicago", "KXHIGHDEN": "America/Denver"}

    def __init__(self, min_price: float = 0.92, max_price: float = 0.995, start_hour: int = 0, end_hour: int = 11,
                 **kw):
        super().__init__(min_price=min_price, max_price=max_price, **kw)
        self.start_hour = start_hour
        self.end_hour = end_hour

    def in_hours(self, m: Market, now: datetime) -> bool:
        """The morning (city time) of the day the market is about: KXHIGHNY-26OCT28 is Oct 28 in New York."""
        zone = self.ZONES.get(m.series_ticker)
        try:
            code = m.event_ticker.split("-")[1]
            day = (2000 + int(code[:2]), MONTHS[code[2:5]], int(code[5:7]))
        except (IndexError, KeyError, ValueError):
            return False
        local = now.astimezone(ZoneInfo(zone)) if zone else None
        return bool(local) and (local.year, local.month, local.day) == day \
            and self.start_hour <= local.hour < self.end_hour

    def describe(self, m, side, price):
        return f"morning favorite: {side.value.upper()} @ {price:.2f} on '{m.title[:40]} {m.yes_sub_title[:20]}'"


class FinalWhistleFiona(FavoriteBidder):
    key = "sports_closer"
    persona = Persona(
        "Ziggy the Zebra", "Head Referee", "🦓",
        "Born in stripes, so refereeing was the obvious career. Bets the winner once the game's decided and "
        "blows the whistle before any comeback can start.",
    )
    series = ("KXNFLGAME", "KXNCAAFGAME", "KXMLBGAME", "KXNBAGAME")
    one_per_event = True

    def __init__(self, min_price: float = 0.97, max_price: float = 0.995, hours_before: float = 3,
                 hours_after: float = 2, **kw):
        super().__init__(min_price=min_price, max_price=max_price, **kw)
        self.hours_before = hours_before
        self.hours_after = hours_after

    def in_hours(self, m: Market, now: datetime) -> bool:
        """Late in the game: Kalshi's expected end is about 3 hours after the start."""
        end = m.expected_expiration_time
        return bool(end) and end - timedelta(hours=self.hours_before) <= now <= end + timedelta(hours=self.hours_after)

    def describe(self, m, side, price):
        return f"game all but over: {side.value.upper()} @ {price:.2f} on '{m.title[:60]}'"
