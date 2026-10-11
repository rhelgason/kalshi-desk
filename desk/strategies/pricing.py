"""
Math helpers: fair value of strike contracts, payoffs, and bet sizing.

Fair value
----------
"Will BTC be above $K at 10pm?" is what options traders call a *digital
option*. If prices move like a random walk (log-normal, the Black-Scholes
assumption), the chance of finishing above K is

    P(above) = N(d2),   d2 = [ln(S/K) - sigma^2 T / 2] / (sigma sqrt(T))

S = spot price now, sigma = annualized volatility, T = years until settlement,
N = the bell-curve CDF. Real crypto has fatter tails than this model, so it
underrates big moves; strategies should be careful far from the money.

Kalshi settles on the *average* of the last 60 seconds, which is slightly
less random than a single price. We account for that in effective_years().

Sizing
------
The Kelly criterion says: if you buy a contract at price p that you think
wins with probability q, bet the fraction (q - p) / (1 - p) of your bankroll.
Full Kelly is very aggressive; most people use a quarter of it.
"""

from __future__ import annotations

import math
from typing import Iterable, Optional

from desk.kalshi.models import Market, Side

SECONDS_PER_YEAR = 365 * 24 * 3600


def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def effective_years(seconds_to_settle: float, averaging_window: float = 60.0) -> float:
    """
    Variance-equivalent time for a settlement that averages the final window.

    Averaging a random walk over its last W seconds has the variance of
    (T - W) + W/3 seconds of plain random walk.
    """
    t = max(seconds_to_settle, 0.0)
    w = min(averaging_window, t)
    return ((t - w) + w / 3) / SECONDS_PER_YEAR


def prob_above(spot: float, strike: float, vol: float, years: float) -> float:
    if spot <= 0 or strike <= 0:
        return float("nan")
    if years <= 0 or vol <= 0:
        return 1.0 if spot > strike else 0.0
    sd = vol * math.sqrt(years)
    d2 = (math.log(spot / strike) - 0.5 * sd * sd) / sd
    return norm_cdf(d2)


def prob_yes(market: Market, spot: float, vol: float, years: float) -> Optional[float]:
    """Model probability that `market` resolves YES, or None if unsupported."""
    st, lo, hi = market.strike_type, market.floor_strike, market.cap_strike
    if st in ("greater", "greater_or_equal") and lo is not None:
        return prob_above(spot, lo, vol, years)
    if st in ("less", "less_or_equal") and hi is not None:
        return 1 - prob_above(spot, hi, vol, years)
    if st == "between" and lo is not None and hi is not None:
        return max(0.0, prob_above(spot, lo, vol, years) - prob_above(spot, hi, vol, years))
    return None


def kelly_fraction(win_prob: float, price: float) -> float:
    """Kelly bet fraction for a $1 binary bought at `price` (fees included in price)."""
    if not (0 < price < 1):
        return 0.0
    return max(0.0, (win_prob - price) / (1 - price))


# ---------------------------------------------------------------------------
# Payoff analysis for multi-leg positions
# ---------------------------------------------------------------------------


def outcome_points(markets: Iterable[Market], eps: float = 0.001) -> list[float]:
    """
    Values of the underlying worth checking: every strike, just either side
    of it, and far below/above all strikes. Between those points every
    contract's payoff is constant, so checking them covers every outcome.
    """
    strikes = sorted({s for m in markets for s in m.strikes})
    if not strikes:
        return []
    pts = {strikes[0] - abs(strikes[0]) - 1, strikes[-1] * 2 + 1}
    for s in strikes:
        pts.update((s - eps, s, s + eps))
    for a, b in zip(strikes, strikes[1:]):
        pts.add((a + b) / 2)
    return sorted(pts)


def leg_pays(market: Market, side: Side, value: float) -> Optional[bool]:
    yes = market.yes_pays_at(value)
    if yes is None:
        return None
    return yes if side is Side.YES else not yes


def payoff_range(legs: list[tuple[Market, Side]]) -> Optional[tuple[float, float]]:
    """
    (worst, best) payout in dollars of holding one contract of each leg,
    across every possible settlement value. None if any leg is unmodelable.
    """
    pts = outcome_points(m for m, _ in legs)
    if not pts:
        return None
    worst, best = math.inf, -math.inf
    for v in pts:
        total = 0
        for m, side in legs:
            pays = leg_pays(m, side, v)
            if pays is None:
                return None
            total += pays
        worst, best = min(worst, total), max(best, total)
    return worst, best


def yes_implies(a: Market, b: Market) -> bool:
    """True if every outcome where B's YES pays, A's YES also pays."""
    pts = outcome_points([a, b])
    if not pts:
        return False
    for v in pts:
        bv, av = b.yes_pays_at(v), a.yes_pays_at(v)
        if bv is None or av is None:
            return False
        if bv and not av:
            return False
    return True
