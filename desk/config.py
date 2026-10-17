"""
Desk configuration. Defaults live here; override any of them in desk.yaml.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DeskConfig:
    env: str = "prod"  # "prod" for real market data, "demo" for Kalshi's sandbox
    # SQLite file, or a postgres:// URL. The DATABASE_URL environment variable
    # (e.g. from .env) overrides this so the hosted bot writes to Postgres.
    db_path: str = "data/desk.db"
    use_database_url: bool = True  # set false to keep a test run off the shared database
    starting_cash: float = 1000.0  # paper dollars for each control-group employee
    pool_cash: float = 1000.0  # the office pool, split across its members when a season starts

    tick_seconds: float = 15.0
    universe_refresh_seconds: float = 300.0  # broad (non-crypto) market scan
    crypto_refresh_seconds: float = 60.0     # a new 15-minute window opens every 15 minutes
    settle_check_seconds: float = 60.0
    equity_every_seconds: float = 300.0      # equity-curve points
    status_every_seconds: float = 60.0       # dashboard snapshot
    accuracy_every_seconds: float = 600.0

    # Crypto markets scanned every tick. The 15-minute "up or down" series settle
    # 96 times a day each, which makes them the fastest source of feedback.
    crypto_series: list[str] = field(default_factory=lambda: [
        "KXBTC15M", "KXETH15M", "KXSOL15M",  # 15-minute up/down
        "KXBTCD", "KXBTC", "KXETHD", "KXETH",  # hourly ladders and ranges
    ])
    crypto_symbols: list[str] = field(default_factory=lambda: ["BTC", "ETH", "SOL"])
    # Hourly ladders have ~190 markets each and only matter to a few employees;
    # the cloud runner fetches them less often to save processing time.
    slow_series: list[str] = field(default_factory=lambda: ["KXBTCD", "KXBTC", "KXETHD", "KXETH"])
    slow_series_every_seconds: float = 0.0
    crypto_horizon_hours: float = 6.0

    # Broad scan (for strategies that look beyond crypto)
    broad_scan: bool = True
    broad_max_days: float = 2.0
    broad_max_markets: int = 5000

    # How many of the busiest markets to pull trade tapes for (whale watching)
    trades_watch_markets: int = 12
    max_tape_trades: int = 20000  # cap on trades fetched per market when checking resting bids

    # Paper fill realism
    liquidity_share: float = 0.5

    requests_per_second: float = 6.0

    # Real money (desk/live). "paper" never sends an order. "live" sends the office
    # pool's bets to Kalshi, and only if KALSHI_LIVE_TRADING=yes is also set where
    # the bot runs. `live` holds the hard limits (desk/live/guard.py DEFAULT_LIMITS).
    trading: str = "paper"
    live: dict[str, Any] = field(default_factory=dict)

    # Books: the pretend pool (training data, every employee) and the real-money
    # pool run side by side, each with its own roster, levels and records.
    # `schema` keeps a book's tables apart in Postgres; `real_book` (on the
    # pretend book's config) names the real book's config file so the hosted bot
    # runs both every tick. While its `env` is demo, the "real" book is practice.
    book: str = "pretend"
    schema: str = "public"
    real_book: str | None = None
    auto_hr: bool = True  # automatic reviews and promotions; off for real money (the manager decides)

    strategies: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None = "desk.yaml") -> "DeskConfig":
        raw = {}
        if path is not None and Path(path).exists():
            raw = yaml.safe_load(Path(path).read_text()) or {}
        if raw.get("extends"):
            # e.g. desk.real.yaml: everything from desk.yaml, with a few keys changed.
            # Nested settings merge one level down, so `strategies: {dart_monkey: {enabled: false}}`
            # switches one employee off without dropping everyone else's settings.
            base_path = Path(path).parent / raw.pop("extends")
            base = yaml.safe_load(base_path.read_text()) or {}
            raw = {**base, **{k: _merge(base.get(k), v) for k, v in raw.items()}}
        known = {f.name for f in fields(cls)}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"Unknown keys in {path}: {sorted(unknown)}")
        cfg = cls(**raw)
        if cfg.book not in ("pretend", "real"):
            raise ValueError(f"book must be pretend or real, not {cfg.book!r}")
        if cfg.trading not in ("paper", "live"):
            raise ValueError(f"trading must be paper or live, not {cfg.trading!r}")
        if cfg.use_database_url and os.getenv("DATABASE_URL"):
            cfg.db_path = os.environ["DATABASE_URL"]
        return cfg


def _merge(base: Any, over: Any) -> Any:
    """`over` on top of `base`; for a dict of dicts (strategies), each inner dict merges too."""
    if not (isinstance(base, dict) and isinstance(over, dict)):
        return over
    out = dict(base)
    for k, v in over.items():
        out[k] = {**base[k], **v} if isinstance(base.get(k), dict) and isinstance(v, dict) else v
    return out
