"""
Run the desk one tick at a time on serverless hosting (Vercel + Supabase).

The long-running `python -m desk paper` loop keeps everything in memory. On
Vercel nothing survives between invocations, so each run:

  1. takes a lease (so two overlapping runs can't double-trade)
  2. loads the saved state from Postgres: paper accounts, price history for
     momentum, timers, drawdown peaks, and small per-employee memories
  3. runs exactly one Desk.tick()
  4. saves the state back and releases the lease

Supabase's pg_cron wakes this up every couple of minutes by calling the
Vercel function in api/tick.py.

Vercel's free plan includes 4 CPU-hours a month of function time, shared with
the dashboard. A budget governor tracks CPU used this month and skips runs if
the month is on pace to go over, so the account never gets paused.
"""

from __future__ import annotations

import logging
import resource
from dataclasses import asdict
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from desk.config import DeskConfig
from desk.feeds.crypto import CryptoFeed, UnderlyingQuote
from desk.kalshi.client import KalshiClient
from desk.kalshi.fees import FeeSchedule
from desk.paper.account import PaperAccount, Position
from desk.paper.ledger import Ledger
from desk.runner import Desk

logger = logging.getLogger(__name__)

STATE_KEY = "_state"
LEASE = "tick"
LEASE_SECONDS = 150
MONTHLY_CPU_BUDGET = 3.0 * 3600  # seconds; Vercel Hobby includes 4 CPU-hours (dashboard uses some)

# Cloud runs happen every couple of minutes, so heavier work is spaced out
CLOUD_OVERRIDES = dict(
    slow_series_every_seconds=600,  # hourly ladders every 10 minutes
    universe_refresh_seconds=600,  # broad non-crypto scan every 10 minutes
    crypto_refresh_seconds=0,  # discover new 15-minute windows every run
    settle_check_seconds=0,  # settle every run
    status_every_seconds=0,  # refresh the dashboard every run
    equity_every_seconds=300,
    accuracy_every_seconds=1800,
)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _dt(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s) if s else None


def _cpu_seconds() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime


_last_cpu_reading = 0.0  # survives between warm invocations of the same process


# ---------------------------------------------------------------------------
# (De)serializing state
# ---------------------------------------------------------------------------


def dump_accounts(accounts: dict[str, PaperAccount]) -> dict:
    return {
        k: {
            "starting_cash": a.starting_cash, "cash": a.cash, "fees_paid": a.fees_paid,
            "realized_pnl": a.realized_pnl, "trades": a.trades,
            "wins": a.settled_wins, "losses": a.settled_losses, "transfers": a.transfers,
            "positions": {t: [p.yes, p.no, p.yes_cost, p.no_cost, p.yes_fees, p.no_fees]
                          for t, p in a.positions.items()},
        }
        for k, a in accounts.items()
    }


def load_accounts(data: dict) -> dict[str, PaperAccount]:
    out = {}
    for k, d in data.items():
        a = PaperAccount(k, d["starting_cash"], cash=d["cash"], fees_paid=d["fees_paid"],
                         realized_pnl=d["realized_pnl"], trades=d["trades"],
                         settled_wins=d["wins"], settled_losses=d["losses"],
                         transfers=d.get("transfers", 0.0))
        a.cash = d["cash"]  # __post_init__ resets a zero balance to starting cash
        for t, v in d["positions"].items():
            a.positions[t] = Position(t, *v)
        out[k] = a
    return out


def dump_feed(feed: CryptoFeed, keep_minutes: int = 75) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=keep_minutes)
    return {
        "history": {s: [[t.isoformat(), p] for t, p in h if t >= cutoff] for s, h in feed.history.items()},
        "quotes": {s: {"iv": q.implied_vol, "rv": q.realized_vol, "spot": q.spot} for s, q in feed.quotes.items()},
        "vol_refreshed": {s: t.isoformat() for s, t in feed._vol_refreshed.items()},
    }


def load_feed(feed: CryptoFeed, data: dict) -> None:
    for s, pts in (data.get("history") or {}).items():
        feed.history[s] = deque(((datetime.fromisoformat(t), p) for t, p in pts), maxlen=2000)
    for s, q in (data.get("quotes") or {}).items():
        feed.quotes[s] = UnderlyingQuote(s, spot=q["spot"], implied_vol=q["iv"], realized_vol=q["rv"])
    feed._vol_refreshed = {s: datetime.fromisoformat(t) for s, t in (data.get("vol_refreshed") or {}).items()}


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------


def _budget_check(state: dict, now: datetime) -> tuple[bool, dict]:
    """Is this month on pace to stay under the CPU budget?"""
    month = now.strftime("%Y-%m")
    budget = state.get("budget") or {}
    if budget.get("month") != month:
        budget = {"month": month, "cpu_seconds": 0.0, "runs": 0, "skipped": 0}
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nxt = (start + timedelta(days=32)).replace(day=1)
    elapsed = max((now - start).total_seconds(), 3600) / (nxt - start).total_seconds()
    projected = budget["cpu_seconds"] / elapsed
    budget["projected_cpu_hours"] = round(projected / 3600, 2)
    return projected <= MONTHLY_CPU_BUDGET, budget


