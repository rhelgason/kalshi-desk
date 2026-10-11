"""
Historical data for backtests, downloaded once and cached under data/cache/.

  Kalshi      settled markets (strike, open/close, result) and 1-minute
              candlesticks of the best YES bid/ask
  Bitstamp    1-minute BTC/ETH/SOL prices (Bitstamp is one of the exchanges in
              CF Benchmarks' settlement index)
  Deribit     hourly DVOL implied volatility (BTC and ETH only)

Kalshi moves markets older than its "historical cutoff" (about two months)
to separate archive endpoints; we only use the live window for now.
"""

from __future__ import annotations

import asyncio
import bisect
import gzip
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx

from desk.feeds.crypto import MINUTES_PER_YEAR, underlying_for_series
from desk.kalshi.client import KalshiClient
from desk.kalshi.models import Market

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache")
BITSTAMP_PAIRS = {"BTC": "btcusd", "ETH": "ethusd", "SOL": "solusd"}


def _read_cache(name: str):
    path = CACHE_DIR / name
    if path.exists():
        with gzip.open(path, "rt") as f:
            return json.load(f)
    return None


def _write_cache(name: str, data) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with gzip.open(CACHE_DIR / name, "wt") as f:
        json.dump(data, f)


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())


# ---------------------------------------------------------------------------
# Containers
# ---------------------------------------------------------------------------


@dataclass
class HistoricalMarket:
    market: Market  # static fields: strike, open/close time, result
    # minute end timestamp -> (yes_bid, yes_ask, volume)
    candles: dict[int, tuple[float, float, float]] = field(default_factory=dict)

    @property
    def yes_value(self) -> Optional[float]:
        if self.market.result == "yes":
            return 1.0
        if self.market.result == "no":
            return 0.0
        return self.market.settlement_value

    def quote_at(self, ts: int) -> Optional[tuple[float, float, float]]:
        """Latest candle at or before ts (quotes persist between updates)."""
        if ts in self.candles:
            return self.candles[ts]
        keys = self._keys()
        i = bisect.bisect_right(keys, ts) - 1
        return self.candles[keys[i]] if i >= 0 else None

    def _keys(self) -> list[int]:
        if not hasattr(self, "_sorted") or len(self._sorted) != len(self.candles):
            self._sorted = sorted(self.candles)
        return self._sorted


