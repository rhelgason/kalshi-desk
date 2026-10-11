"""
Accuracy report: are an employee's probabilities any good?

For every settled bet we know three things: the price paid (the market's
opinion), the employee's own probability (if it states one), and what
actually happened. From that:

  Calibration   Group bets by forecast (0-10%, 10-20%, ...). In a well
                calibrated forecaster, the "70%" group wins about 70% of the
                time.
  Brier score   Average of (forecast - outcome)^2. Lower is better.
  Skill         1 - Brier(employee) / Brier(market price). Above 0 means the
                employee's probabilities beat the price they paid, which is the
                only way a model-based strategy makes money long-term. Below 0
                means the market knew better.
  Edge          Expected = what the employee thought each contract was worth
                minus what it paid (after fees). Realized = what it actually
                got back minus what it paid. If realized edge is far below
                expected edge over many bets, the model is overconfident.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from desk.paper.ledger import Ledger


@dataclass
class Bet:
    strategy: str
    ticker: str
    side: str
    price: float  # per contract, excluding fees
    fee_per_contract: float
    count: float
    model_prob: Optional[float]
    outcome: float  # 1.0 if this side won, 0.0 if it lost


@dataclass
class CalibrationBin:
    lo: float
    hi: float
    n: int
    avg_forecast: float
    hit_rate: float


@dataclass
class AccuracySummary:
    strategy: str
    n: int
    hit_rate: float
    avg_price: float
    brier_market: float
    brier_model: Optional[float]
    skill: Optional[float]
    expected_edge: Optional[float]  # per contract, after fees
    realized_edge: float  # per contract, after fees
    model_bins: list[CalibrationBin] = field(default_factory=list)
    market_bins: list[CalibrationBin] = field(default_factory=list)

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def settled_bets(ledger: Ledger, strategy: Optional[str] = None) -> list[Bet]:
    """Every fill whose market has settled, paired with how it turned out."""
    outcomes: dict[tuple[str, str], float] = {}
    for s in ledger.settlements(strategy):
        outcomes[(s["strategy"], s["ticker"])] = s["yes_value"]
    bets = []
    for f in ledger.fills(strategy):
        key = (f["strategy"], f["ticker"])
        if key not in outcomes or f["count"] <= 0:
            continue
        yes_value = outcomes[key]
        bets.append(Bet(
            strategy=f["strategy"],
            ticker=f["ticker"],
            side=f["side"],
            price=f["price"],
            fee_per_contract=f["fee"] / f["count"],
            count=f["count"],
            model_prob=f["model_prob"],
            outcome=yes_value if f["side"] == "yes" else 1 - yes_value,
        ))
    return bets


def calibration(pairs: list[tuple[float, float]], bins: int = 10) -> list[CalibrationBin]:
    """pairs of (forecast, outcome) -> per-bin average forecast vs hit rate."""
    buckets: list[list[tuple[float, float]]] = [[] for _ in range(bins)]
    for p, o in pairs:
        idx = min(bins - 1, max(0, int(p * bins)))
        buckets[idx].append((p, o))
    out = []
    for i, b in enumerate(buckets):
        if not b:
            continue
        out.append(CalibrationBin(
            lo=i / bins,
            hi=(i + 1) / bins,
            n=len(b),
            avg_forecast=sum(p for p, _ in b) / len(b),
            hit_rate=sum(o for _, o in b) / len(b),
        ))
    return out


def _brier(pairs: list[tuple[float, float]]) -> float:
    return sum((p - o) ** 2 for p, o in pairs) / len(pairs)


def summarize(bets: list[Bet], strategy: str) -> Optional[AccuracySummary]:
    mine = [b for b in bets if b.strategy == strategy]
    if not mine:
        return None
    market = [(b.price, b.outcome) for b in mine]
    modeled = [b for b in mine if b.model_prob is not None]
    model_pairs = [(b.model_prob, b.outcome) for b in modeled]
    brier_market = _brier(market)
    brier_model = _brier(model_pairs) if model_pairs else None
    # Skill only compares bets that had a model probability
    skill = None
    if modeled:
        bm = _brier([(b.price, b.outcome) for b in modeled])
        skill = 1 - brier_model / bm if bm > 0 else None
    return AccuracySummary(
        strategy=strategy,
        n=len(mine),
        hit_rate=sum(b.outcome for b in mine) / len(mine),
        avg_price=sum(b.price for b in mine) / len(mine),
        brier_market=brier_market,
        brier_model=brier_model,
        skill=skill,
        expected_edge=(sum(b.model_prob - b.price - b.fee_per_contract for b in modeled) / len(modeled)
                       if modeled else None),
        realized_edge=sum(b.outcome - b.price - b.fee_per_contract for b in mine) / len(mine),
        model_bins=calibration(model_pairs),
        market_bins=calibration(market),
    )


def accuracy_report(ledger: Ledger, strategies: list[str]) -> list[AccuracySummary]:
    bets = settled_bets(ledger)
    out = [summarize(bets, s) for s in strategies]
    return [s for s in out if s]


def _pct(x: Optional[float], signed: bool = False) -> str:
    if x is None:
        return "-"
    return f"{x:+.1%}" if signed else f"{x:.1%}"


def format_accuracy(summaries: list[AccuracySummary], personas: Optional[dict[str, str]] = None,
                    detail: Optional[str] = None) -> str:
    personas = personas or {}
    header = (f"{'employee':<36}{'bets':>6}{'won':>7}{'avg px':>8}{'exp edge':>10}{'real edge':>11}"
              f"{'brier':>8}{'mkt brier':>10}{'skill':>8}")
    lines = [header, "-" * len(header)]
    for s in sorted(summaries, key=lambda s: s.realized_edge, reverse=True):
        exp = f"{s.expected_edge:+.3f}" if s.expected_edge is not None else "-"
        br = f"{s.brier_model:.3f}" if s.brier_model is not None else "-"
        lines.append(
            f"{personas.get(s.strategy, s.strategy):<36}{s.n:>6}{s.hit_rate:>7.0%}{s.avg_price:>8.2f}"
            f"{exp:>10}{s.realized_edge:>+11.3f}{br:>8}{s.brier_market:>10.3f}{_pct(s.skill, True):>8}"
        )
    lines.append("")
    lines.append("edge = dollars per contract after fees. skill > 0 means the employee's odds beat the market's.")

    for s in summaries:
        if detail and s.strategy != detail:
            continue
        bins = s.model_bins or s.market_bins
        if not detail and not s.model_bins:
            continue
        label = "employee's odds" if s.model_bins else "price paid"
        lines.append("")
        lines.append(f"Calibration for {personas.get(s.strategy, s.strategy)} (by {label}):")
        lines.append(f"  {'forecast':>10} {'bets':>6} {'avg forecast':>13} {'actually won':>13}")
        for b in bins:
            lines.append(f"  {b.lo:>4.0%}-{b.hi:<4.0%} {b.n:>6} {b.avg_forecast:>13.1%} {b.hit_rate:>13.1%}")
    return "\n".join(lines)
