"""
Crypto spot prices and volatility from free public APIs.

Kalshi's crypto markets settle on CF Benchmarks' Real-Time Index (BRTI for
bitcoin), a blend of several big exchanges averaged over the final 60 seconds.
That index isn't free, so we approximate it with the median of Kraken's mid
price and Deribit's index price.

Volatility ("how much does the price wiggle?") comes from two places:
  - implied: Deribit's DVOL index, the options market's forecast (annualized %)
  - realized: what the price actually did over the last few hours (Kraken 1m candles)
"""

from __future__ import annotations

import asyncio
import logging
import math
import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

MINUTES_PER_YEAR = 365 * 24 * 60
# A spot price older than this isn't handed to the employees: if both price
# sources fail, betting on a minutes-old bitcoin price is worse than not betting
MAX_QUOTE_AGE_SECONDS = 90.0

KRAKEN_PAIRS = {"BTC": "XBTUSD", "ETH": "ETHUSD", "SOL": "SOLUSD", "XRP": "XRPUSD", "DOGE": "XDGUSD"}
DERIBIT_INDEX = {"BTC": "btc_usd", "ETH": "eth_usd", "SOL": "sol_usd", "XRP": "xrp_usd", "DOGE": "doge_usd"}
DERIBIT_DVOL = {"BTC", "ETH"}


@dataclass
class UnderlyingQuote:
    symbol: str
    spot: float
    implied_vol: Optional[float] = None  # annualized, e.g. 0.37 = 37%
    realized_vol: Optional[float] = None  # annualized
    sources: dict[str, float] = field(default_factory=dict)
    # Log return over the last N minutes, e.g. {15: 0.002} = up 0.2% in 15 min
    momentum: dict[int, float] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def vol(self, implied_weight: float = 0.7) -> Optional[float]:
        """Blend implied and realized vol; fall back to whichever exists."""
        iv, rv = self.implied_vol, self.realized_vol
        if iv and rv:
            return implied_weight * iv + (1 - implied_weight) * rv
        return iv or rv


def realized_vol_from_closes(closes: list[float], minutes_per_bar: float = 1.0) -> Optional[float]:
    """Annualized volatility from a series of close prices."""
    if len(closes) < 20:
        return None
    rets = [math.log(b / a) for a, b in zip(closes, closes[1:]) if a > 0 and b > 0]
    if len(rets) < 10:
        return None
    per_bar = statistics.pstdev(rets)
    return per_bar * math.sqrt(MINUTES_PER_YEAR / minutes_per_bar)


