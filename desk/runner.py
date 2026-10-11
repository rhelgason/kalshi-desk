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
from typing import Optional

from desk.config import DeskConfig
from desk.feeds.crypto import CryptoFeed
from desk.kalshi.client import KalshiAPIError, KalshiClient
from desk.kalshi.fees import FeeSchedule
from desk.kalshi.models import Event, Market
from desk.paper.broker import ExecutionResult, PaperBroker
from desk.paper.ledger import Ledger
from desk.paper.scoreboard import format_scoreboard, scoreboard_rows
from desk.strategies.base import Snapshot, Strategy, TradeIntent

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Desk:
    def __init__(
        self,
        config: DeskConfig,
        client: KalshiClient,
        strategies: list[Strategy],
        ledger: Ledger,
        feed: Optional[CryptoFeed] = None,
        record_path: Optional[str] = None,
        max_intents_per_strategy: int = 10,
    ):
        self.config = config
        self.client = client
        self.feed = feed
        self.strategies = strategies
        self.ledger = ledger
        self.record_path = record_path
        self.max_intents_per_strategy = max_intents_per_strategy

        accounts = ledger.load_accounts(config.starting_cash, [s.key for s in strategies])
        self.broker = PaperBroker(ledger, accounts, liquidity_share=config.liquidity_share)
        self.personas = {s.key: f"{s.persona.emoji} {s.persona.name} ({s.key})" for s in strategies}

        self.crypto_event_tickers: list[str] = []
        self.broad_markets: dict[str, Market] = {}
        self.fees: dict[str, FeeSchedule] = {}
        self.marks: dict[str, float] = {}
        self.last_snapshot: Optional[Snapshot] = None
        self._last_universe: Optional[datetime] = None
        self._last_crypto: Optional[datetime] = None
        self._last_settle: Optional[datetime] = None
        self.tick_count = 0

    @property
    def accounts(self):
        return self.broker.accounts

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

    async def build_snapshot(self) -> Snapshot:
        events: list[Event] = []
        results = await asyncio.gather(
            *(self.client.get_event(t) for t in self.crypto_event_tickers), return_exceptions=True
        )
        for t, r in zip(self.crypto_event_tickers, results):
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
            acct = self.accounts[strat.key]
            try:
                intents = strat.evaluate(snap, acct)
            except Exception:
                logger.exception("%s crashed while evaluating", strat.key)
                continue
            intents.sort(key=lambda i: i.expected_edge, reverse=True)
            for intent in intents[: self.max_intents_per_strategy]:
                result = await self.execute(intent, snap)
                if result:
                    results.append(result)
        return results

    async def execute(self, intent: TradeIntent, snap: Snapshot) -> Optional[ExecutionResult]:
        try:
            books = await self.client.get_orderbooks(intent.tickers)
            fees = await self._fees_for(intent.tickers, snap)
        except KalshiAPIError as e:
            logger.warning("Couldn't fetch books for %s: %s", intent.tickers, e)
            return None
        result = self.broker.execute(intent, books, fees)
        who = self.personas.get(intent.strategy, intent.strategy)
        if result.filled:
            legs = ", ".join(f"{f.side.upper()} {f.count:g}x {f.ticker} @ {f.avg_price:.3f}" for f in result.fills)
            logger.info("%s BOUGHT %s | %s", who, legs, intent.reason)
        else:
            logger.debug("%s skipped: %s (%s)", who, result.reason, intent.reason)
        return result

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
        if (self._last_crypto is None
                or (now - self._last_crypto).total_seconds() >= self.config.crypto_refresh_seconds):
            await self.refresh_crypto()
        if (self._last_universe is None
                or (now - self._last_universe).total_seconds() >= self.config.universe_refresh_seconds):
            await self.refresh_broad()

        snap = await self.build_snapshot()
        self.last_snapshot = snap
        self.update_marks(snap)
        self.record_snapshot(snap)
        results = await self.run_strategies(snap)

        if (self._last_settle is None
                or (now - self._last_settle).total_seconds() >= self.config.settle_check_seconds):
            await self.settle_check()
            self.record_equity()

        self.tick_count += 1
        return results

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
