"""
Reconciliation: do our books match the real Kalshi account?

Each run compares two things for the office pool's members:

  positions  Kalshi keeps one net number per market (+ YES, - NO). Ours is the
             sum over every employee of YES minus NO contracts held.
  cash       Kalshi's balance against our cash. Kalshi pays out a YES+NO pair as
             $1 right away even when two different employees hold the halves, so:
                 expected = our cash + pairs across employees
             Kalshi does NOT take money out of the balance for bids that are still
             waiting (seen on the real exchange 2026-10-19: each waiting bid showed
             up as exactly that much "extra" cash), and neither do we.
             The first reading sets a baseline (money in the account that isn't
             the pool's); after that, drift is any change in the difference.

Markets that settle or fill can differ for a run (Kalshi pays before our next check
sees the result, or shows a fill seconds before our books book it), so the desk only
halts when the same market differs on three checks in a row (runner.MISMATCH_CHECKS). The other
way round, Kalshi can take several minutes to pay a market we've already settled
(2026-11-02: a ZEC win still held on Kalshi 6+ minutes after its result, which
halted trading): a recently settled market that Kalshi still holds exactly as we
held it is "settling", not a mismatch, and its payout counts as on its way.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Optional

from desk.kalshi.client import KalshiClient
from desk.paper.account import PaperAccount


@dataclass
class Reconciliation:
    balance: float  # Kalshi's cash
    expected: float
    drift: float
    baseline: float
    positions: dict[str, tuple[float, float]] = field(default_factory=dict)  # ticker -> (ours, Kalshi's)
    mismatches: dict[str, tuple[float, float]] = field(default_factory=dict)
    held: float = 0.0  # what Kalshi says the open positions are worth
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
    net = {t: round(yes[t] - no[t], 2) for t in set(yes) | set(no) if abs(yes[t] - no[t]) > 0.005}
    return net, cash + pairs


async def reconcile(client: KalshiClient, accounts: dict[str, PaperAccount], members: set[str], resting: list,
                    baseline: Optional[float] = None, tolerance: float = 0.011,
                    settling: Optional[dict[str, tuple[float, float]]] = None) -> Reconciliation:
    """`settling`: markets we settled recently, ticker -> (net contracts we held, what they pay us)."""
    positions = await client.get_positions()
    theirs = {}
    for p in positions:
        n = float(p.get("position_fp") or p.get("position") or 0)
        if abs(n) > 0.005:
            theirs[p["ticker"]] = n
    account = await client.get_account()
    balance = account["cash"]
    ours, expected = our_books(accounts, members, resting)
    for t, (net, payout) in (settling or {}).items():
        if abs(ours.get(t, 0.0)) < 0.005 and t in theirs and abs(theirs[t] - net) <= tolerance:
            del theirs[t]          # Kalshi hasn't paid it yet: the position is still there,
            balance += payout      # and so is its money, on the way
    base = balance - expected if baseline is None else baseline
    both = {t: (ours.get(t, 0.0), theirs.get(t, 0.0)) for t in set(ours) | set(theirs)}
    mismatches = {t: v for t, v in both.items() if abs(v[0] - v[1]) > tolerance}
    return Reconciliation(balance=round(balance, 4), expected=round(expected, 4),
                          drift=round(balance - expected - base, 4), baseline=round(base, 4),
                          positions=both, mismatches=mismatches, held=round(account["positions"], 4))