class SpotSeries:
    """
    1-minute closes for one coin, with O(1) lookups of price, realized vol
    (rolling window), and momentum at any minute.
    """

    def __init__(self, closes: dict[int, float], vol_window: int = 240):
        # closes keyed by the minute's *end* timestamp
        self.start = min(closes)
        self.end = max(closes)
        n = (self.end - self.start) // 60 + 1
        prices: list[float] = []
        last = closes[self.start]
        for i in range(n):
            last = closes.get(self.start + 60 * i, last)  # forward-fill gaps
            prices.append(last)
        self.prices = prices
        self.vol_window = vol_window
        # Prefix sums of log returns and their squares for fast rolling stdev
        self._s1 = [0.0]
        self._s2 = [0.0]
        for a, b in zip(prices, prices[1:]):
            r = math.log(b / a) if a > 0 and b > 0 else 0.0
            self._s1.append(self._s1[-1] + r)
            self._s2.append(self._s2[-1] + r * r)

    def _idx(self, ts: int) -> Optional[int]:
        if ts < self.start:
            return None
        return min((ts - self.start) // 60, len(self.prices) - 1)

    def price(self, ts: int) -> Optional[float]:
        i = self._idx(ts)
        return self.prices[i] if i is not None else None

    def realized_vol(self, ts: int) -> Optional[float]:
        i = self._idx(ts)
        if i is None or i < 20:
            return None
        lo = max(0, i - self.vol_window)
        n = i - lo
        mean = (self._s1[i] - self._s1[lo]) / n
        var = (self._s2[i] - self._s2[lo]) / n - mean * mean
        return math.sqrt(max(var, 0.0) * MINUTES_PER_YEAR)

    def momentum(self, ts: int, windows: tuple[int, ...] = (5, 15, 60)) -> dict[int, float]:
        i = self._idx(ts)
        out = {}
        if i is None:
            return out
        for w in windows:
            if i - w >= 0 and self.prices[i - w] > 0:
                out[w] = math.log(self.prices[i] / self.prices[i - w])
        return out


@dataclass
class BacktestData:
    markets: list[HistoricalMarket]
    spot: dict[str, SpotSeries]
    dvol: dict[str, list[tuple[int, float]]]  # symbol -> sorted (ts, annualized vol)
    start: int
    end: int

    def implied_vol(self, symbol: str, ts: int) -> Optional[float]:
        rows = self.dvol.get(symbol) or []
        i = bisect.bisect_right(rows, (ts, math.inf)) - 1
        return rows[i][1] if i >= 0 else None


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------


async def fetch_settled_markets(client: KalshiClient, series: str, start: datetime,
                                end: datetime) -> list[dict]:
    """Settled markets in a series that closed within [start, end), newest first."""
    out, cursor = [], None
    while True:
        data = await client.request("GET", "/markets", params={
            "series_ticker": series, "status": "settled", "limit": 1000, "cursor": cursor,
        })
        page = data.get("markets") or []
        for m in page:
            close = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00"))
            if start <= close < end:
                out.append(m)
        cursor = data.get("cursor")
        oldest = page[-1]["close_time"] if page else None
        if not cursor or not page or datetime.fromisoformat(oldest.replace("Z", "+00:00")) < start:
            return out


def _candle_tuple(c: dict) -> Optional[tuple[float, float, float]]:
    bid = (c.get("yes_bid") or {}).get("close_dollars")
    ask = (c.get("yes_ask") or {}).get("close_dollars")
    if bid is None or ask is None:
        return None
    return float(bid), float(ask), float(c.get("volume_fp") or 0)


def _open_close(m: dict) -> tuple[int, int]:
    return (_ts(datetime.fromisoformat(m["open_time"].replace("Z", "+00:00"))),
            _ts(datetime.fromisoformat(m["close_time"].replace("Z", "+00:00"))))


async def fetch_candles(client: KalshiClient, markets: list[dict],
                        max_points: int = 9500) -> dict[str, dict[int, list]]:
    """
    1-minute candles for each market. Kalshi caps a batch request at 10,000
    candles (markets x minutes in the shared time range), so we grow each
    batch of consecutive markets until it would cross that.
    """
    out: dict[str, dict[int, list]] = {}
    ordered = sorted(markets, key=lambda m: m["close_time"])
    i = 0
    while i < len(ordered):
        start, end = _open_close(ordered[i])
        j = i + 1
        while j < len(ordered) and j - i < 100:
            o, c = _open_close(ordered[j])
            s2, e2 = min(start, o), max(end, c)
            if (j - i + 1) * ((e2 - s2) // 60 + 2) > max_points:
                break
            start, end, j = s2, e2, j + 1
        chunk = ordered[i:j]
        raw = await client.get_candlesticks([m["ticker"] for m in chunk], start - 60, end)
        for ticker, candles in raw.items():
            out[ticker] = {}
            for c in candles:
                tup = _candle_tuple(c)
                if tup:
                    out[ticker][int(c["end_period_ts"])] = list(tup)
        i = j
        if i % 200 < len(chunk) or i == len(ordered):
            logger.info("Candles: %d/%d markets", i, len(ordered))
    return out


async def fetch_bitstamp(http: httpx.AsyncClient, symbol: str, start: int, end: int) -> dict[int, float]:
    """1-minute closes keyed by minute end timestamp."""
    pair = BITSTAMP_PAIRS[symbol]
    closes: dict[int, float] = {}
    t = start
    while t < end:
        r = await http.get(f"https://www.bitstamp.net/api/v2/ohlc/{pair}/",
                           params={"step": 60, "limit": 1000, "start": t})
        r.raise_for_status()
        rows = r.json()["data"]["ohlc"]
        if not rows:
            break
        for row in rows:
            closes[int(row["timestamp"]) + 60] = float(row["close"])
        last = int(rows[-1]["timestamp"])
        if last + 60 <= t:
            break
        t = last + 60
        await asyncio.sleep(0.2)
    return closes


async def fetch_dvol(http: httpx.AsyncClient, symbol: str, start: int, end: int) -> list[tuple[int, float]]:
    rows: list[tuple[int, float]] = []
    t_end = end * 1000
    while True:
        r = await http.get("https://www.deribit.com/api/v2/public/get_volatility_index_data", params={
            "currency": symbol, "resolution": 3600, "start_timestamp": start * 1000, "end_timestamp": t_end,
        })
        r.raise_for_status()
        res = r.json()["result"]
        rows.extend((int(d[0] // 1000), float(d[4]) / 100) for d in res["data"])
        cont = res.get("continuation")
        if not cont or cont <= start * 1000:
            break
        t_end = cont
        await asyncio.sleep(0.2)
    return sorted(set(rows))


async def load_backtest_data(client: KalshiClient, series: list[str], days: float,
                             end: Optional[datetime] = None, use_cache: bool = True) -> BacktestData:
    end = end or datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(days=days)
    tag = f"{start:%Y%m%d%H%M}-{end:%Y%m%d%H%M}"

    markets: list[HistoricalMarket] = []
    symbols = set()
    for s in series:
        sym = underlying_for_series(s)
        if sym:
            symbols.add(sym)
        name = f"kalshi_{s}_{tag}.json.gz"
        cached = _read_cache(name) if use_cache else None
        if cached is None:
            logger.info("Downloading settled %s markets for %g days...", s, days)
            raw = await fetch_settled_markets(client, s, start, end)
            candles = await fetch_candles(client, raw)
            cached = {"markets": raw, "candles": candles}
            _write_cache(name, cached)
        for m in cached["markets"]:
            hm = HistoricalMarket(Market.from_api(m, series_ticker=s))
            hm.candles = {int(k): tuple(v) for k, v in cached["candles"].get(m["ticker"], {}).items()}
            markets.append(hm)

    spot: dict[str, SpotSeries] = {}
    dvol: dict[str, list[tuple[int, float]]] = {}
    # Extra history before the start so realized vol has a warm-up window
    s_ts, e_ts = _ts(start) - 6 * 3600, _ts(end) + 3600
    async with httpx.AsyncClient(timeout=30) as http:
        for sym in sorted(symbols):
            name = f"spot_{sym}_{tag}.json.gz"
            cached = _read_cache(name) if use_cache else None
            if cached is None:
                logger.info("Downloading %s 1-minute prices from Bitstamp...", sym)
                closes = await fetch_bitstamp(http, sym, s_ts, e_ts)
                vols = await fetch_dvol(http, sym, s_ts, e_ts) if sym in ("BTC", "ETH") else []
                cached = {"closes": closes, "dvol": vols}
                _write_cache(name, cached)
            closes = {int(k): v for k, v in cached["closes"].items()}
            if closes:
                spot[sym] = SpotSeries(closes)
            dvol[sym] = [tuple(r) for r in cached["dvol"]]

    logger.info("Backtest data: %d markets, %s", len(markets), {k: len(v.prices) for k, v in spot.items()})
    return BacktestData(markets=markets, spot=spot, dvol=dvol, start=_ts(start), end=_ts(end))
