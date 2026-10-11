"""
Fill reality check: how much should we trust each employee's paper fills?

Every live paper fill records what the employee saw and what the order book
really offered. From that, per employee:

  slippage     average cents paid above the price the employee saw (more = worse)
  depth share  how much of the contracts on offer a fill took. Taking a big
               share is unrealistic: faster traders would grab some of it first
  depth        typical contracts available at the price (median), which also
               calibrates how much the backtests assume they can buy
  latency      seconds between seeing the price and filling

Maker fills (Spread Sam) are counted separately: they depend on our assumption
about where we'd stand in the queue, so they're the least certain of all.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass
from typing import Optional

from desk.paper.ledger import Ledger


@dataclass
class Realism:
    strategy: str
    taker_fills: int
    maker_fills: int
    slippage: Optional[float]  # dollars per contract, + = paid more than seen
    depth_share: Optional[float]  # average fraction of on-offer contracts we took
    median_depth: Optional[float]
    latency_s: Optional[float]
    verdict: str
    verdict_key: str

    def to_dict(self) -> dict:
        return asdict(self)


def _verdict(taker: int, maker: int, slippage: Optional[float], share: Optional[float]) -> tuple[str, str]:
    if taker + maker == 0:
        return "none", "No trades yet"
    if maker > taker:
        return "maker", "Depends on queue-position guesses: treat results with caution"
    if share is not None and share > 0.4:
        return "too_big", "Takes a big share of what's on offer: real fills would be smaller"
    if slippage is not None and slippage > 0.01:
        return "slippy", "Prices often move before filling: real results likely worse"
    return "realistic", "Fills look realistic"


def realism_from_fills(strategy: str, fills: list[dict]) -> Realism:
    # Only fills recorded since the reality check existed carry measurements
    fills = [f for f in fills if f.get("seen_price") is not None]
    taker = [f for f in fills if not str(f.get("reason") or "").startswith("maker fill")]
    maker = len(fills) - len(taker)
    measured = taker
    slip = statistics.fmean(f["price"] - f["seen_price"] for f in measured) if measured else None
    with_depth = [f for f in measured if f.get("book_depth")]
    share = statistics.fmean(min(1.0, f["count"] / f["book_depth"]) for f in with_depth) if with_depth else None
    depth = statistics.median(f["book_depth"] for f in with_depth) if with_depth else None
    lat = [f["latency_ms"] for f in measured if f.get("latency_ms") is not None]
    key, text = _verdict(len(taker), maker, slip, share)
    return Realism(strategy, len(taker), maker, slip, share, depth, statistics.fmean(lat) / 1000 if lat else None,
                   text, key)


def realism_report(ledger: Ledger, strategies: list[str]) -> list[Realism]:
    fills = ledger.fills()
    return [realism_from_fills(s, [f for f in fills if f["strategy"] == s]) for s in strategies]


def realism_report_sql(ledger: Ledger, strategies: list[str]) -> list[Realism]:
    # Only fills recorded since the reality check existed carry measurements
    # (seen_price). Note LEAST() ignores NULLs in Postgres, so filter explicitly.
    taker = "(reason NOT LIKE 'maker fill%' OR reason IS NULL)"
    rows = ledger._rows(
        "SELECT strategy,"
        f" count(*) FILTER (WHERE {taker}) AS taker,"
        " count(*) FILTER (WHERE reason LIKE 'maker fill%') AS maker,"
        f" avg(price - seen_price) FILTER (WHERE {taker}) AS slip,"
        f" avg(LEAST(1.0, count / book_depth)) FILTER (WHERE {taker} AND book_depth > 0) AS share,"
        f" percentile_cont(0.5) WITHIN GROUP (ORDER BY book_depth) FILTER (WHERE {taker} AND book_depth > 0) AS depth,"
        f" avg(latency_ms) FILTER (WHERE {taker}) AS lat"
        " FROM fills WHERE season = ? AND seen_price IS NOT NULL GROUP BY strategy",
        (ledger.season,),
    )
    out = []
    for r in rows:
        if r["strategy"] not in strategies:
            continue
        f = lambda v: float(v) if v is not None else None  # noqa: E731
        slip, share = f(r["slip"]), f(r["share"])
        key, text = _verdict(int(r["taker"]), int(r["maker"]), slip, share)
        lat = f(r["lat"])
        out.append(Realism(r["strategy"], int(r["taker"]), int(r["maker"]), slip, share, f(r["depth"]),
                           lat / 1000 if lat is not None else None, text, key))
    return out


def measured_depth(ledger: Ledger, series_prefixes: tuple[str, ...] = ("KXBTC15M", "KXETH15M", "KXSOL15M"),
                   days: int = 14) -> tuple[Optional[float], int]:
    """Median contracts on offer at our price in live 15-minute crypto fills (for calibrating backtests)."""
    from datetime import datetime, timedelta, timezone

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    like = " OR ".join("ticker LIKE ?" for _ in series_prefixes)
    rows = ledger._rows(
        f"SELECT book_depth FROM fills WHERE ts >= ? AND book_depth > 0 AND ({like})"
        " AND (reason NOT LIKE 'maker fill%' OR reason IS NULL)",
        (since, *[p + "-%" for p in series_prefixes]),
    )
    depths = [float(r["book_depth"]) for r in rows]
    return (statistics.median(depths) if depths else None), len(depths)
