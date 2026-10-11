"""
Permanent history store for backtests and autotuning, kept in the database.

Downloading months of 1-minute history takes hours (archived Kalshi markets
must be fetched one at a time), so we only ever download what's missing:

  sync_recent      settled markets still in Kalshi's live API (~2 months), 100 at a time
  backfill_archive older markets from Kalshi's archive, newest first, within a time budget
  sync_prices      1-minute coin prices (Bitstamp) and hourly implied vol (Deribit), per day

The background job runs these every few hours, so the store keeps growing and
the autotuner always has the latest history.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

import httpx

from desk.backtest.data import (BacktestData, HistoricalMarket, SpotSeries, _candle_tuple, fetch_bitstamp,
                                fetch_candles, fetch_dvol, fetch_settled_markets)
from desk.feeds.crypto import underlying_for_series
from desk.kalshi.client import KalshiAPIError, KalshiClient
from desk.kalshi.models import Market
from desk.paper.ledger import Ledger

logger = logging.getLogger(__name__)

MARKET_FIELDS = ("ticker", "event_ticker", "strike_type", "floor_strike", "cap_strike", "open_time",
                 "close_time", "result", "settlement_value_dollars", "expiration_value", "status")


def _ts(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def _day(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Markets
# ---------------------------------------------------------------------------


def known_tickers(ledger: Ledger, series: str) -> set[str]:
    return {r["ticker"] for r in ledger._rows("SELECT ticker FROM market_history WHERE series = ?", (series,))}


def save_markets(ledger: Ledger, series: str, markets: list[dict], candles: dict[str, dict]) -> int:
    saved = 0
    for m in markets:
        c = candles.get(m["ticker"])
        if not c:
            continue
        data = {"m": {k: m.get(k) for k in MARKET_FIELDS},
                "c": [[int(t), *v] for t, v in sorted(c.items(), key=lambda kv: int(kv[0]))]}
        ledger.db.execute(
            "INSERT INTO market_history(ticker, series, close_ts, data) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(ticker) DO NOTHING",
            (m["ticker"], series, _ts(m["close_time"]), json.dumps(data, separators=(",", ":"))),
        )
        saved += 1
    ledger.db.commit()
    return saved


async def sync_recent(client: KalshiClient, ledger: Ledger, series: Iterable[str], days: float) -> dict[str, int]:
    """Add settled markets from the live API (last `days`) that aren't stored yet."""
    end = datetime.now(timezone.utc)
    out = {}
    for s in series:
        have = known_tickers(ledger, s)
        markets = [m for m in await fetch_settled_markets(client, s, end - timedelta(days=days), end)
                   if m["ticker"] not in have and m.get("result") in ("yes", "no")]
        saved = 0
        for i in range(0, len(markets), 500):
            chunk = markets[i:i + 500]
            saved += save_markets(ledger, s, chunk, await fetch_candles(client, chunk))
        out[s] = saved
        logger.info("History %s: +%d recent markets", s, saved)
    return out


