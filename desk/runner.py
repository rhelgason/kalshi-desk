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
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dataclasses import replace
from typing import Optional

from desk.config import DeskConfig
from desk.feeds.crypto import CryptoFeed
from desk.kalshi.client import KalshiAPIError, KalshiClient
from desk.kalshi.fees import FeeSchedule
from desk.kalshi.models import Event, Market, Side
from desk.paper.broker import ExecutionResult, PaperBroker
from desk.paper.ledger import Ledger
from desk.paper.scoreboard import format_scoreboard, scoreboard_rows
from desk import hr
from desk.paper.account import PaperAccount
from desk.strategies import REGISTRY, strategy_params
from desk.strategies.base import Snapshot, Strategy, TradeIntent

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
        self.broker = PaperBroker(ledger, accounts or {}, liquidity_share=config.liquidity_share)
        self.sync_hr()
        if accounts is None:
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

    def _ensure_accounts(self) -> None:
        for k in self._all_keys():
            if k not in self.accounts:
                self.ledger.ensure_account(k, self.config.starting_cash)
                self.accounts[k] = PaperAccount(k, self.config.starting_cash)

    def sync_hr(self) -> None:
        """Apply the latest roster and settings from the database (run before each tick)."""
        season = self.ledger.refresh_season()
        self.policy = hr.load_policy(self.ledger)
        if season != self.season:
            logger.info("Season %s started: everyone begins fresh", season)
            self.season = season
            self.broker.accounts = self.ledger.load_accounts(self.config.starting_cash, self._all_keys())
            self.marks = {}
            self.drawdowns = {} if self.drawdowns is not None else None
        if not self.policy.get("last_review"):
            self.policy["last_review"] = _now().isoformat()  # first review one period from now
            hr.save_policy(self.ledger, self.policy)

        keys = list(REGISTRY) if self.manage_roster else [s.key for s in self.strategies]
        self.roster = hr.load_roster(self.ledger, keys)
        hr.reinstate_expired(self.ledger, self.roster)

        if self.manage_roster:
            wanted = hr.effective_strategy_config(self.config.strategies, self.roster)
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

        self.inactive = {k for k, r in self.roster.items() if not r.is_working()}
        self.multipliers = {k: r.multiplier for k, r in self.roster.items()}
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
            if series not in self.fees:
                self.fees[series] = await self.client.get_fee_schedule(series)
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
        snap = Snapshot.build(_now(), events, list(self.broad_markets.values()), quotes, self.fees)
        if any(s.wants_trades for s in self.strategies):
            snap.trades = await self.fetch_trades(snap)
        return snap

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

    async def _fees_for(self, tickers: list[str], snap: Snapshot) -> dict[str, FeeSchedule]:
        out = {}
        for t in tickers:
            m = snap.markets.get(t)
            series = m.series_ticker if m else t.split("-", 1)[0]
            if series not in self.fees:
                self.fees[series] = await self.client.get_fee_schedule(series)
            out[t] = self.fees[series]
        return out

    async def run_strategies(self, snap: Snapshot) -> list[ExecutionResult]:
        results = []
        for strat in self.strategies:
            if strat.key in self.inactive:
                continue  # suspended: positions still settle, but no new bets
            acct = self.accounts[strat.key]
            try:
                intents = strat.evaluate(snap, acct)
            except Exception:
                logger.exception("%s crashed while evaluating", strat.key)
                continue
            intents.sort(key=lambda i: i.expected_edge, reverse=True)
            for intent in intents[: self.max_intents_per_strategy]:
                if intent.post_only:
                    intent = await self.live_post(strat, intent, snap)
                    if not intent:
                        continue
                    for o in self.broker.place(self._scaled(intent), _now()):
                        logger.debug("%s resting %s %s x%g @ %.2f", strat.key, o.ticker, o.side, o.count, o.price)
                    continue
                result = await self.execute(intent, snap)
                if result:
                    results.append(result)
        return results

    async def live_post(self, strat: Strategy, intent: TradeIntent, snap: Snapshot) -> Optional[TradeIntent]:
        """
        Check a resting bid against the live order book before posting it. The
        market list can lag the book by several cents; a post-only bid at or
        above the real ask would be rejected by Kalshi, so it isn't posted here
        either. Strategies with a `reprice` hook (the patient twins) re-price.
        """
        try:
            books = await self.client.get_orderbooks(intent.tickers)
        except KalshiAPIError as e:
            logger.warning("Couldn't fetch books for %s: %s", intent.tickers, e)
            return None
        live = {}
        for leg in intent.legs:
            m, book = snap.markets.get(leg.ticker), books.get(leg.ticker)
            if not m or not book:
                return None
            live[leg.ticker] = replace(
                m, yes_bid=book.best_bid(Side.YES), yes_ask=book.best_ask(Side.YES),
                no_bid=book.best_bid(Side.NO), no_ask=book.best_ask(Side.NO))
        reprice = getattr(strat, "reprice", None)
        if reprice and len(intent.legs) == 1:
            t = intent.legs[0].ticker
            return reprice(intent, snap.markets[t], live[t])
        for leg in intent.legs:
            ask = live[leg.ticker].ask(leg.side)
            if ask and leg.limit_price >= ask - 1e-9:
                return None
        return intent

    def _scaled(self, intent: TradeIntent) -> TradeIntent:
        mult = self.multipliers.get(intent.strategy, 1.0)
        if mult == 1.0:
            return intent
        # Level-based sizing: promotions mean bigger bets with the same strategy
        return replace(intent, legs=[replace(leg, count=max(1.0, round(leg.count * mult, 2))) for leg in intent.legs])

    async def match_resting(self) -> None:
        """Fill maker orders from the live trade tape since they were placed, then expire stale ones."""
        now = _now()
        since: dict[str, datetime] = {}
        for o in self.broker.resting:
            placed = datetime.fromisoformat(o.placed_at)
            since[o.ticker] = min(since.get(o.ticker, placed), placed)
        if since:
            # Busy bitcoin markets trade ~50 times a second, so fetch every page since the order went up
            results = await asyncio.gather(
                *(self.client.get_trades(t, limit=1000, max_items=self.config.max_tape_trades,
                                         min_ts=int(s.timestamp())) for t, s in since.items()),
                return_exceptions=True)
            trades = {t: r for t, r in zip(since, results) if not isinstance(r, Exception)}
            fees = {t: self.fees.get(t.split("-", 1)[0]) or FeeSchedule() for t in since}
            for f in self.broker.match(trades, fees, now):
                logger.info("Maker fill: %s %s %gx @ %.2f", f.ticker, f.side.upper(), f.count, f.avg_price)
        self.broker.expire(now)

    async def execute(self, intent: TradeIntent, snap: Snapshot) -> Optional[ExecutionResult]:
        intent = self._scaled(intent)
        try:
            books = await self.client.get_orderbooks(intent.tickers)
            fees = await self._fees_for(intent.tickers, snap)
        except KalshiAPIError as e:
            logger.warning("Couldn't fetch books for %s: %s", intent.tickers, e)
            return None
        context = self._safely_value(lambda: self.decision_context(intent, snap, books))
        result = self.broker.execute(intent, books, fees, signal_time=snap.now, context=context)
        self._safely("log decision", lambda: self.log_decision(intent, result, context))
        who = self.personas.get(intent.strategy, intent.strategy)
        if result.filled:
            legs = ", ".join(f"{f.side.upper()} {f.count:g}x {f.ticker} @ {f.avg_price:.3f}" for f in result.fills)
            logger.info("%s BOUGHT %s | %s", who, legs, intent.reason)
        else:
            logger.debug("%s skipped: %s (%s)", who, result.reason, intent.reason)
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
        now = _now()
        self.sync_hr()
        if (self._last_crypto is None
                or (now - self._last_crypto).total_seconds() >= self.config.crypto_refresh_seconds):
            await self.refresh_crypto()
        if (self._last_universe is None
                or (now - self._last_universe).total_seconds() >= self.config.universe_refresh_seconds):
            await self.refresh_broad()

        await self.match_resting()
        snap = await self.build_snapshot()
        self.last_snapshot = snap
        self.update_marks(snap)
        self.record_snapshot(snap)
        self._safely("record market tape", lambda: self.record_tape(snap))
        results = await self.run_strategies(snap)

        if self._due(self._last_settle, self.config.settle_check_seconds, now):
            await self.settle_check()
        if self._due(self._last_equity, self.config.equity_every_seconds, now):
            self.record_equity()
            self._last_equity = now
        if hr.review_due(self.policy, now):
            for a in hr.run_review(self.ledger, self.roster, self.accounts, self.policy, now,
                                   evidence=self.compute_evidence()):
                logger.info("HR: %s", a)
            self.inactive = {k for k, r in self.roster.items() if not r.is_working()}
            self.multipliers = {k: r.multiplier for k, r in self.roster.items()}

        self.tick_count += 1
        # Reporting is best-effort: a bug in a dashboard summary must never stop
        # trading or settlement (the timer still advances, so it isn't retried every run)
        if self._due(self._last_status, self.config.status_every_seconds, now):
            self._safely("publish status", lambda: self.publish_status(snap))
            self._last_status = now
        if self._due(self._last_accuracy, self.config.accuracy_every_seconds, now):
            self._safely("publish accuracy", self.publish_accuracy)
            self._last_accuracy = now
        return results

    def _safely(self, what: str, fn) -> None:
        try:
            fn()
        except Exception:
            logger.exception("Failed to %s; continuing", what)
            try:
                self.ledger.record_event("error", {"step": what})
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
            "tick_seconds": self.config.tick_seconds,
            "season": self.ledger.season,
            "hr": {
                "award_name": hr.award_name(float(self.policy["review_days"])),
                "review_days": self.policy["review_days"],
                "last_review": last_review,
                "next_review": next_review.isoformat() if next_review else None,
                "reserve": self.policy["reserve"],
                "levels": [{"title": t, "multiplier": m} for t, m in hr.LEVELS],
            },
            "employees": employees,
            "positions": positions,
            "underlyings": quotes,
            "crypto_events": self.crypto_event_tickers,
        })

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
