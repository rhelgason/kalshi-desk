from desk.strategies.base import AccountView, Leg, Persona, Snapshot, Strategy, TradeIntent
from desk.strategies.arbitrage import CoverArb, PartitionArb
from desk.strategies.fair_value import CryptoFairValue, MomentumMo, RubberBandRandy, Sniper, VegaVinny
from desk.strategies.behavioral import (
    DartMonkey, FrontRunnerFran, LongshotFade, LongshotLenny, NickelNick, SpreadSam, WhaleWatcherWalt,
)

# Everyone on payroll, in roughly "most to least confident" order
STAFF: tuple[type[Strategy], ...] = (
    CoverArb, PartitionArb,
    CryptoFairValue, VegaVinny, Sniper, MomentumMo, RubberBandRandy,
    LongshotFade, LongshotLenny, NickelNick, FrontRunnerFran, SpreadSam, WhaleWatcherWalt,
    DartMonkey,
)
REGISTRY: dict[str, type[Strategy]] = {cls.key: cls for cls in STAFF}


def strategy_params(strat: Strategy) -> dict:
    """Current settings of a strategy instance, from its constructor arguments."""
    import inspect

    names: list[str] = []
    for klass in type(strat).__mro__:
        init = klass.__dict__.get("__init__")
        if not init:
            continue
        for p in inspect.signature(init).parameters.values():
            if p.name != "self" and p.kind not in (p.VAR_KEYWORD, p.VAR_POSITIONAL) and p.name not in names:
                names.append(p.name)
    out = {}
    for n in names:
        v = getattr(strat, n, None)
        if isinstance(v, (int, float, str, bool)) or v is None:
            out[n] = v
        elif isinstance(v, (list, tuple)) and all(isinstance(x, (int, float, str)) for x in v):
            out[n] = list(v)
    return out


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
    "LongshotFade", "LongshotLenny", "NickelNick", "FrontRunnerFran", "SpreadSam", "WhaleWatcherWalt",
    "DartMonkey",
    "STAFF", "REGISTRY", "build_strategies", "strategy_params",
]
