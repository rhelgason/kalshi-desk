"""
The desk loop: fetch markets -> ask every employee for trades -> paper-fill -> settle.

    every tick (default 15s):
        refresh crypto ladders closing within the horizon, plus spot/vol
        build a Snapshot and run every strategy on it
        fetch fresh orderbooks for anything a strategy wants, paper-fill it
    every few minutes:
        re-discover which events/markets exist
        check held markets for settlement and pay out
"""

from __future__ import annotations

import asyncio
import gzip
import inspect
import json
import logging
import math
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dataclasses import replace
from typing import Optional
from zoneinfo import ZoneInfo

from desk.config import DeskConfig
from desk.feeds.crypto import CryptoFeed
from desk.journal import RunJournal, short_reason
from desk.kalshi.client import KalshiAPIError, KalshiClient
from desk.kalshi.fees import FeeSchedule
from desk.kalshi.models import Event, Market, Side
from desk.paper.broker import ExecutionResult, PaperBroker, RestingOrder
from desk.paper.ledger import Ledger
from desk.paper.pool import Pool, PoolAccountView, PoolState, event_of
from desk.paper.scoreboard import format_scoreboard, scoreboard_rows
from desk import bonus, hr, notify
from desk.strategies import REGISTRY, strategy_params
from desk.strategies.base import Snapshot, Strategy, TradeIntent

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _done(x):
    """The paper broker answers at once; the live broker has to ask Kalshi."""
    return await x if inspect.isawaitable(x) else x


MIN_BET_DOLLARS = 0.25
NOTIFY = "_notify"  # status row: when the last daily phone summary went out
DAILY_HOUR = 21  # 9 PM  # smallest bet the pool places (Kalshi's own step is 0.01 contracts)


# Checks in a row (2 minutes apart) a difference from Kalshi must last before real trading halts
# 11-04: 15 checks (30 minutes), was 3. Fills and payouts reach Kalshi and our books minutes apart, and the owner
# would rather keep trading through a difference that fixes itself; the $40 daily-loss stop still guards the money.
MISMATCH_CHECKS = 15
BOOKS_HALT = "our books don't match Kalshi"
SHARD_MOVE = "_shard_move"  # status key: the last cash transfer between Kalshi shards

