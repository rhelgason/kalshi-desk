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
    """Every bet whose market has settled, paired with how it turned out."""
    outcomes: dict[tuple[str, str], float] = {}
    for s in ledger.settlements(strategy):
        outcomes[(s["strategy"], s["ticker"])] = s["yes_value"]
    # One bet per employee, market and side, however many pieces it filled in
    merged: dict[tuple[str, str, str], list] = {}
    for f in ledger.fills(strategy):
        key = (f["strategy"], f["ticker"])
        if key not in outcomes or f["count"] <= 0:
            continue
        m = merged.setdefault((*key, f["side"]), [0.0, 0.0, 0.0, f["model_prob"]])
        m[0] += f["count"]
        m[1] += f["count"] * f["price"]
        m[2] += f["fee"]
    bets = []
    for (strat, ticker, side), (count, paid, fee, prob) in merged.items():
        yes_value = outcomes[(strat, ticker)]
        bets.append(Bet(
            strategy=strat,
            ticker=ticker,
            side=side,
            price=paid / count,
            fee_per_contract=fee / count,
            count=count,
            model_prob=prob,
            outcome=yes_value if side == "yes" else 1 - yes_value,
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


# One bet per employee, market and side: a resting bid often fills in several
# pieces, and counting each piece as its own bet would overstate the evidence.
_BETS_CTE = """
WITH pieces AS (
    SELECT strategy, ticker, season, side, sum(count) AS count, sum(count * price) / sum(count) AS price,
           sum(fee) / sum(count) AS fpc, avg(model_prob) AS model_prob
    FROM fills WHERE count > 0 AND season = %(season)s
    GROUP BY strategy, ticker, season, side
),
bets AS (
    SELECT f.strategy, f.price, f.model_prob, f.count, f.fpc,
           CASE WHEN f.side = 'yes' THEN s.yes_value ELSE 1 - s.yes_value END AS outcome
    FROM pieces f
    JOIN settlements s ON s.strategy = f.strategy AND s.ticker = f.ticker AND s.season = f.season
)
"""


def accuracy_report_sql(ledger: Ledger, strategies: list[str]) -> list[AccuracySummary]:
    """
    Same numbers as accuracy_report(), aggregated inside Postgres so only a
    few summary rows cross the network instead of every fill.
    """
    season = str(int(ledger.season))
    totals = ledger._rows((_BETS_CTE + """
        SELECT strategy, count(*) AS n, avg(outcome) AS hit_rate, avg(price) AS avg_price,
               avg((price - outcome) ^ 2) AS brier_market,
               avg((model_prob - outcome) ^ 2) FILTER (WHERE model_prob IS NOT NULL) AS brier_model,
               avg((price - outcome) ^ 2) FILTER (WHERE model_prob IS NOT NULL) AS brier_market_modeled,
               avg(model_prob - price - fpc) FILTER (WHERE model_prob IS NOT NULL) AS expected_edge,
               avg(outcome - price - fpc) AS realized_edge
        FROM bets GROUP BY strategy
    """).replace("%(season)s", season))
    bins = ledger._rows((_BETS_CTE + """
        SELECT strategy, 'model' AS kind, LEAST(9, floor(model_prob * 10))::int AS b,
               count(*) AS n, avg(model_prob) AS f, avg(outcome) AS o
        FROM bets WHERE model_prob IS NOT NULL GROUP BY strategy, b
        UNION ALL
        SELECT strategy, 'market', LEAST(9, floor(price * 10))::int, count(*), avg(price), avg(outcome)
        FROM bets GROUP BY strategy, 3
    """).replace("%(season)s", season))
    by_strategy: dict[str, dict[str, list[CalibrationBin]]] = {}
    for r in sorted(bins, key=lambda r: r["b"]):
        by_strategy.setdefault(r["strategy"], {"model": [], "market": []})[r["kind"]].append(
            CalibrationBin(lo=r["b"] / 10, hi=(r["b"] + 1) / 10, n=int(r["n"]),
                           avg_forecast=float(r["f"]), hit_rate=float(r["o"])))
    out = []
    for r in totals:
        if r["strategy"] not in strategies:
            continue
        bm, bmm = r["brier_model"], r["brier_market_modeled"]
        b = by_strategy.get(r["strategy"], {"model": [], "market": []})
        out.append(AccuracySummary(
            strategy=r["strategy"], n=int(r["n"]), hit_rate=float(r["hit_rate"]),
            avg_price=float(r["avg_price"]), brier_market=float(r["brier_market"]),
            brier_model=float(bm) if bm is not None else None,
            skill=(1 - float(bm) / float(bmm)) if bm is not None and bmm else None,
            expected_edge=float(r["expected_edge"]) if r["expected_edge"] is not None else None,
            realized_edge=float(r["realized_edge"]),
            model_bins=b["model"], market_bins=b["market"],
        ))
    return out


def evidence_report(ledger: Ledger, strategies: list[str]) -> list:
    """Skill-or-luck evidence per employee (current season), in Python."""
    from desk.paper.evidence import evidence

    bets = settled_bets(ledger)
    return [evidence(bets, s) for s in strategies if any(b.strategy == s for b in bets)]


def evidence_report_sql(ledger: Ledger, strategies: list[str]) -> list:
    """Same as evidence_report(), aggregated inside Postgres."""
    from desk.paper.evidence import evidence_from_stats

    rows = ledger._rows((_BETS_CTE + """
        SELECT strategy, count(*) AS n, avg(outcome - price - fpc) AS mean,
               coalesce(stddev_samp(outcome - price - fpc), 0) AS sd,
               sum(count) AS contracts, sum(count * (outcome - price - fpc)) AS pnl
        FROM bets GROUP BY strategy
    """).replace("%(season)s", str(int(ledger.season))))
    return [evidence_from_stats(r["strategy"], int(r["n"]), float(r["mean"]), float(r["sd"]),
                                float(r["contracts"]), float(r["pnl"]))
            for r in rows if r["strategy"] in strategies]
