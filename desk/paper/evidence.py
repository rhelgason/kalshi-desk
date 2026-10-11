"""
Skill or luck? How confident are we that an employee's edge is real?

Every settled bet has an "edge": what the contract paid out minus what we paid
(price + fee). Winning bets have positive edge, losing bets negative. A real
edge means the AVERAGE is above zero, consistently, not just a few lucky wins.

We use the standard test for that (a one-sided t-test): compare the average
edge to how much bets vary, scaled by how many bets we've seen.

    confidence = chance the true average edge is above zero

50% means "no idea" (a coin flip), 95% is strong evidence. With few bets,
even a good-looking average stays near 50%. That's the point.

Reality check: a paper fill can be a little better than a real one (other bots
get there first, prices move). So we also ask: would the edge survive if every
contract cost 1 cent more? 2 cents? That's the "cushion".

Caveat: bets placed at the same moment on the same coin move together, so
they're not fully independent. Treat the confidence as optimistic.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Optional

from desk.paper.accuracy import Bet

MIN_BETS = 30  # below this, always "too early to tell"


def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


@dataclass
class Evidence:
    strategy: str
    bets: int
    contracts: float
    edge: float  # average edge per contract, dollars, after fees
    sd: float  # how much single-bet edges vary
    pnl: float  # realized P&L on settled bets
    pnl_1c: float  # ...if every contract had cost 1 cent more
    pnl_2c: float
    confidence: float  # P(true edge > 0)
    confidence_1c: float  # P(true edge > 1 cent): survives slightly worse fills
    bets_needed: Optional[int]  # roughly how many bets to reach 95% at this edge
    verdict: str
    verdict_key: str

    def to_dict(self) -> dict:
        return asdict(self)


def _confidence(mean: float, sd: float, n: int, threshold: float = 0.0) -> float:
    if n < 2:
        return 0.5
    if sd <= 1e-12:
        return 1.0 if mean > threshold else 0.0 if mean < threshold else 0.5
    return norm_cdf((mean - threshold) / (sd / math.sqrt(n)))


def verdict(bets: int, confidence: float, confidence_1c: float) -> tuple[str, str]:
    if bets < MIN_BETS:
        return "too_early", f"Too early to tell ({bets} of {MIN_BETS} bets)"
    if confidence >= 0.95 and confidence_1c >= 0.8:
        return "strong", "Strong evidence of skill"
    if confidence >= 0.95:
        return "fragile", "Real edge, but thin: 1 cent of slippage could erase it"
    if confidence >= 0.8:
        return "promising", "Promising, needs more bets"
    if confidence <= 0.05:
        return "losing", "Reliably losing money"
    if confidence <= 0.2:
        return "probably_not", "Probably no edge"
    return "luck", "Could easily be luck"


def evidence_from_stats(strategy: str, n: int, mean: float, sd: float, contracts: float, pnl: float) -> Evidence:
    conf = _confidence(mean, sd, n)
    conf_1c = _confidence(mean, sd, n, threshold=0.01)
    needed = None
    if mean > 0 and sd > 0:
        needed = max(n, math.ceil((1.645 * sd / mean) ** 2))
    key, text = verdict(n, conf, conf_1c)
    return Evidence(
        strategy=strategy, bets=n, contracts=round(contracts, 2), edge=mean, sd=sd, pnl=round(pnl, 2),
        pnl_1c=round(pnl - 0.01 * contracts, 2), pnl_2c=round(pnl - 0.02 * contracts, 2),
        confidence=conf, confidence_1c=conf_1c, bets_needed=needed, verdict=text, verdict_key=key,
    )


def evidence(bets: list[Bet], strategy: str) -> Evidence:
    mine = [b for b in bets if b.strategy == strategy]
    edges = [b.outcome - b.price - b.fee_per_contract for b in mine]
    n = len(edges)
    mean = sum(edges) / n if n else 0.0
    sd = math.sqrt(sum((e - mean) ** 2 for e in edges) / (n - 1)) if n > 1 else 0.0
    contracts = sum(b.count for b in mine)
    pnl = sum(b.count * (b.outcome - b.price - b.fee_per_contract) for b in mine)
    return evidence_from_stats(strategy, n, mean, sd, contracts, pnl)
