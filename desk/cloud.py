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
import os
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
# seconds; Vercel Hobby includes 4 CPU-hours (dashboard uses some). 0: no budget (the server, `desk tick`, 11-16)
MONTHLY_CPU_BUDGET = float(os.getenv("DESK_CPU_BUDGET_HOURS", "3")) * 3600

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
    mine = set(feed.symbols)  # coins the desk no longer watches are dropped
    return {
        "history": {s: [[t.isoformat(), p] for t, p in h if t >= cutoff] for s, h in feed.history.items() if s in mine},
        "quotes": {s: {"iv": q.implied_vol, "rv": q.realized_vol, "spot": q.spot, "at": q.fetched_at.isoformat()}
                   for s, q in feed.quotes.items() if s in mine},
        "vol_refreshed": {s: t.isoformat() for s, t in feed._vol_refreshed.items() if s in mine},
    }


def load_feed(feed: CryptoFeed, data: dict) -> None:
    mine = set(feed.symbols)
    for s, pts in (data.get("history") or {}).items():
        if s in mine:
            feed.history[s] = deque(((datetime.fromisoformat(t), p) for t, p in pts), maxlen=2000)
    for s, q in (data.get("quotes") or {}).items():
        if s in mine:
            # Keep when the price was fetched: a saved price is not a fresh one
            at = _dt(q.get("at")) or datetime(2000, 1, 1, tzinfo=timezone.utc)
            feed.quotes[s] = UnderlyingQuote(s, spot=q["spot"], implied_vol=q["iv"], realized_vol=q["rv"], fetched_at=at)
    feed._vol_refreshed = {s: datetime.fromisoformat(t) for s, t in (data.get("vol_refreshed") or {}).items()
                           if s in mine}


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------


def _budget_check(state: dict, now: datetime) -> tuple[bool, dict]:
    """Is this month on pace to stay under the CPU budget?"""
    if MONTHLY_CPU_BUDGET <= 0:
        return True, state.get("budget") or {}
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


def restore_desk(cfg: DeskConfig, ledger: Ledger, client: KalshiClient, feed: CryptoFeed, state: dict) -> Desk:
    """A Desk picked up where the saved state left off (paper accounts, resting bids, timers, pool)."""
    from desk.paper.broker import RestingOrder
    from desk.paper.pool import PoolState

    accounts = load_accounts(state["accounts"]) if state.get("accounts") else None
    load_feed(feed, state.get("feed") or {})
    # strategies=None: staff the desk from the HR roster (desk.yaml + website overrides)
    desk = Desk(cfg, client, None, ledger, feed=feed, accounts=accounts)
    desk.broker.resting = [RestingOrder(**o) for o in state.get("resting") or []]
    desk.broker.sync_resting_views()
    for s in desk.strategies:
        if s.key in (state.get("strategies") or {}):
            s.set_state(state["strategies"][s.key])

    t = state.get("timers") or {}
    desk._last_universe = _dt(t.get("universe"))
    desk._last_slow = _dt(t.get("slow"))
    desk._last_equity = _dt(t.get("equity"))
    desk._last_accuracy = _dt(t.get("accuracy"))
    desk._last_prune = _dt(t.get("prune"))
    # Known windows, so "Crypto events: ..." is only logged when they change
    desk.crypto_event_tickers = list(state.get("crypto_events") or [])
    desk.started_at = _dt(state.get("started_at")) or desk.started_at
    desk.tick_count = state.get("tick_count", 0)
    desk.marks = state.get("marks") or {}
    desk.fees = {k: FeeSchedule(*v) for k, v in (state.get("fees") or {}).items()}
    desk.peaks = state.get("peaks") or {}
    desk.drawdowns = {k: v[1] for k, v in desk.peaks.items()}
    desk.briers = state.get("briers") or {}
    desk.pool.state = PoolState.from_dict(state.get("pool"))
    return desk


def saved_state(desk: Desk, feed: CryptoFeed, old: dict) -> dict:
    """The state to save after a run (restore_desk reads it back); the budget and last run carry over from `old`."""
    cfg = desk.config
    # Track each employee's peak equity and worst drop from it
    peaks = getattr(desk, "peaks", None) or {}
    for k, acct in desk.accounts.items():
        eq = acct.equity(desk.marks)
        peak, worst = peaks.get(k, [eq, 0.0])
        peak = max(peak, eq)
        worst = max(worst, (peak - eq) / peak if peak > 0 else 0.0)
        peaks[k] = [peak, worst]
    desk.peaks = peaks
    held = {t for a in desk.accounts.values() for t in a.open_tickers}
    return {
        "season": desk.ledger.season,
        "accounts": dump_accounts(desk.accounts),
        "resting": [asdict(o) for o in desk.broker.resting],
        "feed": dump_feed(feed),
        "strategies": {s.key: st for s in desk.strategies if (st := s.get_state()) is not None},
        "timers": {"universe": _iso(desk._last_universe), "slow": _iso(desk._last_slow),
                   "equity": _iso(desk._last_equity), "accuracy": _iso(desk._last_accuracy),
                   "prune": _iso(desk._last_prune)},
        "crypto_events": desk.crypto_event_tickers,
        "started_at": _iso(desk.started_at),
        "tick_count": desk.tick_count,
        "marks": {t: m for t, m in desk.marks.items() if t in held},
        # Only series the desk trades or still holds (old seasons' sports fees pile up otherwise)
        "fees": {k: [f.fee_type, f.multiplier] for k, f in desk.fees.items()
                 if k in cfg.crypto_series or k in {t.split("-", 1)[0] for t in held}},
        "peaks": peaks,
        "pool": desk.pool.state.to_dict(),
        "briers": desk.briers,
        "budget": old.get("budget"),
        "last_run": old.get("last_run"),
    }


