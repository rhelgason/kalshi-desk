"""
Seed a new season from history: "what if we had started this staff N days ago?"

The replay runs the book's own employees through the same pieces the bot uses
live (strategy code, the office pool's sizing and guardrails, the paper broker
and Kalshi's fees) over stored 15-minute markets, then writes the result into a
new season with the original timestamps. The bot carries on from there.

Kept honest on purpose:
  - the employees look every 2 minutes, like the hosted bot
  - a bet fills at the NEXT minute's quote, and only if it's still at or under
    the price the employee saw (otherwise it's skipped, as live)
  - thin markets (`slippage`, dollars per contract by series) pay extra: the
    limit is raised by that much and the fill costs that much more
  - every replayed fill is marked "[replay]" in its reason and context
Candles show prices but not how many contracts were offered, so `depth`
contracts are assumed at the quote.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

from desk.backtest.data import BacktestData
from desk.backtest.engine import Backtest, BacktestConfig
from desk.kalshi.fees import FeeSchedule
from desk.kalshi.models import Level, Orderbook
from desk.paper.ledger import Ledger
from desk.paper.pool import Pool, PoolAccountView
from desk.strategies.base import Strategy, TradeIntent

logger = logging.getLogger(__name__)

REPLAY_TAG = "[replay] "


def _dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, timezone.utc)


class SeasonReplay(Backtest):
    def __init__(self, data: BacktestData, strategies: list[Strategy], members: set[str],
                 multipliers: dict[str, float], pool_settings: dict, pool_cash: float, control_cash: float,
                 fees: dict[str, FeeSchedule], slippage: Optional[dict[str, float]] = None,
                 every_minutes: int = 2, depth: float = 100.0):
        ledger = Ledger(":memory:")
        for s in strategies:  # pool members share the pool; the control group has its own money
            ledger.set_starting_cash(s.key, pool_cash / len(members) if s.key in members else control_cash)
        super().__init__(data, strategies, BacktestConfig(depth=depth, fill_delay=1, fees=fees,
                                                          equity_every_minutes=60), ledger)
        self.members = members
        self.broker.pool_members = members
        self.multipliers = multipliers
        self.pool = Pool(pool_settings, members)
        self.slippage = slippage or {}
        self.every = every_minutes

    def _slip(self, ticker: str) -> float:
        return self.slippage.get(self.by_ticker[ticker].market.series_ticker, 0.0)

    def _book(self, ticker: str, ts: int) -> Optional[Orderbook]:
        book = super()._book(ticker, ts)
        s = self._slip(ticker)
        if book is None or not s:
            return book
        # Buying either side costs `s` more: both sides' bids sit `s` lower
        return Orderbook(ticker, [Level(round(lv.price - s, 4), lv.size) for lv in book.yes_bids],
                         [Level(round(lv.price - s, 4), lv.size) for lv in book.no_bids])

    def _size(self, intent: TradeIntent) -> tuple[Optional[TradeIntent], str]:
        # The live bot's own sizing (Desk.size): level x pool bet, trimmed to the window cap
        from desk.runner import Desk

        desk = SimpleNamespace(pool=self.pool, multipliers=self.multipliers, accounts=self.accounts,
                               broker=self.broker, bonus={})
        return Desk.size(desk, intent)

    def run(self, frames=None, progress_every_days: float = 7) -> None:
        frames = frames if frames is not None else self.build_frames()
        order = sorted(self.strategies, key=lambda s: -self.multipliers.get(s.key, 1.0))
        for frame in frames:
            ts, snap = frame.ts, frame.snap
            iso = _dt(ts).isoformat()
            for ticker, yes_value in frame.settles:
                self.broker.settle(ticker, yes_value, ts=iso)
            if snap is None:
                continue
            self.stats["minutes"] += 1
            marks = {m.ticker: m.mid for m in snap.markets.values() if m.mid is not None}
            if (ts // 60) % self.every == 0:
                self.pool.update(self.pool.total_equity(self.accounts, marks), _dt(ts),
                                 self.pool.capital(self.accounts))
                for strat in order:
                    member = strat.key in self.members
                    if member and self.pool.stopped:
                        continue
                    acct = self.accounts[strat.key]
                    view = PoolAccountView(acct, self.broker.free_cash(strat.key)) if member else acct
                    intents = sorted(strat.evaluate(snap, view), key=lambda i: i.expected_edge, reverse=True)
                    for intent in intents[:10]:
                        self.stats["intents"] += 1
                        bet, why = self._size(intent)
                        if not bet:
                            self.stats["skipped"] += 1
                            continue
                        bet = replace(bet, reason=REPLAY_TAG + bet.reason, legs=[
                            replace(leg, limit_price=round(leg.limit_price + self._slip(leg.ticker), 4))
                            for leg in bet.legs])
                        books = {t: self._book(t, ts + 60) for t in bet.tickers}
                        if any(b is None for b in books.values()):
                            self.stats["skipped"] += 1
                            continue
                        result = self.broker.execute(bet, books, self._fees_for(bet.tickers), ts=iso,
                                                     context={"replay": True})
                        self.stats["fills" if result.filled else "skipped"] += 1
            if self.stats["minutes"] % self.config.equity_every_minutes == 0:
                for name, acct in self.accounts.items():
                    self.ledger.record_equity(name, acct.cash, acct.equity(marks), ts=iso)
        iso = _dt(self.data.end).isoformat()
        for name, acct in self.accounts.items():
            self.ledger.record_equity(name, acct.cash, acct.equity({}), ts=iso)


def _bulk(ledger: Ledger, sql: str, rows: list[tuple]) -> None:
    if not rows:
        return
    if ledger.is_postgres:
        from desk.paper.ledger import qualify

        with ledger.db.conn.cursor() as cur:
            cur.executemany(ledger.db.translate(qualify(sql, ledger.schema)), rows)
    else:
        ledger.db.executemany(sql, rows)


def write_season(replay: SeasonReplay, dest: Ledger, season: int) -> dict[str, int]:
    """Copy the replay's records into `dest` under `season` (the caller starts the season)."""
    src = replay.ledger
    fills = [(r["ts"], r["strategy"], r["intent_id"], r["ticker"], r["side"], r["count"], r["price"], r["fee"],
              r["model_prob"], r["expected_edge"], r["reason"], season, r["seen_price"], r["book_depth"],
              r["latency_ms"], r["context"]) for r in src._rows("SELECT * FROM fills ORDER BY id")]
    settles = [(r["ts"], r["strategy"], r["ticker"], r["yes_value"], r["pnl"], season)
               for r in src._rows("SELECT * FROM settlements ORDER BY id")]
    equity = [(r["ts"], r["strategy"], r["cash"], r["equity"], season)
              for r in src._rows("SELECT * FROM equity ORDER BY id")]
    _bulk(dest, "INSERT INTO fills(ts, strategy, intent_id, ticker, side, count, price, fee, model_prob,"
                " expected_edge, reason, season, seen_price, book_depth, latency_ms, context)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", fills)
    _bulk(dest, "INSERT INTO settlements(ts, strategy, ticker, yes_value, pnl, season) VALUES (?, ?, ?, ?, ?, ?)",
          settles)
    _bulk(dest, "INSERT INTO equity(ts, strategy, cash, equity, season) VALUES (?, ?, ?, ?, ?)", equity)
    dest.db.commit()
    return {"fills": len(fills), "settlements": len(settles), "equity": len(equity)}