async def backfill_archive(client: KalshiClient, ledger: Ledger, series: Iterable[str],
                           seconds: float, max_age_days: float = 365) -> dict[str, int]:
    """
    Fill in archived markets, newest first, until `seconds` have passed.
    Archived candles must be fetched one market at a time, so this is the slow part.
    """
    series = list(series)
    end_all = time.monotonic() + seconds
    oldest_allowed = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    out = {s: 0 for s in series}
    for i, s in enumerate(series):
        # Split the remaining time evenly so every series makes progress each run
        deadline = time.monotonic() + (end_all - time.monotonic()) / (len(series) - i)
        have = known_tickers(ledger, s)
        cursor = None
        while time.monotonic() < deadline:
            data = await client.request("GET", "/historical/markets",
                                        params={"series_ticker": s, "limit": 1000, "cursor": cursor})
            page = data.get("markets") or []
            todo = [m for m in page if m["ticker"] not in have and m.get("result") in ("yes", "no")
                    and datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")) >= oldest_allowed]
            batch_m, batch_c = [], {}
            for m in todo:
                if time.monotonic() >= deadline:
                    break
                try:
                    raw = await client.request(
                        "GET", f"/historical/markets/{m['ticker']}/candlesticks",
                        params={"start_ts": _ts(m["open_time"]) - 60, "end_ts": _ts(m["close_time"]),
                                "period_interval": 1})
                except KalshiAPIError as e:
                    logger.warning("Archive candles failed for %s: %s", m["ticker"], e)
                    continue
                c = {}
                for cs in raw.get("candlesticks") or []:
                    tup = _candle_tuple(cs)
                    if tup:
                        c[int(cs["end_period_ts"])] = list(tup)
                batch_m.append(m)
                batch_c[m["ticker"]] = c
                if len(batch_m) >= 50:
                    out[s] += save_markets(ledger, s, batch_m, batch_c)
                    batch_m, batch_c = [], {}
            if batch_m:
                out[s] += save_markets(ledger, s, batch_m, batch_c)
            cursor = data.get("cursor")
            oldest = page[-1]["close_time"] if page else None
            if not cursor or not page or datetime.fromisoformat(oldest.replace("Z", "+00:00")) < oldest_allowed:
                break
        logger.info("History %s: +%d archived markets", s, out[s])
    return out


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------


def _stored_days(ledger: Ledger, symbol: str) -> set[str]:
    return {r["day"] for r in ledger._rows("SELECT day FROM price_history WHERE symbol = ?", (symbol,))}


def _save_day(ledger: Ledger, symbol: str, day: str, data) -> None:
    ledger._write(
        "INSERT INTO price_history(symbol, day, data) VALUES (?, ?, ?)"
        " ON CONFLICT(symbol, day) DO UPDATE SET data = excluded.data",
        (symbol, day, json.dumps(data, separators=(",", ":"))),
    )


async def sync_prices(ledger: Ledger, symbols: Iterable[str], start: datetime, end: datetime) -> int:
    """Store any missing days of 1-minute prices (and DVOL for BTC/ETH). Today is always refreshed."""
    today = _day(int(time.time()))
    saved = 0
    async with httpx.AsyncClient(timeout=30) as http:
        for sym in symbols:
            have = _stored_days(ledger, sym)
            have_vol = _stored_days(ledger, f"DVOL:{sym}")
            day = start.replace(hour=0, minute=0, second=0, microsecond=0)
            while day <= end:
                d = day.strftime("%Y-%m-%d")
                s_ts, e_ts = int(day.timestamp()), int((day + timedelta(days=1)).timestamp())
                if d not in have or d == today:
                    closes = await fetch_bitstamp(http, sym, s_ts, e_ts)
                    if closes:
                        _save_day(ledger, sym, d, {str(k): v for k, v in closes.items() if s_ts < k <= e_ts})
                        saved += 1
                if sym in ("BTC", "ETH") and (d not in have_vol or d == today):
                    rows = await fetch_dvol(http, sym, s_ts, e_ts)
                    _save_day(ledger, f"DVOL:{sym}", d, rows)
                day += timedelta(days=1)
                await asyncio.sleep(0.1)
    return saved


# ---------------------------------------------------------------------------
# Loading for backtests
# ---------------------------------------------------------------------------


def load_from_store(ledger: Ledger, series: list[str], start: datetime, end: datetime) -> BacktestData:
    s_ts, e_ts = int(start.timestamp()), int(end.timestamp())
    markets: list[HistoricalMarket] = []
    symbols = set()
    for s in series:
        sym = underlying_for_series(s)
        if sym:
            symbols.add(sym)
        for r in ledger._rows("SELECT data FROM market_history WHERE series = ? AND close_ts > ? AND close_ts <= ?",
                              (s, s_ts, e_ts)):
            d = json.loads(r["data"])
            hm = HistoricalMarket(Market.from_api(d["m"], series_ticker=s))
            hm.candles = {int(t): (b, a, v) for t, b, a, v in d["c"]}
            markets.append(hm)

    first_day, last_day = _day(s_ts - 86400), _day(e_ts)
    spot, dvol = {}, {}
    for sym in sorted(symbols):
        closes: dict[int, float] = {}
        for r in ledger._rows("SELECT data FROM price_history WHERE symbol = ? AND day >= ? AND day <= ?",
                              (sym, first_day, last_day)):
            closes.update({int(k): v for k, v in json.loads(r["data"]).items()})
        if closes:
            spot[sym] = SpotSeries(closes)
        rows: list[tuple[int, float]] = []
        for r in ledger._rows("SELECT data FROM price_history WHERE symbol = ? AND day >= ? AND day <= ?",
                              (f"DVOL:{sym}", first_day, last_day)):
            rows.extend(tuple(x) for x in json.loads(r["data"]))
        dvol[sym] = sorted(set(rows))
    logger.info("Loaded %d stored markets, %s", len(markets), {k: len(v.prices) for k, v in spot.items()})
    return BacktestData(markets=markets, spot=spot, dvol=dvol, start=s_ts, end=e_ts)


def coverage(ledger: Ledger) -> list[dict]:
    """How much history is stored, per series (for the dashboard)."""
    return [dict(r) for r in ledger._rows(
        "SELECT series, COUNT(*) AS markets, MIN(close_ts) AS oldest, MAX(close_ts) AS newest"
        " FROM market_history GROUP BY series ORDER BY series")]
