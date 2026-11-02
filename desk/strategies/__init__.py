from desk.strategies.base import AccountView, Leg, Persona, Snapshot, Strategy, TradeIntent
from desk.strategies.arbitrage import CoverArb, PartitionArb
from desk.strategies.fair_value import CryptoFairValue, MomentumMo, RubberBandRandy, Sniper, VegaVinny
from desk.strategies.bitcoin import (
    BinanceBelle, BitcoinBea, BreakoutBetty, BreakoutBonnie, ClosingTimeCoco, DogecoinDot, EarlyBirdEdie, EarlyBirdEllie, EtherEsther,
    HypeHannah, NearlyNadia, NickelNora, RippleRita, SilverMedalSid, SolarSally, SteadySadie, ZcashZoe,
)
from desk.strategies.other_markets import FinalWhistleFiona, WeatherWendy
from desk.strategies.behavioral import (
    DartMonkey, FrontRunnerFran, LongshotFade, LongshotLenny, NickelNick, SpreadSam, SteadyStella, WhaleWatcherWalt,
)

# Everyone on payroll. Since Season 5 the desk trades 15-minute coin up/down markets
# (bitcoin, ether, solana; XRP and doge on Training), and the staff is the heavy-favorite
# family that a 10-month backtest found an edge in (research/stella_backtest).
STAFF: tuple[type[Strategy], ...] = (
    SteadyStella,  # heavy favorites mid-window, paying the ask (Training's yardstick for the twins)
    SteadySadie,  # Stella's patient twin: the real book's only employee 2026-10-24 to 10-31; now keeps the pool's money
    BitcoinBea, EtherEsther, SolarSally, RippleRita, DogecoinDot,  # Sadie's rules, one coin each (2026-10-31)
    HypeHannah, BinanceBelle, NearlyNadia, ZcashZoe,  # and four thinner coins, Training only (2026-11-02)
    ClosingTimeCoco, SilverMedalSid,  # resting bids late in the window / on the next tier of favorites
    WeatherWendy, FinalWhistleFiona,  # Training only: weather mornings and finished games (research/other_markets)
    LongshotLenny, DartMonkey,  # yardsticks: everyone should beat these
)
# Retired. Rick, Sue, Vinny, Fran, Sam, Walt need strike ladders, sports or the
# trade tape; the Professor, Mo and Randy's pricing model showed no edge on
# 15-minute bitcoin (Mo and Randy bet once in 45 days). The Sniper, Nick, the Wet
# Blanket, Wipeout, Edie and the twins Nora, Ellie and Bonnie retired 2026-10-24: no
# rule of theirs held up in the Oct 23 scan, and they lost the real book $13 of $100.
# Kept so old seasons and tests still make sense.
ALUMNI: tuple[type[Strategy], ...] = (
    CoverArb, PartitionArb, VegaVinny, FrontRunnerFran, SpreadSam, WhaleWatcherWalt,
    CryptoFairValue, MomentumMo, RubberBandRandy,
    Sniper, NickelNick, LongshotFade, BreakoutBetty, EarlyBirdEdie, NickelNora, EarlyBirdEllie, BreakoutBonnie,
)
REGISTRY: dict[str, type[Strategy]] = {cls.key: cls for cls in STAFF}
EVERYONE: dict[str, type[Strategy]] = {cls.key: cls for cls in STAFF + ALUMNI}


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


def build_strategies(config: dict[str, dict], registry: dict[str, type[Strategy]] = REGISTRY) -> list[Strategy]:
    """
    Instantiate strategies from config: {key: {"enabled": bool, **params}}.
    Keys missing from config are created with defaults.
    """
    unknown = set(config) - set(registry)
    if unknown:
        raise ValueError(f"Unknown strategies in config: {sorted(unknown)}")
    out = []
    for key, cls in registry.items():
        params = dict(config.get(key) or {})
        if not params.pop("enabled", True):
            continue
        out.append(cls(**params))
    return out


__all__ = [
    "AccountView", "Leg", "Persona", "Snapshot", "Strategy", "TradeIntent",
    "BitcoinBea", "EtherEsther", "SolarSally", "RippleRita", "DogecoinDot", "HypeHannah", "BinanceBelle", "NearlyNadia",
    "ZcashZoe",
    "CoverArb", "PartitionArb", "CryptoFairValue", "VegaVinny", "Sniper", "MomentumMo", "RubberBandRandy",
    "LongshotFade", "LongshotLenny", "NickelNick", "FrontRunnerFran", "SpreadSam", "WhaleWatcherWalt",
    "DartMonkey", "SteadyStella", "BreakoutBetty", "EarlyBirdEdie", "NickelNora", "EarlyBirdEllie", "BreakoutBonnie",
    "SteadySadie", "ClosingTimeCoco", "WeatherWendy", "FinalWhistleFiona", "SilverMedalSid", "STAFF", "ALUMNI", "REGISTRY", "EVERYONE", "build_strategies", "strategy_params",
]
