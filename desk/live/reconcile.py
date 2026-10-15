"""
Reconciliation: do our books match the real Kalshi account?

Each run compares two things for the office pool's members:

  positions  Kalshi keeps one net number per market (+ YES, - NO). Ours is the
             sum over every employee of YES minus NO contracts held.
  cash       Kalshi's available balance against our cash. Kalshi pays out a
             YES+NO pair as $1 right away even when two different employees hold
             the halves, and sets aside money for bids that are waiting, so:
                 expected = our cash + pairs across employees - money in waiting bids
             The first reading sets a baseline (money in the account that isn't
             the pool's); after that, drift is any change in the difference.

Markets that settle can differ for a run (Kalshi pays before our next check
sees the result), so the desk only halts when a mismatch lasts two runs.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Optional

from desk.kalshi.client import KalshiClient
from desk.paper.account import PaperAccount


@dataclass
class Reconciliation:
    balance: float
    expected: float
    drift: float
    baseline: float
    positions: dict[str, tuple[float, float]] = field(default_factory=dict)  # ticker -> (ours, Kalshi's)
    mismatches: dict[str, tuple[float, float]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.mismatches

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ok"] = self.ok
        return d


def our_books(accounts: dict[str, PaperAccount], members: set[str], resting: list) -> tuple[dict, float]:
    """(net contracts by ticker, expected Kalshi balance) for the pool's members."""
    yes: dict[str, float] = defaultdict(float)
    no: dict[str, float] = defaultdict(float)
    cash = 0.0
    for k, a in accounts.items():
        if k not in members:
            continue
        cash += a.cash
        for t, p in a.positions.items():
            yes[t] += p.yes
            no[t] += p.no
    pairs = sum(min(yes[t], no[t]) for t in set(yes) | set(no))
    waiting = sum(o.price * o.remaining for o in resting if o.strategy in members)
    net = {t: round(yes[t] - no[t], 2) for t in set(yes) | set(no) if abs(yes[t] - no[t]) > 0.005}
    return net, cash + pairs - waiting


async def reconcile(client: KalshiClient, accounts: dict[str, PaperAccount], members: set[str], resting: list,
                    baseline: Optional[float] = None, tolerance: float = 0.011) -> Reconciliation:
    positions = await client.get_positions()
    theirs = {}
    for p in positions:
        n = float(p.get("position_fp") or p.get("position") or 0)
        if abs(n) > 0.005:
            theirs[p["ticker"]] = n
    balance = await client.get_balance()
    ours, expected = our_books(accounts, members, resting)
    base = balance - expected if baseline is None else baseline
    both = {t: (ours.get(t, 0.0), theirs.get(t, 0.0)) for t in set(ours) | set(theirs)}
    mismatches = {t: v for t, v in both.items() if abs(v[0] - v[1]) > tolerance}
    return Reconciliation(balance=round(balance, 4), expected=round(expected, 4),
                          drift=round(balance - expected - base, 4), baseline=round(base, 4),
                          positions=both, mismatches=mismatches)
