"""
Kalshi trading fees.

Kalshi charges a "quadratic" fee that's biggest for coin-flip prices and tiny
near 0 or 1:

    taker fee = ceil( 0.07   x multiplier x contracts x P x (1 - P) )  to the cent
    maker fee = ceil( 0.0175 x multiplier x contracts x P x (1 - P) )  to the cent

At 50c that's 1.75c per contract for takers. At 5c or 95c it's ~0.33c.
"Taker" = your order trades immediately against a resting order.
"Maker" = your order rests on the book and someone else trades into it.
Maker fees only apply on some series (fee_type "quadratic_with_maker_fees").

Rounding up to the next cent per order is the published schedule. Kalshi's
newer rounding docs describe finer-grained rounding for direct members, so
rounding to the cent is the conservative choice (it slightly overstates fees).

Source: https://kalshi.com/docs/kalshi-fee-schedule.pdf (Feb 2026)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

TAKER_RATE = 0.07
MAKER_RATE = 0.0175


def _round_up(amount: float, increment: float) -> float:
    if amount <= 0:
        return 0.0
    # Small epsilon so that 0.0175 * 100 doesn't round up to 1.76 from float noise
    return math.ceil(amount / increment - 1e-9) * increment


def quadratic_fee(
    price: float,
    count: float,
    rate: float,
    multiplier: float = 1.0,
    round_to: float = 0.01,
) -> float:
    if count <= 0 or not (0 < price < 1):
        return 0.0
    raw = rate * multiplier * count * price * (1 - price)
    return round(_round_up(raw, round_to), 6)


def taker_fee(price: float, count: float, multiplier: float = 1.0, round_to: float = 0.01) -> float:
    return quadratic_fee(price, count, TAKER_RATE, multiplier, round_to)


def maker_fee(price: float, count: float, multiplier: float = 1.0, round_to: float = 0.01) -> float:
    return quadratic_fee(price, count, MAKER_RATE, multiplier, round_to)


def taker_fee_per_contract(price: float, multiplier: float = 1.0) -> float:
    """Un-rounded fee per contract; useful for comparing edges."""
    if not (0 < price < 1):
        return 0.0
    return TAKER_RATE * multiplier * price * (1 - price)


@dataclass
class FeeSchedule:
    """Per-series fee settings, from GET /series/{ticker}."""

    fee_type: str = "quadratic"
    multiplier: float = 1.0
    round_to: float = 0.01

    @classmethod
    def from_series(cls, series: dict) -> "FeeSchedule":
        return cls(
            fee_type=series.get("fee_type") or "quadratic",
            multiplier=float(series.get("fee_multiplier") or 1.0),
        )

    @property
    def charges_maker_fees(self) -> bool:
        return "maker" in self.fee_type

    def taker(self, price: float, count: float) -> float:
        return taker_fee(price, count, self.multiplier, self.round_to)

    def maker(self, price: float, count: float) -> float:
        if not self.charges_maker_fees:
            return 0.0
        return maker_fee(price, count, self.multiplier, self.round_to)

    def taker_per_contract(self, price: float) -> float:
        return taker_fee_per_contract(price, self.multiplier)
