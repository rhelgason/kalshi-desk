"""
Parameter tuning with a train/test split.

Trying lots of settings on the same history and keeping the best one is a
trap: some combination will always look great by luck ("overfitting"). So we
split the history in time:

    train  (first 2/3)   pick settings here
    test   (last 1/3)    check them here, on markets the search never saw

A setting is only worth using if it also makes money in the test period.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from typing import Any, Optional

from desk.backtest.data import BacktestData
from desk.backtest.engine import Backtest, BacktestConfig
from desk.paper.accuracy import accuracy_report, evidence_report
from desk.paper.scoreboard import scoreboard_rows
from desk.strategies import EVERYONE

logger = logging.getLogger(__name__)


def parse_grid(specs: list[str]) -> dict[str, list[Any]]:
    """["min_edge=0.02,0.04", "market_weight=0,0.8"] -> {"min_edge": [0.02, 0.04], ...}"""
    grid: dict[str, list[Any]] = {}
    for spec in specs:
        key, _, values = spec.partition("=")
        parsed = []
        for v in values.split(","):
            v = v.strip()
            try:
                parsed.append(int(v) if v.lstrip("-").isdigit() else float(v))
            except ValueError:
                parsed.append({"true": True, "false": False}.get(v.lower(), v))
        grid[key.strip()] = parsed
    return grid


def combos(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    keys = list(grid)
    return [dict(zip(keys, vals)) for vals in itertools.product(*(grid[k] for k in keys))] or [{}]


@dataclass
class Result:
    pnl: float
    roi: float
    bets: int
    wins: int
    losses: int
    fees: float
    max_drawdown: float
    skill: Optional[float]
    realized_edge: Optional[float]
    confidence: float = 0.5  # skill-or-luck confidence (desk.paper.evidence)


@dataclass
class TuneRow:
    params: dict[str, Any]
    train: Result
    test: Result

    @property
    def holds_up(self) -> bool:
        return self.train.pnl > 0 and self.test.pnl > 0


def _run(key: str, params: dict, frames, data: BacktestData, cfg: BacktestConfig) -> Result:
    strat = EVERYONE[key](**params)  # alumni too: `desk tune` can still replay a retired employee
    bt = Backtest(data, [strat], cfg)
    bt.run(frames)
    row = scoreboard_rows(bt.accounts, bt.ledger)[0]
    acc = accuracy_report(bt.ledger, [key])
    a = acc[0] if acc else None
    ev = evidence_report(bt.ledger, [key])
    return Result(row.pnl, row.roi, row.fills, row.wins, row.losses, row.fees, row.max_drawdown,
                  a.skill if a else None, a.realized_edge if a else None,
                  ev[0].confidence if ev else 0.5)


def tune(key: str, base: dict[str, Any], grid: dict[str, list[Any]], data: BacktestData,
         cfg: BacktestConfig, train_fraction: float = 2 / 3) -> list[TuneRow]:
    split = int(data.start + (data.end - data.start) * train_fraction)
    train, test = data.slice(data.start, split), data.slice(split, data.end)
    # Frames don't depend on the strategy, so build them once per period
    train_frames = Backtest(train, [], cfg).build_frames()
    test_frames = Backtest(test, [], cfg).build_frames()
    rows = []
    for i, combo in enumerate(combos(grid), 1):
        params = {**base, **combo}
        rows.append(TuneRow(combo, _run(key, params, train_frames, train, cfg),
                            _run(key, params, test_frames, test, cfg)))
        if i % 10 == 0:
            logger.info("Tuned %d combinations", i)
    rows.sort(key=lambda r: r.train.pnl, reverse=True)
    return rows


def _fmt(r: Result) -> str:
    skill = f"{r.skill:+.0%}" if r.skill is not None else "  -"
    edge = f"{r.realized_edge * 100:+.1f}c" if r.realized_edge is not None else "  -"
    return f"{r.pnl:>+9.2f} {r.bets:>5} {skill:>6} {edge:>7} {r.max_drawdown:>6.0%}"


def format_tune(rows: list[TuneRow], top: int = 15) -> str:
    header = (f"{'settings':<44} | {'TRAIN P&L':>9} {'bets':>5} {'skill':>6} {'edge':>7} {'maxDD':>6}"
              f" | {'TEST P&L':>9} {'bets':>5} {'skill':>6} {'edge':>7} {'maxDD':>6}")
    lines = [header, "-" * len(header)]
    for r in rows[:top]:
        label = ", ".join(f"{k}={v}" for k, v in r.params.items()) or "(current settings)"
        mark = " ✓" if r.holds_up else ""
        lines.append(f"{label[:44]:<44} | {_fmt(r.train)} | {_fmt(r.test)}{mark}")
    lines.append("")
    lines.append("✓ = profitable in BOTH periods. Prefer settings that hold up in TEST with a decent number of bets;")
    lines.append("a huge TRAIN number that collapses in TEST is luck, not skill.")
    return "\n".join(lines)
