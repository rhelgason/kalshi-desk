"""
Desk configuration. Defaults live here; override any of them in desk.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DeskConfig:
    env: str = "prod"  # "prod" for real market data, "demo" for Kalshi's sandbox
    db_path: str = "data/desk.db"
    starting_cash: float = 1000.0  # paper dollars per employee

    tick_seconds: float = 15.0
    universe_refresh_seconds: float = 300.0  # broad (non-crypto) market scan
    crypto_refresh_seconds: float = 60.0     # a new 15-minute window opens every 15 minutes
    settle_check_seconds: float = 60.0

    # Crypto markets scanned every tick. The 15-minute "up or down" series settle
    # 96 times a day each, which makes them the fastest source of feedback.
    crypto_series: list[str] = field(default_factory=lambda: [
        "KXBTC15M", "KXETH15M", "KXSOL15M",  # 15-minute up/down
        "KXBTCD", "KXBTC", "KXETHD", "KXETH",  # hourly ladders and ranges
    ])
    crypto_symbols: list[str] = field(default_factory=lambda: ["BTC", "ETH", "SOL"])
    crypto_horizon_hours: float = 6.0

    # Broad scan (for strategies that look beyond crypto)
    broad_scan: bool = True
    broad_max_days: float = 2.0
    broad_max_markets: int = 5000

    # How many of the busiest markets to pull trade tapes for (whale watching)
    trades_watch_markets: int = 12

    # Paper fill realism
    liquidity_share: float = 0.5

    requests_per_second: float = 6.0

    strategies: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None = "desk.yaml") -> "DeskConfig":
        if path is None or not Path(path).exists():
            return cls()
        raw = yaml.safe_load(Path(path).read_text()) or {}
        known = {f.name for f in fields(cls)}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"Unknown keys in {path}: {sorted(unknown)}")
        return cls(**raw)
