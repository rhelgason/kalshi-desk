"""
Minute-by-minute replay of settled markets.

At each minute t:
  1. pay out any market that closed at or before t
  2. build the Snapshot an employee would have seen live: every market open at
     t with its best bid/ask from the candle ending at t, and each coin's price,
     realized vol (last 4 hours), implied vol (DVOL), and momentum at t
  3. run every employee and paper-fill their trades through the same
     PaperBroker used live, with Kalshi's fees

Realism caveats (results are optimistic, not pessimistic):
  - Candles show the best bid/ask but not how many contracts were offered. We
    assume `depth` contracts at the quote.
  - With fill_delay=0 you trade at the exact quote the strategy saw. Live bots
    are a few seconds late; fill_delay=1 fills at the next minute's quote
    instead, and only if it's still at or below your limit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Optional

from desk.backtest.data import BacktestData, HistoricalMarket
from desk.feeds.crypto import UnderlyingQuote, underlying_for_series
from desk.kalshi.fees import FeeSchedule
from desk.kalshi.models import Level, Market, Orderbook
from desk.paper.broker import PaperBroker
from desk.paper.ledger import Ledger
from desk.strategies.base import Snapshot, Strategy

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    starting_cash: float = 1000.0
    depth: float = 100.0  # contracts assumed available at the best quote
    fill_delay: int = 0  # minutes between seeing a quote and trading
    equity_every_minutes: int = 60
    fees: dict[str, FeeSchedule] = field(default_factory=dict)  # by series; default quadratic x1


def _dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, timezone.utc)


class Backtest:
    def __init__(self, data: BacktestData, strategies: list[Strategy], config: BacktestConfig,
                 ledger: Optional[Ledger] = None):
        self.data = data
        self.strategies = strategies
        self.config = config
        self.ledger = ledger or Ledger(":memory:")
        accounts = self.ledger.load_accounts(config.starting_cash, [s.key for s in strategies])
        self.broker = PaperBroker(self.ledger, accounts, liquidity_share=1.0)
        self.by_ticker = {hm.market.ticker: hm for hm in data.markets}
        self.stats = {"minutes": 0, "intents": 0, "fills": 0, "skipped": 0}

    @property
    def accounts(self):
        return self.broker.accounts

    def _market_at(self, hm: HistoricalMarket, ts: int) -> Optional[Market]:
        m = hm.market
        if not (m.open_time and m.close_time) or not (_ts(m.open_time) <= ts < _ts(m.close_time)):
            return None
        q = hm.quote_at(ts)
        if not q:
            return None
        bid, ask, vol = q
        if not (0 < bid < ask < 1):
            return None  # no two-sided market yet
        return replace(
            m, status="active", result="", settlement_value=None,
            yes_bid=bid, yes_ask=ask, no_bid=round(1 - ask, 4), no_ask=round(1 - bid, 4),
            yes_bid_size=self.config.depth, yes_ask_size=self.config.depth,
            volume_24h=max(vol, 1e6),  # candles lack 24h volume; don't let filters reject on it
        )

    def _book(self, ticker: str, ts: int) -> Optional[Orderbook]:
        hm = self.by_ticker[ticker]
        q = hm.quote_at(ts)
        if not q:
            return None
        bid, ask, _ = q
        d = self.config.depth
        return Orderbook(ticker, yes_bids=[Level(bid, d)] if bid > 0 else [],
                         no_bids=[Level(round(1 - ask, 4), d)] if ask < 1 else [])

    def _quotes(self, ts: int) -> dict[str, UnderlyingQuote]:
        out = {}
        for sym, series in self.data.spot.items():
            price = series.price(ts)
            if price is None:
                continue
            out[sym] = UnderlyingQuote(
                symbol=sym, spot=price,
                implied_vol=self.data.implied_vol(sym, ts),
                realized_vol=series.realized_vol(ts),
                momentum=series.momentum(ts),
                fetched_at=_dt(ts),
            )
        return out

    def _fees_for(self, tickers: list[str]) -> dict[str, FeeSchedule]:
        return {t: self.config.fees.get(self.by_ticker[t].market.series_ticker, FeeSchedule()) for t in tickers}

    def run(self, progress_every_days: float = 7) -> None:
        markets = sorted(self.data.markets, key=lambda hm: hm.market.open_time or _dt(0))
        to_settle = sorted(markets, key=lambda hm: hm.market.close_time or _dt(0))
        start = max(self.data.start, min(_ts(hm.market.open_time) for hm in markets if hm.market.open_time))
        end = self.data.end
        settle_i = 0
        open_i = 0
        active: list[HistoricalMarket] = []
        next_progress = start + progress_every_days * 86400

        for ts in range(start - start % 60, end + 60, 60):
            iso = _dt(ts).isoformat()
            # 1. settlements
            while settle_i < len(to_settle) and _ts(to_settle[settle_i].market.close_time) <= ts:
                hm = to_settle[settle_i]
                settle_i += 1
                if hm.yes_value is not None:
                    self.broker.settle(hm.market.ticker, hm.yes_value, ts=iso)

            # 2. snapshot of markets open right now
            while open_i < len(markets) and _ts(markets[open_i].market.open_time) <= ts:
                active.append(markets[open_i])
                open_i += 1
            active = [hm for hm in active if _ts(hm.market.close_time) > ts]
            live = [m for m in (self._market_at(hm, ts) for hm in active) if m]
            if not live:
                continue
            snap = Snapshot.build(_dt(ts), [], live, self._quotes(ts), self.config.fees)
            self.stats["minutes"] += 1

            # 3. employees trade
            fill_ts = ts + 60 * self.config.fill_delay
            for strat in self.strategies:
                for intent in strat.evaluate(snap, self.accounts[strat.key]):
                    self.stats["intents"] += 1
                    books = {t: self._book(t, fill_ts) for t in intent.tickers}
                    if any(b is None for b in books.values()):
                        self.stats["skipped"] += 1
                        continue
                    result = self.broker.execute(intent, books, self._fees_for(intent.tickers), ts=iso)
                    self.stats["fills" if result.filled else "skipped"] += 1

            if self.stats["minutes"] % self.config.equity_every_minutes == 0:
                marks = {m.ticker: m.mid for m in live if m.mid is not None}
                for name, acct in self.accounts.items():
                    self.ledger.record_equity(name, acct.cash, acct.equity(marks), ts=iso)

            if ts >= next_progress:
                logger.info("Backtest at %s: %d fills so far", _dt(ts).date(), self.stats["fills"])
                next_progress += progress_every_days * 86400

        # Final equity point after everything has settled
        iso = _dt(end).isoformat()
        for name, acct in self.accounts.items():
            self.ledger.record_equity(name, acct.cash, acct.equity({}), ts=iso)


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())
