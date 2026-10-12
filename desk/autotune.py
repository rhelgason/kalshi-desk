"""
Autotuning: employees adjust their own settings as new history comes in.

Every run (daily by default, or when "Retune now" is pressed on the website):

  1. Load the last `lookback_days` of stored history (desk/backtest/store.py).
  2. For each employee with autotune on, try every combination in its search
     space. Pick the best on the TRAIN period (first 2/3).
  3. Apply it only if it is also profitable in the unseen TEST period (last 1/3)
     with enough bets, AND beats the employee's current settings in TEST by
     `min_improvement` dollars. Otherwise keep the current settings.
  4. Log the decision to the office news feed and save the full results.

Employees that can't be replayed from price history (Walt reads the live trade
tape, Vinny needs hourly ladders, the market maker needs fills from other
traders) are left to the performance reviews instead.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from desk import hr
from desk.backtest.data import BacktestData
from desk.backtest.engine import BacktestConfig
from desk.backtest.tune import TuneRow, combos, tune
from desk.config import DeskConfig
from desk.kalshi.fees import FeeSchedule
from desk.paper.ledger import Ledger

logger = logging.getLogger(__name__)

SEARCH_SPACES: dict[str, dict[str, list[Any]]] = {
    "nickel_picker": {"min_price": [0.85, 0.88, 0.90], "max_price": [0.93, 0.95, 0.97],
                      "min_seconds": [300, 600, 900]},
    "longshot_fade": {"min_yes": [0.03, 0.05, 0.08], "max_yes": [0.12, 0.15, 0.20],
                      "min_seconds": [300, 600, 900]},
    "sniper": {"min_win_prob": [0.95, 0.97, 0.98], "max_seconds": [180, 300, 600],
               "vol_multiplier": [1.0, 1.5, 2.0]},
    "fair_value": {"market_weight": [0.7, 0.8, 0.9], "min_edge": [0.04, 0.06, 0.08, 0.12]},
    "momentum": {"momentum_window": [5, 15, 60], "market_weight": [0.8, 0.9], "min_edge": [0.04, 0.08]},
    "mean_revert": {"momentum_window": [5, 15], "market_weight": [0.8, 0.9], "min_edge": [0.04, 0.08]},
}

TUNE_SERIES = ["KXBTC15M"]  # bitcoin only since Season 3


def _summary(r) -> dict:
    return {"pnl": round(r.pnl, 2), "bets": r.bets, "wins": r.wins, "roi": round(r.roi, 4),
            "skill": r.skill, "realized_edge": r.realized_edge, "confidence": round(r.confidence, 3)}


def decide(key: str, current: dict, data: BacktestData, bt_cfg: BacktestConfig, policy: dict) -> dict:
    """Search one employee's settings; return what we found and whether to switch."""
    space = SEARCH_SPACES[key]
    grid = {k: v for k, v in space.items()}
    rows = tune(key, current, grid, data, bt_cfg)
    baseline = tune(key, current, {}, data, bt_cfg)[0]  # current settings, same split
    at = policy["autotune"]
    # Must make money in BOTH periods, with enough test bets, and the test-period
    # result must not look like luck
    passing = [r for r in rows if r.holds_up and r.test.bets >= int(at["min_test_bets"])
               and r.test.confidence >= float(at.get("min_confidence", 0.0))]
    best: Optional[TuneRow] = max(passing, key=lambda r: r.train.pnl) if passing else None
    changes = {k: v for k, v in (best.params if best else {}).items() if current.get(k) != v}
    apply = bool(best and changes and best.test.pnl >= baseline.test.pnl + float(at["min_improvement"]))
    if not best:
        why = "no setting made money in both periods with enough bets and confidence"
    elif not changes:
        why = "current settings are already the best"
    elif not apply:
        why = f"best found added only ${best.test.pnl - baseline.test.pnl:+.2f} in the test period"
    else:
        why = f"test-period P&L ${baseline.test.pnl:+.2f} -> ${best.test.pnl:+.2f}"
    return {
        "employee": key, "applied": apply, "why": why, "changes": changes if apply else {},
        "tried": len(rows), "current": {"params": {k: current.get(k) for k in space},
                                        "train": _summary(baseline.train), "test": _summary(baseline.test)},
        "best": ({"params": best.params, "train": _summary(best.train), "test": _summary(best.test)}
                 if best else None),
        "top": [{"params": r.params, "train": _summary(r.train), "test": _summary(r.test), "holds_up": r.holds_up}
                for r in rows[:10]],
    }


def autotune_due(policy: dict, now: Optional[datetime] = None) -> bool:
    at = policy["autotune"]
    if not at.get("enabled"):
        return bool(at.get("requested_at"))
    if at.get("requested_at"):
        return True
    last = at.get("last_run")
    return not last or (now or datetime.now(timezone.utc)) - datetime.fromisoformat(last) >= timedelta(
        hours=float(at["every_hours"]))


def run_autotune(ledger: Ledger, cfg: DeskConfig, data: BacktestData,
                 fees: Optional[dict[str, FeeSchedule]] = None, only: Optional[list[str]] = None,
                 depth: float = 100) -> list[dict]:
    policy = hr.load_policy(ledger)
    roster = hr.load_roster(ledger, list(SEARCH_SPACES))
    effective = hr.effective_strategy_config(cfg.strategies, roster)
    bt_cfg = BacktestConfig(starting_cash=cfg.starting_cash, depth=depth, fill_delay=1, fees=fees or {})
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    decisions = []
    for key in SEARCH_SPACES:
        rec = roster[key]
        if (only and key not in only) or not rec.autotune or rec.status == "fired" or rec.control:
            continue
        current = {k: v for k, v in (effective.get(key) or {}).items() if k != "enabled"}
        logger.info("Autotuning %s (%d combinations)", key, len(combos(SEARCH_SPACES[key])))
        d = decide(key, current, data, bt_cfg, policy)
        decisions.append(d)
        ledger.save_tuning_run(f"{stamp}-{key}", key, d)
        if d["applied"]:
            rec.params = {**rec.params, **d["changes"]}
            ledger.upsert_employee(rec.to_row())
        ledger.record_event("tune", {k: d[k] for k in ("applied", "why", "changes", "tried")} | {
            "test_before": d["current"]["test"], "test_after": d["best"]["test"] if d["best"] else None},
            strategy=key)
    policy = hr.load_policy(ledger)  # reload: the website may have changed it meanwhile
    policy["autotune"]["last_run"] = datetime.now(timezone.utc).isoformat()
    policy["autotune"]["requested_at"] = None
    hr.save_policy(ledger, policy)
    return decisions