async def run_cloud_tick(ledger: Optional[Ledger] = None, config_path: Optional[str] = None,
                         client: Optional[KalshiClient] = None, feed: Optional[CryptoFeed] = None) -> dict:
    global _last_cpu_reading
    started = time.time()
    cfg = DeskConfig.load(config_path or str(Path(__file__).resolve().parent.parent / "desk.yaml"))
    for k, v in CLOUD_OVERRIDES.items():
        setattr(cfg, k, v)
    ledger = ledger or Ledger(cfg.db_path)

    if not ledger.try_lease(LEASE, LEASE_SECONDS):
        return {"ok": False, "skipped": "another run is in progress"}

    try:
        state = ledger.get_status(STATE_KEY) or {}
        now = datetime.now(timezone.utc)
        within_budget, budget = _budget_check(state, now)
        if not within_budget:
            budget["skipped"] = budget.get("skipped", 0) + 1
            state["budget"] = budget
            ledger.set_status(STATE_KEY, state)
            return {"ok": True, "skipped": "monthly CPU budget pacing", "budget": budget}

        if state.get("season", 1) != ledger.season:
            # The website started a new season: everyone begins fresh
            state = {"budget": state.get("budget"), "feed": state.get("feed"), "fees": state.get("fees")}
        accounts = load_accounts(state["accounts"]) if state.get("accounts") else None

        feed = feed or CryptoFeed(tuple(cfg.crypto_symbols))
        load_feed(feed, state.get("feed") or {})
        client = client or KalshiClient(env=cfg.env, requests_per_second=cfg.requests_per_second)
        # strategies=None: staff the desk from the HR roster (desk.yaml + website overrides)
        desk = Desk(cfg, client, None, ledger, feed=feed, accounts=accounts)
        from desk.paper.broker import RestingOrder

        desk.broker.resting = [RestingOrder(**o) for o in state.get("resting") or []]
        desk.broker.sync_resting_views()
        strategies = desk.strategies
        for s in strategies:
            if s.key in (state.get("strategies") or {}):
                s.set_state(state["strategies"][s.key])

        t = state.get("timers") or {}
        desk._last_universe = _dt(t.get("universe"))
        desk._last_slow = _dt(t.get("slow"))
        desk._last_equity = _dt(t.get("equity"))
        desk._last_accuracy = _dt(t.get("accuracy"))
        desk.started_at = _dt(state.get("started_at")) or desk.started_at
        desk.tick_count = state.get("tick_count", 0)
        desk.marks = state.get("marks") or {}
        desk.fees = {k: FeeSchedule(*v) for k, v in (state.get("fees") or {}).items()}
        peaks = state.get("peaks") or {}
        desk.drawdowns = {k: v[1] for k, v in peaks.items()}
        desk.briers = state.get("briers") or {}
        from desk.paper.pool import PoolState

        desk.pool.state = PoolState.from_dict(state.get("pool"))

        try:
            results = await desk.tick()
        finally:
            await client.close()
            await feed.close()

        # Track each employee's peak equity and worst drop from it
        for k, acct in desk.accounts.items():
            eq = acct.equity(desk.marks)
            peak, worst = peaks.get(k, [eq, 0.0])
            peak = max(peak, eq)
            worst = max(worst, (peak - eq) / peak if peak > 0 else 0.0)
            peaks[k] = [peak, worst]

        held = {t for a in desk.accounts.values() for t in a.open_tickers}
        cpu_now = _cpu_seconds()
        used = cpu_now - _last_cpu_reading
        _last_cpu_reading = cpu_now
        budget["cpu_seconds"] = budget["cpu_seconds"] + used
        budget["runs"] = budget.get("runs", 0) + 1

        state = {
            "season": ledger.season,
            "accounts": dump_accounts(desk.accounts),
            "resting": [asdict(o) for o in desk.broker.resting],
            "feed": dump_feed(feed),
            "strategies": {s.key: st for s in desk.strategies if (st := s.get_state()) is not None},
            "timers": {"universe": _iso(desk._last_universe), "slow": _iso(desk._last_slow),
                       "equity": _iso(desk._last_equity), "accuracy": _iso(desk._last_accuracy)},
            "started_at": _iso(desk.started_at),
            "tick_count": desk.tick_count,
            "marks": {t: m for t, m in desk.marks.items() if t in held},
            "fees": {k: [f.fee_type, f.multiplier] for k, f in desk.fees.items()},
            "peaks": peaks,
            "pool": desk.pool.state.to_dict(),
            "briers": desk.briers,
            "budget": budget,
            "last_run": {"at": now.isoformat(), "seconds": round(time.time() - started, 1),
                         "cpu_seconds": round(used, 3)},
        }
        ledger.set_status(STATE_KEY, state)
        return {
            "ok": True,
            "fills": sum(len(r.fills) for r in results if r.filled),
            "seconds": round(time.time() - started, 1),
            "cpu_seconds": round(used, 3),
            "budget": budget,
        }
    finally:
        ledger.release_lease(LEASE)