async def run_cloud_tick(ledger: Optional[Ledger] = None, config_path: Optional[str] = None,
                         client: Optional[KalshiClient] = None, feed: Optional[CryptoFeed] = None) -> dict:
    global _last_cpu_reading
    started = time.time()
    cfg = DeskConfig.load(config_path or str(Path(__file__).resolve().parent.parent / "desk.yaml"))
    for k, v in CLOUD_OVERRIDES.items():
        setattr(cfg, k, v)
    ledger = ledger or Ledger(cfg.db_path, cfg.schema)

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
        feed = feed or CryptoFeed(tuple(cfg.crypto_symbols))
        if client is None:
            if cfg.trading == "live":
                from desk.live import live_client

                client = live_client(cfg)  # refuses (and the run fails loudly) unless safely set up
            else:
                client = KalshiClient(env=cfg.env, requests_per_second=cfg.requests_per_second)
        desk = restore_desk(cfg, ledger, client, feed, state)

        try:
            results = await desk.tick()
        finally:
            await client.close()
            await feed.close()

        cpu_now = _cpu_seconds()
        used = cpu_now - _last_cpu_reading
        _last_cpu_reading = cpu_now
        budget["cpu_seconds"] = budget["cpu_seconds"] + used
        budget["runs"] = budget.get("runs", 0) + 1
        state = saved_state(desk, feed, state)
        state["budget"] = budget
        state["last_run"] = {"at": now.isoformat(), "seconds": round(time.time() - started, 1),
                             "cpu_seconds": round(used, 3)}
        ledger.set_status(STATE_KEY, state)
        journal = desk.journal.summary()
        return {
            "ok": True,
            "fills": sum(len(r.fills) for r in results if r.filled),
            "warnings": journal["warnings"],
            "seconds": round(time.time() - started, 1),
            "cpu_seconds": round(used, 3),
            "budget": budget,
        }
    finally:
        ledger.release_lease(LEASE)


async def run_all_books(config_path: Optional[str] = None) -> dict:
    """One run of every book: the real-money book first (if desk.yaml names one), then the pretend
    pool. Each has its own ledger schema and lease; one failing never stops the other."""
    from desk.live.guard import ENV_SWITCH, env_allows_live

    path = Path(config_path or Path(__file__).resolve().parent.parent / "desk.yaml")
    cfg = DeskConfig.load(path)
    out: dict = {}
    if cfg.real_book:
        real_path = path.parent / cfg.real_book
        if not real_path.exists():
            # Never fall back to defaults: that would be a second, misconfigured pretend run
            raise FileNotFoundError(f"real book config {real_path} is missing (is it in vercel.json includeFiles?)")
        if DeskConfig.load(real_path).trading == "live" and not env_allows_live():
            # Not set up on this host yet: wait quietly rather than fail every run
            out["real"] = {"ok": True, "skipped": f"{ENV_SWITCH}=yes isn't set on the bot"}
        else:
            try:
                out["real"] = await run_cloud_tick(config_path=str(real_path))
            except Exception as e:  # e.g. the API key is missing: report it, keep the pretend pool running
                logger.exception("real book failed")
                out["real"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    out["pretend"] = await run_cloud_tick(config_path=str(path))
    return {"ok": all(r.get("ok") for r in out.values()), **out}


def reset_pool_day(ledger: Ledger, equity: float) -> Optional[dict]:
    """
    Start the pool's day (and its high-water mark) over at `equity`: for when the saved
    day-open or peak is wrong (e.g. money that left and came back counted twice), which
    would otherwise hold a false daily stop until midnight. Waits its turn with the bot's runs.
    Returns the new pool state, or None if a run is in progress (try again in a minute).
    """
    from desk.paper.pool import PoolState

    if not ledger.try_lease(LEASE, LEASE_SECONDS):
        return None
    try:
        state = ledger.get_status(STATE_KEY) or {}
        pool = PoolState.from_dict(state.get("pool"))
        pool.day_open = pool.peak = equity
        pool.stopped_at = None
        state["pool"] = pool.to_dict()
        ledger.set_status(STATE_KEY, state)
        ledger.record_event("trading", {"action": "pool day reset", "equity": round(equity, 2)})
        return state["pool"]
    finally:
        ledger.release_lease(LEASE)
