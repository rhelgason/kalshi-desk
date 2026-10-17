"""
Background jobs, run by GitHub Actions every few hours (.github/workflows/jobs.yml).

    python -m desk jobs

  1. sync the newest settled markets and coin prices into the history store
  2. spend a few minutes backfilling Kalshi's archive (older history)
  3. if autotuning is due (daily by default) or "Retune now" was pressed on the
     website: retune every eligible employee, then run a backtest of the whole
     desk with its current settings and save it for the dashboard

These are too heavy for Vercel's free CPU allowance but fit easily in GitHub's
2,000 free Actions minutes a month for private repos.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from desk import hr
from desk.autotune import TUNE_SERIES, autotune_due, run_autotune
from desk.backtest import Backtest, BacktestConfig
from desk.backtest.store import backfill_archive, coverage, load_from_store, sync_prices, sync_recent
from desk.config import DeskConfig
from desk.kalshi.client import KalshiClient
from desk.paper.accuracy import accuracy_report
from desk.paper.realism import measured_depth
from desk.paper.ledger import Ledger
from desk.paper.scoreboard import scoreboard_rows
from desk.strategies import REGISTRY

logger = logging.getLogger(__name__)


def calibrate_depth(ledger: Ledger, cfg: DeskConfig, min_samples: int = 30) -> dict:
    """
    Measure how many contracts were really on offer at our price in live fills,
    and use that (times the live liquidity share) as the backtests' depth.
    """
    depth, n = measured_depth(ledger)
    policy = hr.load_policy(ledger)
    realism = policy.get("realism") or {}
    if depth and n >= min_samples:
        realism = {"depth": round(max(5.0, depth * cfg.liquidity_share), 1), "samples": n,
                   "measured_at": datetime.now(timezone.utc).isoformat(), "median_on_offer": depth}
        policy["realism"] = realism
        hr.save_policy(ledger, policy)
    return realism


def snapshot_roster(ledger: Ledger, cfg: DeskConfig) -> int:
    """Record everyone's status, level and exact settings, so reviews know what was in force when."""
    roster = hr.load_roster(ledger, list(REGISTRY))
    effective = hr.effective_strategy_config(cfg.strategies, roster)
    snap = {k: {"status": r.status, "level": r.level, "multiplier": r.multiplier, "autotune": r.autotune,
                "settings": {p: v for p, v in (effective.get(k) or {}).items() if p != "enabled"}}
            for k, r in roster.items()}
    ledger.record_event("roster", snap)
    return len(snap)


def nightly_backtest(ledger: Ledger, cfg: DeskConfig, data, fees, depth: float = 100) -> str:
    """Backtest every working, replayable employee with today's settings; save for the dashboard."""
    roster = hr.load_roster(ledger, list(REGISTRY))
    effective = hr.effective_strategy_config(cfg.strategies, roster)
    strategies = []
    for key, cls in REGISTRY.items():
        params = dict(effective.get(key) or {})
        if not params.pop("enabled", True) or not getattr(cls, "backtestable", True):
            continue
        if key == "dart_monkey":
            params["seed"] = 42
        strategies.append(cls(**params))
    bt = Backtest(data, strategies, BacktestConfig(starting_cash=cfg.starting_cash, depth=depth, fill_delay=1,
                                                   fees=fees))
    bt.run()
    stamp = "auto-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    rows = scoreboard_rows(bt.accounts, bt.ledger)
    summary = {
        "id": stamp, "days": round((data.end - data.start) / 86400, 1), "series": TUNE_SERIES, "fill_delay": 1,
        "depth": depth, "settled_markets": sum(1 for hm in data.markets if hm.yes_value is not None),
        "stats": bt.stats, "automatic": True,
        "scoreboard": [{**r.__dict__, "pnl": r.pnl, "roi": r.roi, "win_rate": r.win_rate} for r in rows],
        "accuracy": [s.to_dict() for s in accuracy_report(bt.ledger, [s.key for s in strategies])],
        "equity": {s.key: [(ts, round(eq, 2)) for ts, eq in bt.ledger.equity_curve(s.key)] for s in strategies},
        "employees": [{"key": s.key, "name": s.persona.name, "emoji": s.persona.emoji} for s in strategies],
    }
    ledger.save_backtest(stamp, summary)
    return stamp


async def run_jobs(cfg: DeskConfig, backfill_seconds: float = 600, force_tune: bool = False) -> dict:
    ledger = Ledger(cfg.db_path, cfg.schema)
    policy = hr.load_policy(ledger)
    lookback = float(policy["autotune"]["lookback_days"])
    now = datetime.now(timezone.utc)
    report: dict = {}
    started = time.monotonic()
    async with KalshiClient(env=cfg.env, requests_per_second=6) as client:
        report["recent"] = await sync_recent(client, ledger, TUNE_SERIES, days=min(lookback, 60) + 1)
        report["prices"] = await sync_prices(ledger, ["BTC"], now - timedelta(days=lookback + 2), now)
        report["archive"] = await backfill_archive(client, ledger, TUNE_SERIES, seconds=backfill_seconds)
        fees = {s: await client.get_fee_schedule(s) for s in TUNE_SERIES}
    report["coverage"] = coverage(ledger)
    report["realism"] = calibrate_depth(ledger, cfg)
    depth = float(report["realism"].get("depth") or 100)

    if force_tune or autotune_due(policy, now):
        data = load_from_store(ledger, TUNE_SERIES, now - timedelta(days=lookback), now)
        report["autotune"] = [{k: d[k] for k in ("employee", "applied", "why", "changes")}
                              for d in run_autotune(ledger, cfg, data, fees, depth=depth)]
        report["backtest"] = nightly_backtest(ledger, cfg, data, fees, depth=depth)
    report["roster"] = snapshot_roster(ledger, cfg)
    report["seconds"] = round(time.monotonic() - started, 1)
    ledger.set_status("jobs", {"finished_at": datetime.now(timezone.utc).isoformat(), **report})
    return report