class CryptoFeed:
    def __init__(self, symbols: tuple[str, ...] = ("BTC", "ETH"), timeout: float = 10.0,
                 transport: Optional[httpx.AsyncBaseTransport] = None):
        self.symbols = symbols
        self._http = httpx.AsyncClient(timeout=timeout, transport=transport)
        self.quotes: dict[str, UnderlyingQuote] = {}
        self._vol_refreshed: dict[str, datetime] = {}
        # Recent (time, price) points per symbol, for momentum
        self.history: dict[str, deque] = {s: deque(maxlen=2000) for s in symbols}

    async def close(self) -> None:
        await self._http.aclose()

    async def _json(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        try:
            r = await self._http.get(url, params=params)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Feed request failed %s: %s", url, e)
            return None

    async def kraken_mid(self, symbol: str) -> Optional[float]:
        pair = KRAKEN_PAIRS.get(symbol)
        if not pair:
            return None
        data = await self._json("https://api.kraken.com/0/public/Ticker", {"pair": pair})
        if not data or data.get("error"):
            return None
        tick = next(iter(data["result"].values()))
        return (float(tick["a"][0]) + float(tick["b"][0])) / 2

    async def deribit_index(self, symbol: str) -> Optional[float]:
        name = DERIBIT_INDEX.get(symbol)
        if not name:
            return None
        data = await self._json("https://www.deribit.com/api/v2/public/get_index_price", {"index_name": name})
        return float(data["result"]["index_price"]) if data and "result" in data else None

    async def deribit_dvol(self, symbol: str) -> Optional[float]:
        if symbol not in DERIBIT_DVOL:
            return None
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        data = await self._json(
            "https://www.deribit.com/api/v2/public/get_volatility_index_data",
            {"currency": symbol, "resolution": 3600, "start_timestamp": now_ms - 3 * 3600_000, "end_timestamp": now_ms},
        )
        rows = (data or {}).get("result", {}).get("data") or []
        return float(rows[-1][4]) / 100 if rows else None

    async def kraken_realized_vol(self, symbol: str, minutes: int = 240) -> Optional[float]:
        """Realized vol from 1-minute candles; also seeds price history for momentum."""
        pair = KRAKEN_PAIRS.get(symbol)
        if not pair:
            return None
        data = await self._json("https://api.kraken.com/0/public/OHLC", {"pair": pair, "interval": 1})
        if not data or data.get("error"):
            return None
        rows = next(v for k, v in data["result"].items() if k != "last")[-minutes:]
        self._merge_history(symbol, [(datetime.fromtimestamp(r[0] + 60, timezone.utc), float(r[4])) for r in rows])
        return realized_vol_from_closes([float(r[4]) for r in rows])

    def _merge_history(self, symbol: str, points: list[tuple[datetime, float]]) -> None:
        hist = self.history.setdefault(symbol, deque(maxlen=2000))
        merged = sorted({t: p for t, p in list(hist) + points}.items())
        hist.clear()
        hist.extend(merged[-hist.maxlen:])

    def momentum(self, symbol: str, now: datetime, spot: float,
                 windows: tuple[int, ...] = (5, 15, 60)) -> dict[int, float]:
        out = {}
        hist = self.history.get(symbol) or ()
        for w in windows:
            target = now - timedelta(minutes=w)
            # Latest point at or before the target time, if it's not too stale
            past = [p for t, p in hist if target - timedelta(minutes=max(2, w / 5)) <= t <= target]
            if past and past[-1] > 0:
                out[w] = math.log(spot / past[-1])
        return out

    def fresh_quotes(self, now: Optional[datetime] = None,
                     max_age: float = MAX_QUOTE_AGE_SECONDS) -> dict[str, UnderlyingQuote]:
        now = now or datetime.now(timezone.utc)
        return {s: q for s, q in self.quotes.items()
                if s in self.symbols and (now - q.fetched_at).total_seconds() <= max_age}

    async def refresh(self, vol_every_seconds: float = 300) -> dict[str, UnderlyingQuote]:
        """Update spot every call; vol only every `vol_every_seconds`. Returns only fresh quotes."""

        async def one(sym: str) -> None:
            kraken, deribit = await asyncio.gather(self.kraken_mid(sym), self.deribit_index(sym))
            sources = {k: v for k, v in (("kraken", kraken), ("deribit", deribit)) if v}
            if len(sources) == 1:
                logger.warning("%s price from %s only (the other source failed)", sym, next(iter(sources)))
            if not sources:
                prev = self.quotes.get(sym)
                age = (datetime.now(timezone.utc) - prev.fetched_at).total_seconds() if prev else float("inf")
                if age > MAX_QUOTE_AGE_SECONDS:
                    logger.warning("No %s price from Kraken or Deribit, and the last one is too old: "
                                   "nobody bets on %s this run", sym, sym)
                else:
                    logger.warning("No %s price from Kraken or Deribit; using the one from %.0fs ago", sym, age)
                return
            prev = self.quotes.get(sym)
            quote = UnderlyingQuote(
                symbol=sym,
                spot=statistics.median(sources.values()),
                sources=sources,
                implied_vol=prev.implied_vol if prev else None,
                realized_vol=prev.realized_vol if prev else None,
            )
            last = self._vol_refreshed.get(sym)
            if last is None or (quote.fetched_at - last).total_seconds() >= vol_every_seconds:
                iv, rv = await asyncio.gather(self.deribit_dvol(sym), self.kraken_realized_vol(sym))
                quote.implied_vol = iv or quote.implied_vol
                quote.realized_vol = rv or quote.realized_vol
                self._vol_refreshed[sym] = quote.fetched_at
            self._merge_history(sym, [(quote.fetched_at, quote.spot)])
            quote.momentum = self.momentum(sym, quote.fetched_at, quote.spot)
            self.quotes[sym] = quote

        await asyncio.gather(*(one(s) for s in self.symbols))
        return self.fresh_quotes()


# Which underlying a Kalshi series tracks. Only series with numeric strikes
# on a crypto price belong here.
SERIES_UNDERLYING = {
    "KXBTC15M": "BTC",  # 15-minute up/down (strike = price at the window's start)
    "KXETH15M": "ETH",
    "KXSOL15M": "SOL",
    "KXXRP15M": "XRP",
    "KXDOGE15M": "DOGE",
    "KXBTCD": "BTC",  # hourly above/below
    "KXBTC": "BTC",   # hourly ranges
    "KXETHD": "ETH",
    "KXETH": "ETH",
    "KXSOLD": "SOL",
    "KXSOLE": "SOL",
}


def underlying_for_series(series_ticker: str) -> Optional[str]:
    return SERIES_UNDERLYING.get(series_ticker.upper())