class Desk:
    def __init__(
        self,
        config: DeskConfig,
        client: KalshiClient,
        strategies: Optional[list[Strategy]],
        ledger: Ledger,
        feed: Optional[CryptoFeed] = None,
        record_path: Optional[str] = None,
        max_intents_per_strategy: int = 10,
        accounts: Optional[dict] = None,
    ):
        self.config = config
        self.client = client
        self.feed = feed
        self.ledger = ledger
        self.record_path = record_path
        self.max_intents_per_strategy = max_intents_per_strategy

        # strategies=None means "staff the desk from the HR roster" (desk.yaml +
        # website overrides, minus fired employees). Passing a list pins it.
        self.manage_roster = strategies is None
        self.strategies: list[Strategy] = list(strategies or [])
        self._strategy_params: dict[str, dict] = {}
        self.roster: dict[str, hr.EmployeeRecord] = {}
        self.policy: dict = hr.load_policy(ledger)
        self.inactive: set[str] = set()
        self.multipliers: dict[str, float] = {}
        self.season = ledger.season
        # Real money only when desk.yaml says `trading: live` (and the host and API key agree: desk/live)
        self.guard = None
        if config.trading == "live":
            from desk.live import make_live_broker

            self.broker = make_live_broker(config, ledger, accounts or {}, client)
            self.guard = self.broker.guard
        else:
            self.broker = PaperBroker(ledger, accounts or {}, liquidity_share=config.liquidity_share)
        # The office pool everyone but the control group bets out of (desk.paper.pool)
        self.pool = Pool(self.policy["pool"], ())
        self.bonus: dict = {}  # the Employee of the Week's bonus pot (desk/bonus.py), reloaded each run
        if accounts:
            # A saved account that disagrees with the records about its starting money is stale
            # (e.g. re-added empty while it was off the roster): drop it so it's rebuilt below
            start = {r["strategy"]: float(r["starting_cash"])
                     for r in ledger._rows("SELECT strategy, starting_cash FROM accounts")}
            for k in [k for k, a in accounts.items() if k in start and abs(a.starting_cash - start[k]) > 1e-6]:
                logger.warning("Saved account for %s is stale; rebuilding it from the records", k)
                del accounts[k]
        self.sync_hr()
        if accounts is None:
            self._ensure_account_rows()
            self.broker.accounts = ledger.load_accounts(config.starting_cash, self._all_keys())
            self._ensure_accounts()

        self.crypto_event_tickers: list[str] = []
        self.broad_markets: dict[str, Market] = {}
        self.fees: dict[str, FeeSchedule] = {}
        self.marks: dict[str, float] = {}
        self.last_snapshot: Optional[Snapshot] = None
        self._last_universe: Optional[datetime] = None
        self._last_crypto: Optional[datetime] = None
        self._last_slow: Optional[datetime] = None
        # Optional precomputed metrics (the cloud runner keeps these in its saved
        # state so it doesn't reread whole tables every run)
        self.drawdowns: Optional[dict[str, float]] = None
        self.briers: Optional[dict[str, Optional[float]]] = None
        self._last_settle: Optional[datetime] = None
        self._last_equity: Optional[datetime] = None
        self._last_status: Optional[datetime] = None
        self._last_accuracy: Optional[datetime] = None
        self.started_at = _now()
        self.tick_count = 0
        # This run's summary (desk/journal.py), saved to the `runs` table at the end of each tick
        self.journal = RunJournal()
        self._last_prune: Optional[datetime] = None

    @property
    def accounts(self):
        return self.broker.accounts

    @property
    def personas(self) -> dict[str, str]:
        return {s.key: f"{s.persona.emoji} {s.persona.name} ({s.key})" for s in self.strategies}

    # ------------------------------------------------------------------
    # HR: who's working, at what size, with which settings
    # ------------------------------------------------------------------

    def _all_keys(self) -> list[str]:
        return sorted({s.key for s in self.strategies} | set(self.roster))

    def opening_cash(self, key: str) -> float:
        """A new hire's own money: none for pool members (they share the pool), paper cash for the control group."""
        rec = self.roster.get(key)
        return self.config.starting_cash if rec and rec.control else 0.0

    def _ensure_account_rows(self) -> None:
        keys = self._all_keys()
        members = [k for k in keys if not (self.roster.get(k) and self.roster[k].control)]
        existing = {r["strategy"] for r in self.ledger._rows("SELECT strategy FROM accounts")}
        if members and not existing & set(members):
            # A brand-new office: split the pool evenly to start
            for k in members:
                self.ledger.ensure_account(k, self.config.pool_cash / len(members))
        for k in keys:
            self.ledger.ensure_account(k, self.opening_cash(k))

    def _ensure_accounts(self) -> None:
        missing = [k for k in self._all_keys() if k not in self.accounts]
        for k in missing:
            self.ledger.ensure_account(k, self.opening_cash(k))
        if missing:
            # Someone back on staff (or a new hire): their account as the records say, not an empty one.
            # A pool member re-added with $0 left their share out of the books (2026-10-20 real-book halt)
            self.accounts.update(self.ledger.load_accounts(self.config.starting_cash, missing))

    def _add_staff_markets(self) -> None:
        """
        A hire's markets join this book's lists (a coin specialist's 15-minute series, an "other" employee's
        series), so hiring onto the real book needs no yaml change. The yaml's own lists are never shrunk.
        """
        if not hasattr(self, "_yaml_series"):
            self._yaml_series = (list(self.config.crypto_series), list(self.config.other_series))
        crypto, other = (list(x) for x in self._yaml_series)
        for s in self.strategies:
            coin = getattr(s, "coin", "")
            if coin and f"KX{coin}15M" not in crypto:
                crypto.append(f"KX{coin}15M")
            if s.scope == "other":
                other += [x for x in getattr(s, "series", ()) if x not in other]
        self.config.crypto_series, self.config.other_series = crypto, other

    def sync_hr(self) -> None:
        """Apply the latest roster and settings from the database (run before each tick)."""
        season = self.ledger.refresh_season()
        self.policy = hr.load_policy(self.ledger)
        if season != self.season:
            logger.info("Season %s started: everyone begins fresh", season)
            self.season = season
            self._ensure_account_rows()
            self.broker.accounts = self.ledger.load_accounts(self.config.starting_cash, self._all_keys())
            self.marks = {}
            self.drawdowns = {} if self.drawdowns is not None else None
            self.pool.state = PoolState()
            self.broker.resting = []  # last season's bids don't carry over
            self.broker.sync_resting_views()
        if not self.policy.get("last_review"):
            self.policy["last_review"] = _now().isoformat()  # first review one period from now
            hr.save_policy(self.ledger, self.policy)

        # `enabled: false` in this book's config means not on this book at all (e.g. the
        # yardsticks on real money): no roster row, no pool share, nothing on its dashboard
        # ...unless hired onto it since (hr.hire, the policy's `hired` list): no new season needed
        hired = [k for k in self.policy.get("hired") or [] if k in REGISTRY]
        keys = ([k for k in REGISTRY if (self.config.strategies.get(k) or {}).get("enabled", True) or k in hired]
                if self.manage_roster else [s.key for s in self.strategies])
        self.roster = hr.load_roster(self.ledger, keys)
        hr.reinstate_expired(self.ledger, self.roster)

        if self.manage_roster:
            wanted = hr.effective_strategy_config(self.config.strategies, self.roster, hired)
            current = {s.key: s for s in self.strategies}
            staff = []
            for key, cls in REGISTRY.items():
                params = dict(wanted.get(key) or {})
                if not params.pop("enabled", True):
                    continue
                strat = current.get(key)
                if strat is None or self._strategy_params.get(key) != params:
                    try:
                        fresh = cls(**params)
                    except TypeError as e:  # a bad override from the website shouldn't stop the desk
                        logger.error("Bad settings for %s (%s); keeping previous settings", key, e)
                        if strat:
                            staff.append(strat)
                        continue
                    if strat is not None:
                        state = strat.get_state()
                        if state is not None:
                            fresh.set_state(state)
                        logger.info("%s now using settings %s", key, params)
                    strat = fresh
                    self._strategy_params[key] = params
                staff.append(strat)
            self.strategies = staff
            self._add_staff_markets()

        self.inactive = {k for k, r in self.roster.items() if not r.is_working()}
        self.multipliers = {k: r.multiplier for k, r in self.roster.items()}
        self.bonus = bonus.load(self.ledger)
        self.pool.settings = self.policy["pool"]
        self.pool.members = self.broker.pool_members = {k for k, r in self.roster.items() if not r.control}
        if self.manage_roster and self.broker.accounts:
            # Retired employees (no longer on staff) stop being tracked once they hold nothing
            keep = set(self._all_keys())
            for k in [k for k, a in self.broker.accounts.items() if k not in keep and not a.open_tickers]:
                del self.broker.accounts[k]
        if self.broker.accounts:
            self._ensure_accounts()

    # ------------------------------------------------------------------
    # Universe discovery
    # ------------------------------------------------------------------

    async def refresh_universe(self) -> None:
        await self.refresh_crypto()
        await self.refresh_broad()

    async def refresh_crypto(self) -> None:
        """Find open crypto events settling within the horizon (cheap; runs every minute)."""
        now = _now()
        horizon = now + timedelta(hours=self.config.crypto_horizon_hours)
        tickers = []
        for series in self.config.crypto_series:
            try:
                events = await self.client.get_events(series_ticker=series, status="open", with_markets=False)
            except KalshiAPIError as e:
                logger.warning("Couldn't list events for %s: %s", series, e)
                continue
            for e in events:
                if e.strike_date and now < e.strike_date <= horizon:
                    tickers.append(e.event_ticker)
            await self._fee_for_series(series)
        if set(tickers) != set(self.crypto_event_tickers):
            logger.info("Crypto events: %s", ", ".join(sorted(tickers)) or "none")
        self.crypto_event_tickers = tickers
        self._last_crypto = now

    async def refresh_broad(self) -> None:
        """Scan non-crypto markets closing soon (bigger; runs every few minutes)."""
        now = _now()
        if self.config.broad_scan:
            start = int((now + timedelta(minutes=10)).timestamp())
            end = int((now + timedelta(days=self.config.broad_max_days)).timestamp())
            try:
                markets = await self.client.get_markets(
                    min_close_ts=start, max_close_ts=end, max_items=self.config.broad_max_markets
                )
                self.broad_markets = {m.ticker: m for m in markets if m.is_tradeable}
            except KalshiAPIError as e:
                logger.warning("Broad market scan failed: %s", e)
            logger.info("Broad scan: %d markets closing within %g days", len(self.broad_markets),
                        self.config.broad_max_days)
        self._last_universe = now

    # ------------------------------------------------------------------
    # One tick
    # ------------------------------------------------------------------

    def _events_to_fetch(self) -> list[str]:
        """Fast series every tick; slow (hourly ladder) series only when due."""
        now = _now()
        slow_due = self._due(self._last_slow, self.config.slow_series_every_seconds, now)
        if slow_due:
            self._last_slow = now
        slow = set(self.config.slow_series)
        return [t for t in self.crypto_event_tickers if slow_due or t.split("-", 1)[0] not in slow]

    async def build_snapshot(self) -> Snapshot:
        events: list[Event] = []
        tickers = self._events_to_fetch()
        results = await asyncio.gather(*(self.client.get_event(t) for t in tickers), return_exceptions=True)
        for t, r in zip(tickers, results):
            if isinstance(r, Exception):
                logger.warning("Failed to fetch event %s: %s", t, r)
            else:
                events.append(r)
        quotes = await self.feed.refresh() if self.feed else {}
        other = await self.fetch_other()
        snap = Snapshot.build(_now(), events, list(self.broad_markets.values()) + other, quotes, self.fees)
        if any(s.wants_trades for s in self.strategies):
            snap.trades = await self.fetch_trades(snap)
        return snap

    async def fetch_other(self) -> list[Market]:
        """
        The other_series markets about to be decided (weather today, games today), straight from the events
        list with their prices: one call per series each run, not one per event.
        """
        now = _now()
        lo, hi = now - timedelta(hours=3), now + timedelta(hours=self.config.other_horizon_hours)
        series = list(self.config.other_series)
        listed = await asyncio.gather(*(self.client.get_events(series_ticker=s, status="open", with_markets=True,
                                                               page_size=200) for s in series), return_exceptions=True)
        out = []
        for s, events in zip(series, listed):
            if isinstance(events, Exception):
                logger.warning("Couldn't list events for %s: %s", s, events)
                continue
            try:
                await self._fee_for_series(s)
            except KalshiAPIError as e:
                logger.warning("Couldn't get the fee schedule for %s: %s", s, e)
            for e in events:
                for m in e.markets:
                    when = e.strike_date or m.expected_expiration_time or m.close_time
                    if m.is_tradeable and when and lo <= when <= hi:
                        out.append(m)
        return out

    def scoped(self, snap: Snapshot, scope: str) -> Snapshot:
        """The coin employees see only coin markets, the "other" employees only other_series markets."""
        if not self.config.other_series:
            return snap
        other = set(self.config.other_series)
        markets = {t: m for t, m in snap.markets.items() if (m.series_ticker in other) == (scope == "other")}
        return replace(snap, markets=markets)

    async def fetch_trades(self, snap: Snapshot) -> dict[str, list[dict]]:
        """Latest trades for the busiest markets (for tape-reading employees)."""
        busy = sorted(
            (m for m in snap.markets.values() if m.is_tradeable and m.mid is not None and 0.1 <= m.mid <= 0.9),
            key=lambda m: m.volume_24h, reverse=True,
        )[: self.config.trades_watch_markets]
        results = await asyncio.gather(
            *(self.client.get_trades(m.ticker, limit=50, max_items=50) for m in busy), return_exceptions=True
        )
        return {m.ticker: r for m, r in zip(busy, results) if not isinstance(r, Exception)}

    async def _fee_for_series(self, series: str) -> FeeSchedule:
        if series in self.fees:
            return self.fees[series]
        fee = await self.client.get_fee_schedule(series)
        if not fee.assumed:  # only Kalshi's real answer is kept (and saved between cloud runs)
            self.fees[series] = fee
        return fee

    async def _fees_for(self, tickers: list[str], snap: Snapshot) -> dict[str, FeeSchedule]:
        out = {}
        for t in tickers:
            m = snap.markets.get(t)
            out[t] = await self._fee_for_series(m.series_ticker if m else t.split("-", 1)[0])
        return out

    async def run_strategies(self, snap: Snapshot) -> list[ExecutionResult]:
        results = []
        was_stopped = bool(self.pool.state.stopped_at)
        self.pool.update(self.pool.total_equity(self.accounts, self.marks), _now(), self.pool.capital(self.accounts))
        if self.guard and self.pool.state.stopped_at and not was_stopped:
            # Real money: the daily stop is a pause too (until midnight), so it pings the phone
            notify.paused(f"the pool is down {-self.pool.today:.1%} today (daily stop at "
                          f"{float(self.pool.settings['daily_stop']):.0%}); bets resume at midnight", "the pool's daily stop")
        if self.pool.stopped:
            logger.info("Daily stop: the pool is down %.1f%% today, no new bets until midnight", -self.pool.today * 100)
            for o in await _done(self.broker.cancel(self.pool.members)):  # bids waiting come down too
                self._bid_ended(o, "bid pulled: daily stop")
        halted = bool(self.guard and self.guard.halted)
        views = {scope: self.scoped(snap, scope) for scope in ("coins", "other")}
        # Higher levels go first, so they get first claim on a window's share of the pool
        for strat in sorted(self.strategies, key=lambda s: -self.multipliers.get(s.key, 1.0)):
            if strat.key in self.inactive:
                self.journal.count(strat.key, "suspended")
                continue  # suspended: positions still settle, but no new bets
            if strat.key in self.pool.members and self.pool.stopped:
                self.journal.count(strat.key, "daily stop")
                continue
            if strat.key in self.pool.members and halted:
                self.journal.count(strat.key, "trading halted")
                continue
            self.journal.count(strat.key, "on shift")
            acct = self.accounts[strat.key]
            view = PoolAccountView(acct, self.broker.free_cash(strat.key)) if strat.key in self.pool.members else acct
            try:
                intents = strat.evaluate(views.get(strat.scope, views["coins"]), view)
            except Exception:
                logger.exception("%s crashed while evaluating", strat.key)
                self.journal.count(strat.key, "crashed")
                continue
            if intents:
                self.journal.count(strat.key, "ideas", len(intents))
            intents.sort(key=lambda i: i.expected_edge, reverse=True)
            for intent in intents[: self.max_intents_per_strategy]:
                if intent.post_only:
                    await self.post_bid(strat, intent, snap)
                    continue
                bet, why = self.size(intent)
                if not bet:
                    self._skip(intent, why)
                    continue
                result = await self.execute(bet, snap)
                if result:
                    results.append(result)
                    if bet.bonus and result.filled:
                        bonus.spend(self.ledger, self.bonus, bet.bonus * result.total_cost)
        return results

    async def post_bid(self, strat: Strategy, intent: TradeIntent, snap: Snapshot) -> list[RestingOrder]:
        """Check, size and post one resting bid; every outcome is logged and recorded."""
        live, why = await self._live_post(strat, intent, snap)
        bet, why = self.size(live) if live else (None, why)
        if not bet:
            self._skip(intent, why)
            return []
        placed = await _done(self.broker.place(bet, _now()))
        if not placed:
            self._skip(bet, "not enough free cash for the bid")
            return []
        who = self.personas.get(strat.key, strat.key)
        for o in placed:
            if bet.bonus:
                o.bonus = bet.bonus
                bonus.spend(self.ledger, self.bonus, bet.bonus * o.price * o.count)
            self.journal.count(strat.key, "bids posted")
            logger.info("%s BID %s %gx %s @ %.3f (until %s) | %s", who, o.side.upper(), o.count, o.ticker, o.price,
                        o.expires_at[11:19], o.reason)
            self._safely("log decision", lambda o=o: self.ledger.record_decision(
                o.strategy, o.ticker, o.side, o.price, o.count, 0.0, "bid posted", o.reason,
                {"order_id": o.order_id, "expires_at": o.expires_at}))
        return placed

    def _skip(self, intent: TradeIntent, why: str) -> None:
        """An idea that didn't become a bet: count it, log it, and keep it for reviews."""
        self.journal.skipped(intent.strategy, why)
        logger.info("%s skipped %s: %s", self.personas.get(intent.strategy, intent.strategy),
                    ", ".join(intent.tickers), why)
        for leg in intent.legs:
            self._safely("log decision", lambda leg=leg: self.ledger.record_decision(
                intent.strategy, leg.ticker, leg.side.value, leg.limit_price, leg.count, 0.0, why, intent.reason))

    def _bid_ended(self, o: RestingOrder, outcome: str) -> None:
        self.journal.count(o.strategy, outcome)
        if o.bonus and o.remaining >= 0.01:  # the unfilled part of a bonus bid goes back to the bonus
            bonus.spend(self.ledger, self.bonus, -o.bonus * o.price * o.remaining)
        logger.info("%s %s: %s %s @ %.3f, filled %g of %g", self.personas.get(o.strategy, o.strategy), outcome,
                    o.ticker, o.side.upper(), o.price, o.filled, o.count)
        self._safely("log decision", lambda: self.ledger.record_decision(
            o.strategy, o.ticker, o.side, o.price, o.count, o.filled, outcome, o.reason, {"order_id": o.order_id}))

    async def live_post(self, strat: Strategy, intent: TradeIntent, snap: Snapshot) -> Optional[TradeIntent]:
        return (await self._live_post(strat, intent, snap))[0]

    async def _live_post(self, strat: Strategy, intent: TradeIntent,
                         snap: Snapshot) -> tuple[Optional[TradeIntent], str]:
        """
        Check a resting bid against the live order book before posting it. The
        market list can lag the book by several cents; a post-only bid at or
        above the real ask would be rejected by Kalshi, so it isn't posted here
        either. Strategies with a `reprice` hook (the patient twins) re-price.
        Returns (bid or None, why not).
        """
        try:
            books = await self.client.get_orderbooks(intent.tickers)
        except KalshiAPIError as e:
            logger.warning("Couldn't fetch books for %s: %s", intent.tickers, e)
            return None, "couldn't fetch the order book"
        live = {}
        for leg in intent.legs:
            m, book = snap.markets.get(leg.ticker), books.get(leg.ticker)
            if not m or not book:
                return None, "no order book for the market"
            live[leg.ticker] = replace(
                m, yes_bid=book.best_bid(Side.YES), yes_ask=book.best_ask(Side.YES),
                no_bid=book.best_bid(Side.NO), no_ask=book.best_ask(Side.NO))
        reprice = getattr(strat, "reprice", None)
        if reprice and len(intent.legs) == 1:
            t = intent.legs[0].ticker
            bid = reprice(intent, snap.markets[t], live[t])
            return bid, "" if bid else "no room for a bid under the live ask"
        for leg in intent.legs:
            ask = live[leg.ticker].ask(leg.side)
            if ask and leg.limit_price >= ask - 1e-9:
                return None, "bid would cross the live ask"
        return intent, ""

    def sized(self, intent: TradeIntent) -> Optional[TradeIntent]:
        return self.size(intent)[0]

    def size(self, intent: TradeIntent) -> tuple[Optional[TradeIntent], str]:
        """
        Resize a bet to its share of the pool: the employee's level times the
        pool's bet size, trimmed to what's left of the window cap. The strategy
        picks the market, side and price; the pool decides how much.
        Returns (bet or None, why not).
        """
        dollars = base = self.pool.bet_dollars(self.multipliers.get(intent.strategy, 1.0))
        dollars += bonus.extra(self.bonus, intent.strategy, base)  # Employee of the Week: bigger bets, same pool
        capped = False
        if intent.strategy in self.pool.members:
            room = min(self.pool.window_room(event_of(leg.ticker), self.accounts, self.broker.resting)
                       for leg in intent.legs)
            capped = room < dollars
            dollars = min(dollars, room)
        cost = sum(leg.count * leg.limit_price for leg in intent.legs)
        if cost <= 0:
            return None, "no price"
        if dollars <= 0:
            return None, "window cap full" if capped else "the pool is empty"
        # Kalshi takes contracts in 0.01 steps, so a small pool's $0.50 bet is still a bet
        legs = [replace(leg, count=math.floor(leg.count * dollars / cost * 100) / 100) for leg in intent.legs]
        spend = sum(leg.count * leg.limit_price for leg in legs)
        if any(leg.count < 0.01 for leg in legs) or spend < MIN_BET_DOLLARS:
            # crumbs left under the cap aren't worth an order
            return None, "window cap full" if capped else f"bet under ${MIN_BET_DOLLARS:.2f}"
        return replace(intent, legs=legs, bonus=max(spend - base, 0.0) / spend), ""

    async def match_resting(self) -> None:
        """Fill maker orders from the live trade tape since they were last checked, then expire stale ones."""
        now = _now()
        before = list(self.broker.resting)
        if self.guard:
            # Real bids: ask Kalshi what filled
            for f in await self.broker.poll(now):
                self.journal.count(f.strategy, "maker fills")
                logger.info("%s REAL MAKER FILL %s %gx %s @ %.3f", self.personas.get(f.strategy, f.strategy),
                            f.side.upper(), f.count, f.ticker, f.avg_price)
        paper = [o for o in self.broker.resting if not (self.guard and o.strategy in self.pool.members)]
        since: dict[str, datetime] = {}
        for o in paper:
            since[o.ticker] = min(since.get(o.ticker, o.checked_from), o.checked_from)
        if since:
            # Busy bitcoin markets trade ~50 times a second, so fetch every page since the order went up
            results = await asyncio.gather(
                *(self.client.get_trades(t, limit=1000, max_items=self.config.max_tape_trades,
                                         min_ts=int(s.timestamp())) for t, s in since.items()),
                return_exceptions=True)
            trades = {t: r for t, r in zip(since, results) if not isinstance(r, Exception)}
            fees = {t: self.fees.get(t.split("-", 1)[0]) or FeeSchedule() for t in since}
            for t in since:
                if t not in trades:
                    logger.warning("Couldn't fetch the trade tape for %s; its bids are checked next run", t)
            for f in self.broker.match(trades, fees, now):
                self.journal.count(f.strategy, "maker fills")
                logger.info("%s MAKER FILL %s %gx %s @ %.3f", self.personas.get(f.strategy, f.strategy),
                            f.side.upper(), f.count, f.ticker, f.avg_price)
        await _done(self.broker.expire(now))
        still = {o.order_id for o in self.broker.resting}
        for o in before:
            if o.order_id not in still:
                self._bid_ended(o, "bid filled" if o.remaining < 0.01 else
                                "bid expired" if o.filled < 0.01 else "bid expired, part filled")

    async def execute(self, intent: TradeIntent, snap: Snapshot) -> Optional[ExecutionResult]:
        try:
            books = await self.client.get_orderbooks(intent.tickers)
            fees = await self._fees_for(intent.tickers, snap)
        except KalshiAPIError as e:
            logger.warning("Couldn't fetch books for %s: %s", intent.tickers, e)
            self._skip(intent, "couldn't fetch the order book")
            return None
        context = self._safely_value(lambda: self.decision_context(intent, snap, books))
        result = await _done(self.broker.execute(intent, books, fees, signal_time=snap.now, context=context))
        self._safely("log decision", lambda: self.log_decision(intent, result, context))
        who = self.personas.get(intent.strategy, intent.strategy)
        if result.filled:
            self.journal.count(intent.strategy, "bets")
            self.journal.count(intent.strategy, "dollars bet", round(result.total_cost, 2))
            legs = ", ".join(f"{f.side.upper()} {f.count:g}x {f.ticker} @ {f.avg_price:.3f}" for f in result.fills)
            logger.info("%s BOUGHT %s | %s", who, legs, intent.reason)
        else:
            self.journal.skipped(intent.strategy, result.reason)
            logger.info("%s skipped %s: %s (%s)", who, ", ".join(intent.tickers), result.reason, intent.reason)
        return result

    # ------------------------------------------------------------------
    # Review logging: enough detail to judge every employee a month later
    # ------------------------------------------------------------------

    def decision_context(self, intent: TradeIntent, snap: Snapshot, books: dict) -> dict:
        """What the employee saw when deciding: the market, bitcoin, time left, their settings and size."""
        legs = []
        for leg in intent.legs:
            m = snap.markets.get(leg.ticker)
            book = books.get(leg.ticker)
            q = snap.underlying_for(m) if m else None
            legs.append({
                "ticker": leg.ticker, "side": leg.side.value, "limit": leg.limit_price, "count": leg.count,
                "yes_bid": m.yes_bid if m else None, "yes_ask": m.yes_ask if m else None,
                "yes_bid_size": m.yes_bid_size if m else None, "yes_ask_size": m.yes_ask_size if m else None,
                "volume": m.volume if m else None, "volume_24h": m.volume_24h if m else None,
                "strike": m.floor_strike if m else None, "strike_type": m.strike_type if m else None,
                "close_time": m.close_time.isoformat() if m and m.close_time else None,
                "secs_left": round(m.seconds_to_close(snap.now) or 0, 1) if m else None,
                "depth_at_limit": book.depth_at_or_better(leg.side, leg.limit_price) if book else None,
                "spot": q.spot if q else None, "realized_vol": q.realized_vol if q else None,
                "implied_vol": q.implied_vol if q else None, "momentum": q.momentum if q else None,
            })
        strat = next((s for s in self.strategies if s.key == intent.strategy), None)
        rec = self.roster.get(intent.strategy)
        return {
            "legs": legs, "model_prob": intent.model_prob, "expected_edge": intent.expected_edge,
            "level": rec.level if rec else None, "multiplier": self.multipliers.get(intent.strategy, 1.0),
            "params": strategy_params(strat) if strat else None,
            "cash": round(self.accounts[intent.strategy].cash, 2) if intent.strategy in self.accounts else None,
            "open_positions": len(self.accounts[intent.strategy].open_tickers) if intent.strategy in self.accounts else None,
            "hour_utc": snap.now.hour, "weekday": snap.now.weekday(),
        }

    def log_decision(self, intent: TradeIntent, result, context: Optional[dict]) -> None:
        filled = {f.ticker: f.count for f in result.fills}
        for leg in intent.legs:
            self.ledger.record_decision(
                intent.strategy, leg.ticker, leg.side.value, leg.limit_price, leg.count,
                filled.get(leg.ticker, 0.0), "filled" if result.filled else (result.reason or "not filled"),
                intent.reason, context,
            )

    def record_tape(self, snap: Snapshot) -> None:
        """Every watched market's quote this run, with bitcoin's price (crypto series only)."""
        ts = snap.now.isoformat()
        rows = []
        for m in snap.markets.values():
            if m.event_ticker.split("-", 1)[0] not in self.config.crypto_series:
                continue
            q = snap.underlying_for(m)
            rows.append((ts, m.ticker, round(m.seconds_to_close(snap.now) or 0, 1), m.yes_bid, m.yes_ask,
                         m.yes_bid_size, m.yes_ask_size, m.volume, m.floor_strike, q.spot if q else None))
        self.ledger.record_tape(rows)

    def _safely_value(self, fn):
        try:
            return fn()
        except Exception:
            logger.exception("Couldn't build review context; continuing")
            return None

    def update_marks(self, snap: Snapshot) -> None:
        for t, m in snap.markets.items():
            if m.mid is not None:
                self.marks[t] = m.mid
            elif m.last_price:
                self.marks[t] = m.last_price

    async def settle_check(self) -> dict[str, dict[str, float]]:
        held = sorted({t for a in self.accounts.values() for t in a.open_tickers})
        settled: dict[str, dict[str, float]] = {}
        for i in range(0, len(held), 50):
            chunk = held[i : i + 50]
            try:
                markets = await self.client.get_markets(tickers=chunk, exclude_multivariate=False)
            except KalshiAPIError as e:
                logger.warning("Settlement check failed: %s", e)
                continue
            for m in markets:
                if m.result == "yes":
                    value = 1.0
                elif m.result == "no":
                    value = 0.0
                elif m.settlement_value is not None and m.status in ("settled", "finalized"):
                    value = m.settlement_value
                else:
                    if m.mid is not None:
                        self.marks[m.ticker] = m.mid
                    continue
                pnl = self.broker.settle(m.ticker, value)
                if pnl:
                    settled[m.ticker] = pnl
                    for strat, p in pnl.items():
                        self.journal.count(strat, "payouts")
                        self.journal.count(strat, "payout P&L", round(p, 2))
                        logger.info("%s SETTLED %s -> %s, P&L %+.2f", self.personas.get(strat, strat),
                                    m.ticker, "YES" if value == 1 else "NO" if value == 0 else value, p)
        self._last_settle = _now()
        return settled

    def record_equity(self) -> None:
        for name, acct in self.accounts.items():
            self.ledger.record_equity(name, acct.cash, acct.equity(self.marks))

    def record_snapshot(self, snap: Snapshot) -> None:
        """Append a compact copy of the snapshot for later replay/backtests."""
        if not self.record_path:
            return
        path = Path(self.record_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": snap.now.isoformat(),
            "underlyings": {k: {"spot": q.spot, "iv": q.implied_vol, "rv": q.realized_vol}
                            for k, q in snap.underlyings.items()},
            "markets": [
                [m.ticker, m.event_ticker, m.strike_type, m.floor_strike, m.cap_strike,
                 m.yes_bid, m.yes_ask, m.yes_bid_size, m.yes_ask_size,
                 m.close_time.isoformat() if m.close_time else None]
                for m in snap.markets.values()
                if m.event_ticker.split("-", 1)[0] in self.config.crypto_series
            ],
        }
        with gzip.open(path, "at") as f:
            f.write(json.dumps(row) + "\n")

    async def tick(self) -> list[ExecutionResult]:
        """One run, journaled: whatever happens, a summary lands in the `runs` table."""
        self.journal = RunJournal()
        self.journal.capture()
        try:
            return await self._tick()
        except Exception as e:
            self.journal.info["failed"] = f"{type(e).__name__}: {e}"
            raise
        finally:
            self.journal.release()
            self._safely("record the run journal", self.record_run)

    async def _tick(self) -> list[ExecutionResult]:
        now = _now()
        j = self.journal
        with j.phase("hr"):
            self.sync_hr()
        if self.guard:
            with j.phase("guard"):
                await self.check_guard()
        with j.phase("discover"):
            if (self._last_crypto is None
                    or (now - self._last_crypto).total_seconds() >= self.config.crypto_refresh_seconds):
                await self.refresh_crypto()
            if (self._last_universe is None
                    or (now - self._last_universe).total_seconds() >= self.config.universe_refresh_seconds):
                await self.refresh_broad()

        with j.phase("bids"):
            await self.match_resting()
        with j.phase("snapshot"):
            snap = await self.build_snapshot()
        self.last_snapshot = snap
        self.update_marks(snap)
        self.record_snapshot(snap)
        with j.phase("tape"):
            self._safely("record market tape", lambda: self.record_tape(snap))
        with j.phase("decide"):
            results = await self.run_strategies(snap)

        with j.phase("settle"):
            if self._due(self._last_settle, self.config.settle_check_seconds, now):
                await self.settle_check()
            if self._due(self._last_equity, self.config.equity_every_seconds, now):
                self.record_equity()
                self._last_equity = now
        if self.guard:
            with j.phase("reconcile"):
                await self.reconcile_live()
        # The real-money book has no automatic reviews: the manager hires, fires and levels by hand
        review = hr.review_due(self.policy, now)
        week = self.office_pnl_since_review() if review else 0.0
        winner: Optional[str] = None  # this week's Employee of the Week, if a review runs
        if self.config.auto_hr and review:
            with j.phase("review"):
                for a in hr.run_review(self.ledger, self.roster, self.accounts, self.policy, now,
                                       evidence=self.compute_evidence(), pool=self.pool.equity or None):
                    logger.info("HR: %s", a)
                    j.count(a.get("strategy") or "desk", f"review: {a.get('action') or a['kind']}")
                    if a["kind"] == "award":
                        winner = a["strategy"]
            self.inactive = {k for k, r in self.roster.items() if not r.is_working()}
            self.multipliers = {k: r.multiplier for k, r in self.roster.items()}
        elif review:
            # No automatic HR, but the weekly award still happens (it changes no levels or money)
            with j.phase("review"):
                for a in hr.run_award(self.ledger, self.roster, self.accounts, self.policy, now):
                    logger.info("HR: %s", a)
                    winner = a["strategy"]
        if review:
            self.bonus = bonus.hand_out(self.ledger, self.config.bonus_pot, week, self.pool.equity,
                                        winner, now)
            logger.info("Bonus pot: %s", self.bonus)

        self.tick_count += 1
        # Reporting is best-effort: a bug in a dashboard summary must never stop
        # trading or settlement (the timer still advances, so it isn't retried every run)
        with j.phase("report"):
            if self.guard:
                self._safely("daily summary", lambda: self.daily_summary(now))
            if self._due(self._last_status, self.config.status_every_seconds, now):
                self._safely("publish status", lambda: self.publish_status(snap))
                self._last_status = now
            if self._due(self._last_accuracy, self.config.accuracy_every_seconds, now):
                self._safely("publish accuracy", self.publish_accuracy)
                self._last_accuracy = now
        return results

    # ------------------------------------------------------------------
    # Real money: the kill switch and checking our books against Kalshi
    # ------------------------------------------------------------------

    async def check_guard(self) -> None:
        """Re-read the kill switch; while it's on, nothing real stays on the book."""
        self.guard.refresh()
        self.guard.equity = self.pool.equity  # for limits set as a share of the pool
        signer = getattr(self.client, "signer", None)
        if hasattr(signer, "fingerprint"):  # which key is in use, safe to show (see KalshiSigner.fingerprint)
            self.journal.info["key"] = signer.fingerprint()
        if self.guard.halted:
            real = [o for o in self.broker.resting if o.strategy in self.pool.members]
            if real:
                for o in await self.broker.cancel_everything():
                    self._bid_ended(o, "bid pulled: trading halted")
            self.journal.info["halted"] = self.guard.state.get("reason") or True

    def recently_settled(self, minutes: float = 720) -> dict[str, tuple[float, float]]:
        """Markets the pool settled in the last `minutes`: ticker -> (net contracts held, YES minus NO, and what
        they pay). Kalshi can take minutes to pay a coin market out, and hours for a weather one once the weather
        service reports (desk/live/reconcile.py only uses this while Kalshi still shows exactly that position)."""
        since = (_now() - timedelta(minutes=minutes)).isoformat()
        members = sorted(self.pool.members)
        if not members:
            return {}
        who = ",".join("?" * len(members))
        out: dict[str, tuple[float, float]] = {}
        for r in self.ledger._rows(
                f"SELECT f.ticker, f.side, f.count, s.yes_value FROM settlements s JOIN fills f "
                f"ON f.season = s.season AND f.strategy = s.strategy AND f.ticker = s.ticker "
                f"WHERE s.season = ? AND s.ts >= ? AND s.strategy IN ({who})", (self.season, since, *members)):
            t, n, side, yes_value = r["ticker"], float(r["count"]), r["side"], float(r["yes_value"])
            net, pay = out.get(t, (0.0, 0.0))
            won = yes_value if side == "yes" else 1 - yes_value
            out[t] = (round(net + (n if side == "yes" else -n), 2), round(pay + n * won, 4))
        return out

    async def split_cash(self) -> None:
        """Kalshi pays for an order from its market's exchange shard only: coins trade on shard 2, weather on 0.
        desk.real.yaml `shards` says how to split the cash (percent per shard). 11-03 we asked Kalshi to keep that
        split itself (target allocation), but by 11-04 it had moved nothing: shard 0 still had $0 and Wendell's
        bids were refused for "insufficient balance". So the bot moves the cash itself: a shard under half its
        share is topped up to its share from the shard with the most to spare, at most once every 10 minutes
        (a transfer takes Kalshi a moment, and the next run mustn't send it twice)."""
        want = {int(k): int(v) for k, v in (self.config.shards or {}).items()}
        if not want:
            return
        try:
            rows = await self.client.get_balance_breakdown()
        except KalshiAPIError as e:
            logger.warning("Couldn't read the cash on each shard: %s", e)
            return
        have = {int(r["exchange_index"]): float(r["balance"]) for r in rows}
        self.journal.info["shards"] = {k: round(v, 2) for k, v in have.items() if v or k in want}
        total = sum(have.values())
        moved = self.ledger.get_status(SHARD_MOVE) or {}
        if total <= 0 or (moved.get("at") and _now() - datetime.fromisoformat(moved["at"]) < timedelta(minutes=10)):
            return
        for shard, pct in sorted(want.items()):
            share = total * pct / 100
            if have.get(shard, 0.0) >= share / 2:
                continue
            spare = {k: v - total * want.get(k, 0) / 100 for k, v in have.items() if k != shard}
            source = max(spare, key=spare.get, default=None)
            amount = round(min(share - have.get(shard, 0.0), spare.get(source, 0.0)), 2)
            if source is None or amount < 1:
                continue
            try:
                await self.client.transfer_between_shards(amount, source, shard)
            except KalshiAPIError as e:
                logger.warning("Couldn't move $%.2f to shard %d: %s", amount, shard, e)
                return
            logger.warning("Moved $%.2f of cash from shard %d to shard %d (split %s)", amount, source, shard, want)
            self.ledger.set_status(SHARD_MOVE, {"at": _now().isoformat(), "from": source, "to": shard, "dollars": amount})
            return

    async def reconcile_live(self) -> None:
        from desk.live.reconcile import reconcile

        # Book fills on bids posted this run first: one taken the second it went up is on Kalshi already
        for f in await self.broker.poll(_now()):
            self.journal.count(f.strategy, "maker fills")
            logger.info("%s REAL MAKER FILL %s %gx %s @ %.3f", self.personas.get(f.strategy, f.strategy),
                        f.side.upper(), f.count, f.ticker, f.avg_price)
        await self.split_cash()
        books = self.guard.books()
        if books.get("season") != self.season:
            books = {"season": self.season}  # a new season is a new pool: measure from scratch
        try:
            r = await reconcile(self.client, self.accounts, self.pool.members, self.broker.resting,
                                baseline=books.get("baseline"), settling=self.recently_settled())
        except KalshiAPIError as e:
            logger.warning("Couldn't check our books against Kalshi: %s", e)
            return
        # A difference only counts while it lasts. Fills, payouts and results reach Kalshi and our books seconds
        # apart, so one market can differ for one check and be gone by the next (11-03: BNB, then BNB again, then
        # SOL, on three checks in a row, halted trading though each fixed itself). A market has to differ on
        # MISMATCH_CHECKS checks in a row, or the cash (with every position agreeing) on as many, to halt.
        seen = books.get("seen") or {}
        seen = {t: seen.get(t, 0) + 1 for t in r.mismatches}
        drifting = not r.mismatches and abs(r.drift) > float(self.guard.limits["max_drift"])
        strikes = max([*seen.values(), books.get("strikes", 0) + 1 if drifting else 0])
        books.update(baseline=r.baseline if books.get("baseline") is None else books["baseline"],
                     strikes=strikes, seen=seen, last={**r.to_dict(), "at": _now().isoformat()})
        self.journal.info["books"] = {"balance": r.balance, "drift": r.drift, "mismatches": len(r.mismatches)}
        if r.mismatches or drifting:
            logger.warning("Our books differ from Kalshi (check %d of %d): drift $%.2f, positions %s",
                           strikes, MISMATCH_CHECKS, r.drift, r.mismatches)
        if self.guard.halted and strikes == 0 and abs(r.drift) <= float(self.guard.limits["max_drift"]) \
                and str(self.guard.state.get("reason", "")).startswith(BOOKS_HALT):
            # The safety check paused trading and the books agree again: carry on without waiting for the manager
            self.guard.resume(by="the safety check (books match Kalshi again)")
            return
        if strikes >= MISMATCH_CHECKS:
            what = (f"positions differ on {', '.join(sorted(r.mismatches))}" if r.mismatches
                    else f"cash is off by ${r.drift:+.2f}")
            self.guard.halt(f"{BOOKS_HALT}: {what}")
            for o in await self.broker.cancel_everything():
                self._bid_ended(o, "bid pulled: trading halted")
        else:
            self.guard.check_loss(self.pool.equity, self.pool.state.day_open)
            if self.guard.halted:
                for o in await self.broker.cancel_everything():
                    self._bid_ended(o, "bid pulled: trading halted")
        self.guard.save_books(books)

    def office_pnl_since_review(self) -> float:
        """The office pool's settled profit since the last review (the bonus pot takes a share)."""
        since = self.policy.get("last_review")
        if not since:
            return 0.0
        stats = hr.period_stats(self.ledger, self.accounts, datetime.fromisoformat(since))
        return sum(st.pnl for k, st in stats.items() if k in self.pool.members)

    def daily_summary(self, now: datetime) -> None:
        """Real money only: at 9 PM (the pool's time zone), a phone summary since the last one."""
        if not notify.configured():
            return
        local = now.astimezone(ZoneInfo(self.policy["pool"].get("timezone") or "America/Vancouver"))
        sent = self.ledger.get_status(NOTIFY) or {}
        if local.hour < DAILY_HOUR or sent.get("day") == local.date().isoformat():
            return
        since = sent.get("at") or (local.replace(hour=DAILY_HOUR, minute=0, second=0, microsecond=0)
                                   - timedelta(days=1)).astimezone(timezone.utc).isoformat()
        rows = self.ledger._rows("SELECT strategy, pnl FROM settlements WHERE ts >= ? AND ts < ?",
                                 (since, now.isoformat()))
        by: dict[str, float] = {}
        for r in rows:
            by[r["strategy"]] = by.get(r["strategy"], 0.0) + float(r["pnl"])
        leader = max(by.items(), key=lambda kv: kv[1]) if by else None
        open_tickers = {t for k in self.pool.members if k in self.accounts for t in self.accounts[k].open_tickers}
        riding = sum(p.yes_cost + p.no_cost for k in self.pool.members if k in self.accounts
                     for p in self.accounts[k].positions.values())
        ok = notify.daily(sum(by.values()), len(rows), sum(1 for r in rows if float(r["pnl"]) > 0),
                          (self.personas.get(leader[0], leader[0]), leader[1]) if leader else None,
                          self.pool.equity, riding, len(open_tickers),
                          halted=(self.guard.state.get("reason") or "by the manager") if self.guard.halted else None)
        if ok:
            self.ledger.set_status(NOTIFY, {"day": local.date().isoformat(), "at": now.isoformat()})

    def record_run(self) -> None:
        """Save this run's journal (and, about hourly, drop journals older than two weeks)."""
        snap = self.last_snapshot
        held = {t for a in self.accounts.values() for t in a.open_tickers}
        self.journal.info.update({
            "season": self.season,
            "tick": self.tick_count,
            "market": {
                "windows": sorted(self.crypto_event_tickers),
                "markets": len(snap.markets) if snap else 0,
                "spot": {k: round(q.spot, 2) for k, q in snap.underlyings.items()} if snap else {},
                "no_price": [s for s in self.feed.symbols if not snap or s not in snap.underlyings] if self.feed else [],
            },
            "pool": {k: v for k, v in self.pool.summary(self.accounts, self.broker.resting).items()
                     if k in ("equity", "pnl", "cash", "in_play", "today", "stopped", "braked", "bet", "window_cap")},
            "bids_waiting": len(self.broker.resting),
            "positions": len(held),
        })
        self.ledger.record_run(self.journal.summary())
        now = _now()
        if self._due(self._last_prune, 3600, now):
            self._last_prune = now
            self.ledger.prune_runs()

    def _safely(self, what: str, fn) -> None:
        try:
            fn()
        except Exception as e:
            logger.exception("Failed to %s; continuing", what)
            try:
                self.ledger.record_event("error", {"step": what, "error": f"{type(e).__name__}: {e}",
                                                   "trace": traceback.format_exc()[-2000:]})
            except Exception:
                pass

    @staticmethod
    def _due(last: Optional[datetime], every: float, now: datetime) -> bool:
        return last is None or (now - last).total_seconds() >= every

    def publish_status(self, snap: Optional[Snapshot] = None) -> None:
        """Small JSON summary the web dashboard reads (scoreboard, HR, positions, prices)."""
        rows = {r.strategy: r for r in scoreboard_rows(self.accounts, self.ledger, self.marks,
                                                       drawdowns=self.drawdowns, briers=self.briers)}
        live = {s.key: s for s in self.strategies}
        employees = []
        for key, cls in REGISTRY.items():
            rec = self.roster.get(key)
            if rec is None:
                continue
            strat = live.get(key)
            r = rows.get(key)
            employees.append({
                "key": key, "name": cls.persona.name, "title": cls.persona.title,
                "emoji": cls.persona.emoji, "blurb": cls.persona.blurb,
                "status": rec.status if rec.status != "suspended" or not rec.is_working() else "active",
                "suspended_until": rec.suspended_until, "level": rec.level,
                "level_title": hr.level_title(rec.level), "multiplier": rec.multiplier,
                "strikes": rec.strikes, "awards": rec.awards, "control": rec.control,
                "autotune": rec.autotune, "note": rec.note, "overrides": rec.params,
                "params": strategy_params(strat) if strat else {},
                "backtestable": getattr(cls, "backtestable", True),
                **({
                    "starting_cash": r.starting_cash, "equity": r.equity, "pnl": r.pnl, "roi": r.roi,
                    "realized_pnl": r.realized_pnl, "open_positions": r.open_positions, "fills": r.fills,
                    "wins": r.wins, "losses": r.losses, "win_rate": r.win_rate, "fees": r.fees,
                    "max_drawdown": r.max_drawdown, "brier": r.brier,
                } if r else {}),
            })
        positions = []
        for name, acct in self.accounts.items():
            for t, p in acct.positions.items():
                m = snap.markets.get(t) if snap else None
                positions.append({
                    "strategy": name, "ticker": t, "title": m.title if m else "",
                    "subtitle": m.yes_sub_title if m else "",
                    "yes": round(p.yes, 2), "no": round(p.no, 2),
                    "cost": round(p.yes_cost + p.no_cost, 4), "mark": self.marks.get(t),
                    "closes": m.close_time.isoformat() if m and m.close_time else None,
                    "strike": m.floor_strike if m else None,
                })
        quotes = {}
        if snap:
            quotes = {k: {"spot": q.spot, "implied_vol": q.implied_vol, "realized_vol": q.realized_vol,
                          "momentum": q.momentum} for k, q in snap.underlyings.items()}
        last_review = self.policy.get("last_review")
        next_review = (datetime.fromisoformat(last_review) + timedelta(days=float(self.policy["review_days"]))
                       if last_review else None)
        self.ledger.set_status("live", {
            "updated_at": _now().isoformat(),
            "started_at": self.started_at.isoformat(),
            "tick_count": self.tick_count,
            "env": self.config.env,
            "book": self.config.book,
            "tick_seconds": self.config.tick_seconds,
            "season": self.ledger.season,
            "hr": {
                "award_name": hr.award_name(float(self.policy["review_days"])),
                "review_days": self.policy["review_days"],
                "last_review": last_review,
                "next_review": next_review.isoformat() if next_review else None,
                "reserve": self.policy["reserve"],
                "levels": [{"title": t, "multiplier": m, "bet_pct": m * float(self.policy["pool"]["bet_pct"])}
                           for t, m in hr.LEVELS],
            },
            "pool": self.pool.summary(self.accounts, self.broker.resting),
            "trading": self.trading_status(),
            "employees": employees,
            "positions": positions,
            "underlyings": quotes,
            "crypto_events": self.crypto_event_tickers,
        })

    def trading_status(self) -> dict:
        """Paper or real money, and for real money: the kill switch and the last check against Kalshi."""
        if not self.guard:
            return {"mode": "paper"}
        return {"mode": "live", "env": self.config.env, **self.guard.state, "limits": self.guard.limits,
                "books": self.guard.books().get("last")}

    def compute_evidence(self) -> dict[str, dict]:
        """Skill-or-luck evidence for every employee this season."""
        from desk.paper.accuracy import evidence_report, evidence_report_sql

        keys = list(self.roster) or [s.key for s in self.strategies]
        report = evidence_report_sql(self.ledger, keys) if self.ledger.is_postgres else evidence_report(self.ledger, keys)
        return {e.strategy: e.to_dict() for e in report}

    def publish_accuracy(self) -> None:
        from desk.paper.accuracy import accuracy_report, accuracy_report_sql

        keys = list(self.roster) or [s.key for s in self.strategies]
        # On Postgres, aggregate in the database instead of downloading every fill
        summaries = accuracy_report_sql(self.ledger, keys) if self.ledger.is_postgres else accuracy_report(self.ledger, keys)
        if self.briers is not None:
            self.briers.update({s.strategy: s.brier_model for s in summaries})
        self.ledger.set_status("accuracy", {
            "updated_at": _now().isoformat(),
            "summaries": [s.to_dict() for s in summaries],
            "evidence": self.compute_evidence(),
            "realism": self.compute_realism(),
        })

    def compute_realism(self) -> dict[str, dict]:
        """Fill reality check per employee this season."""
        from desk.paper.realism import realism_report, realism_report_sql

        keys = list(self.roster) or [s.key for s in self.strategies]
        report = realism_report_sql(self.ledger, keys) if self.ledger.is_postgres else realism_report(self.ledger, keys)
        return {r.strategy: r.to_dict() for r in report}

    def scoreboard(self) -> str:
        return format_scoreboard(scoreboard_rows(self.accounts, self.ledger, self.marks), self.personas)

    async def run_forever(self, scoreboard_every: int = 20) -> None:
        logger.info("Desk open with %d employees: %s", len(self.strategies), ", ".join(self.personas.values()))
        while True:
            started = _now()
            try:
                await self.tick()
            except Exception:
                logger.exception("Tick failed; continuing")
            if self.tick_count % scoreboard_every == 0:
                print("\n" + self.scoreboard() + "\n", flush=True)
            elapsed = (_now() - started).total_seconds()
            await asyncio.sleep(max(0.0, self.config.tick_seconds - elapsed))
