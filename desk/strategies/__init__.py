from desk.strategies.base import AccountView, Leg, Persona, Snapshot, Strategy, TradeIntent
from desk.strategies.arbitrage import CoverArb, PartitionArb
from desk.strategies.fair_value import CryptoFairValue, MomentumMo, RubberBandRandy, Sniper, VegaVinny
from desk.strategies.behavioral import (
    DartMonkey, LongshotFade, LongshotLenny, NickelNick, WhaleWatcherWalt,
)

# Everyone on payroll, in roughly "most to least confident" order
STAFF: tuple[type[Strategy], ...] = (
    CoverArb, PartitionArb,
    CryptoFairValue, VegaVinny, Sniper, MomentumMo, RubberBandRandy,
    LongshotFade, LongshotLenny, NickelNick, WhaleWatcherWalt,
    DartMonkey,
)
REGISTRY: dict[str, type[Strategy]] = {cls.key: cls for cls in STAFF}


def build_strategies(config: dict[str, dict]) -> list[Strategy]:
    """
    Instantiate strategies from config: {key: {"enabled": bool, **params}}.
    Keys missing from config are created with defaults.
    """
    unknown = set(config) - set(REGISTRY)
    if unknown:
        raise ValueError(f"Unknown strategies in config: {sorted(unknown)}")
    out = []
    for key, cls in REGISTRY.items():
        params = dict(config.get(key) or {})
        if not params.pop("enabled", True):
            continue
        out.append(cls(**params))
    return out


__all__ = [
    "AccountView", "Leg", "Persona", "Snapshot", "Strategy", "TradeIntent",
    "CoverArb", "PartitionArb", "CryptoFairValue", "VegaVinny", "Sniper", "MomentumMo", "RubberBandRandy",
    "LongshotFade", "LongshotLenny", "NickelNick", "WhaleWatcherWalt", "DartMonkey",
    "STAFF", "REGISTRY", "build_strategies",
]
