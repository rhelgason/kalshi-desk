"""
Command line for the desk.

    python -m desk scan          one look at the market: what would each employee do?
    python -m desk paper         run the paper-trading loop (Ctrl+C to stop)
    python -m desk report        scoreboard from the saved ledger
    python -m desk accuracy      are each employee's probabilities any good?
    python -m desk backtest      replay the last N days of settled markets with every employee
    python -m desk tune EMPLOYEE --set param=v1,v2   search settings with a train/test split
    python -m desk jobs          background jobs: history sync, archive backfill, autotuning
    python -m desk review --days 30   performance review of every employee (Markdown)
    python -m desk new-season --level heavy_maker=Senior ...     fresh start: split the office pool
    python -m desk seed-season --days 30 --history data/research.db [--apply]   new season as if started N days ago
    python -m desk log --hours 6 what the bot did each run (bets, skips and why, warnings)
    python -m desk health        is the hosted bot running? (exit 1 if it has gone quiet)
    python -m desk live-check [--order]   test the Kalshi API key; --order places and cancels a tiny bid
                      [--fund]    move the cash to the crypto shard, where bitcoin bets are paid from
    python -m desk halt "why" [--long] / resume    the real-money kill switch
    python -m desk employees     who works here
    python -m desk whoami        check your Kalshi API key (read-only)
    python -m desk fast          the always-on Fast Sadie and her 2-minute twin (the DigitalOcean server)
    python -m desk fast-report   is the server worth it? month by month, net of its cost
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from desk.config import DeskConfig
from desk.feeds.crypto import CryptoFeed
from desk.kalshi.auth import KalshiSigner
from desk.kalshi.client import KalshiClient
from desk.kalshi.models import Side
from desk.paper.ledger import Ledger, is_postgres
from desk.paper.scoreboard import format_scoreboard, scoreboard_rows
from desk.runner import Desk
from desk.strategies import REGISTRY, build_strategies
from desk.strategies.fair_value import CryptoFairValue


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _make_desk(cfg: DeskConfig, ledger: Ledger, record: str | None = None) -> Desk:
    if cfg.trading == "live":
        from desk.live import live_client

        client = live_client(cfg)
    else:
        client = KalshiClient(env=cfg.env, requests_per_second=cfg.requests_per_second)
    feed = CryptoFeed(tuple(cfg.crypto_symbols))
    # None = staff from the HR roster (desk.yaml + website overrides, minus fired employees)
    return Desk(cfg, client, None, ledger, feed=feed, record_path=record)


async def cmd_scan(cfg: DeskConfig) -> None:
    desk = _make_desk(cfg, Ledger(":memory:"))
    try:
        await desk.refresh_universe()
        snap = await desk.build_snapshot()

        print(f"\nScanned {len(snap.markets)} markets at {snap.now:%Y-%m-%d %H:%M UTC}")
        for sym, q in snap.underlyings.items():
            iv = f"{q.implied_vol:.0%}" if q.implied_vol else "?"
            rv = f"{q.realized_vol:.0%}" if q.realized_vol else "?"
            print(f"  {sym}: ${q.spot:,.2f}  implied vol {iv}  realized vol {rv}  sources {q.sources}")

        # Model vs market for the nearest BTC strikes
        fv = next((s for s in desk.strategies if isinstance(s, CryptoFairValue)), CryptoFairValue())
        btc = snap.underlyings.get("BTC")
        ladder = [m for m in snap.markets.values()
                  if m.series_ticker == "KXBTCD" and m.is_tradeable and m.floor_strike]
        if btc and ladder:
            soonest = min(m.close_time for m in ladder)
            ladder = sorted((m for m in ladder if m.close_time == soonest),
                            key=lambda m: abs(m.floor_strike - btc.spot))[:9]
            mins = (soonest - snap.now).total_seconds() / 60
            print(f"\nBTC above/below, closing in {mins:.0f} min: model vs market")
            print(f"  {'strike':>12} {'model':>7} {'bid':>6} {'ask':>6}  verdict")
            for m in sorted(ladder, key=lambda m: m.floor_strike):
                q = fv.model_prob(m, snap)
                if q is None:
                    continue
                verdict = ""
                if m.ask(Side.YES) and q - m.ask(Side.YES) > 0.02:
                    verdict = "YES looks cheap"
                elif m.ask(Side.NO) and (1 - q) - m.ask(Side.NO) > 0.02:
                    verdict = "NO looks cheap"
                print(f"  {m.floor_strike:>12,.2f} {q:>7.1%} {m.yes_bid:>6.2f} {m.yes_ask:>6.2f}  {verdict}")

        print("\nWhat each employee would do right now:")
        for strat in desk.strategies:
            intents = strat.evaluate(snap, desk.accounts[strat.key])
            print(f"\n  {strat.persona.emoji} {strat.persona.name} ({strat.key}): {len(intents)} idea(s)")
            for i in sorted(intents, key=lambda i: i.expected_edge, reverse=True)[:5]:
                edge = f" edge {i.expected_edge:+.3f}/contract" if i.expected_edge else ""
                print(f"     - {i.reason}{edge}")
        print()
    finally:
        await desk.client.close()
        if desk.feed:
            await desk.feed.close()


async def cmd_paper(cfg: DeskConfig, record: str | None) -> None:
    ledger = Ledger(cfg.db_path, cfg.schema)
    desk = _make_desk(cfg, ledger, record)
    try:
        await desk.run_forever()
    finally:
        print("\n" + desk.scoreboard())
        await desk.client.close()
        if desk.feed:
            await desk.feed.close()
        ledger.close()


async def live_marks(cfg: DeskConfig, tickers: list[str]) -> dict[str, float]:
    """Current YES mid (or last trade) for each ticker, from Kalshi's public API."""
    marks: dict[str, float] = {}
    async with KalshiClient(env=cfg.env, requests_per_second=cfg.requests_per_second) as client:
        for i in range(0, len(tickers), 50):
            for m in await client.get_markets(tickers=tickers[i:i + 50], exclude_multivariate=False):
                if m.result in ("yes", "no"):
                    marks[m.ticker] = 1.0 if m.result == "yes" else 0.0
                elif m.mid is not None:
                    marks[m.ticker] = m.mid
                elif m.last_price:
                    marks[m.ticker] = m.last_price
    return marks


def cmd_report(cfg: DeskConfig, offline: bool) -> None:
    ledger = Ledger(cfg.db_path, cfg.schema)
    strategies = build_strategies(cfg.strategies)
    accounts = ledger.load_accounts(cfg.starting_cash, [s.key for s in strategies])
    personas = {s.key: f"{s.persona.emoji} {s.persona.name} ({s.key})" for s in strategies}
    marks = {}
    if not offline:
        held = sorted({t for a in accounts.values() for t in a.open_tickers})
        try:
            marks = asyncio.run(live_marks(cfg, held)) if held else {}
        except Exception as e:  # network trouble shouldn't kill the report
            print(f"(Couldn't fetch live prices: {e}; valuing open bets at price paid)")
    print(format_scoreboard(scoreboard_rows(accounts, ledger, marks), personas))
    if offline:
        print("\n(Open bets valued at the price paid, fees counted as spent.)")
    else:
        print(f"\n(Open bets valued at current Kalshi prices: {len(marks)} markets.)")


def cmd_accuracy(cfg: DeskConfig, db: str | None, detail: str | None) -> None:
    from desk.paper.accuracy import accuracy_report, format_accuracy

    ledger = Ledger(db or cfg.db_path, cfg.schema)
    strategies = build_strategies(cfg.strategies)
    personas = {s.key: f"{s.persona.emoji} {s.persona.name} ({s.key})" for s in strategies}
    summaries = accuracy_report(ledger, [s.key for s in strategies])
    if not summaries:
        print("No settled bets yet. Check back after some markets settle.")
        return
    print(format_accuracy(summaries, personas, detail))


async def cmd_backtest(cfg: DeskConfig, days: float, series: list[str], fill_delay: int,
                       depth: float, only: list[str] | None, save: bool) -> None:
    import json
    import sqlite3
    import time
    from datetime import datetime, timezone
    from pathlib import Path

    from desk.backtest import Backtest, BacktestConfig, load_backtest_data
    from desk.paper.accuracy import accuracy_report, format_accuracy

    strat_cfg = {k: dict(v or {}) for k, v in cfg.strategies.items()}
    strat_cfg.setdefault("dart_monkey", {})["seed"] = 42  # reproducible darts
    strategies = [s for s in build_strategies(strat_cfg) if not only or s.key in only]
    personas = {s.key: f"{s.persona.emoji} {s.persona.name} ({s.key})" for s in strategies}

    async with KalshiClient(env=cfg.env, requests_per_second=cfg.requests_per_second) as client:
        data = await load_backtest_data(client, series, days)
        fees = {s: await client.get_fee_schedule(s) for s in series}

    bt = Backtest(data, strategies, BacktestConfig(
        starting_cash=cfg.starting_cash, depth=depth, fill_delay=fill_delay, fees=fees))
    t0 = time.time()
    bt.run()
    settled = sum(1 for hm in data.markets if hm.yes_value is not None)
    print(f"\nBacktest: {days:g} days, {settled} settled markets in {', '.join(series)}, "
          f"fill delay {fill_delay} min, depth {depth:g} ({time.time() - t0:.1f}s)")
    print(f"{bt.stats['fills']} fills from {bt.stats['intents']} trade ideas\n")
    print(format_scoreboard(scoreboard_rows(bt.accounts, bt.ledger), personas))
    summaries = accuracy_report(bt.ledger, [s.key for s in strategies])
    print()
    print(format_accuracy(summaries, personas))

    if save:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out = Path("data/backtests")
        out.mkdir(parents=True, exist_ok=True)
        dest = sqlite3.connect(out / f"{stamp}.db")
        bt.ledger.db.backup(dest)
        dest.close()
        summary = {
            "id": stamp, "days": days, "series": series, "fill_delay": fill_delay, "depth": depth,
            "settled_markets": settled, "stats": bt.stats,
            "scoreboard": [{**r.__dict__, "pnl": r.pnl, "roi": r.roi, "win_rate": r.win_rate}
                           for r in scoreboard_rows(bt.accounts, bt.ledger)],
            "accuracy": [s.to_dict() for s in summaries],
        }
        summary["equity"] = {
            s.key: [(ts, round(eq, 2)) for ts, eq in bt.ledger.equity_curve(s.key)] for s in strategies
        }
        summary["employees"] = [{"key": s.key, "name": s.persona.name, "emoji": s.persona.emoji}
                                for s in strategies]
        (out / f"{stamp}.json").write_text(json.dumps(summary, indent=1, default=str))
        if is_postgres(cfg.db_path):
            Ledger(cfg.db_path, cfg.schema).save_backtest(stamp, summary)
            print("Uploaded summary to the dashboard database.")
        print(f"\nSaved to data/backtests/{stamp}.db and .json "
              f"(try: python -m desk accuracy --db data/backtests/{stamp}.db --employee fair_value)")


def cmd_migrate(cfg: DeskConfig, source: str, upload_backtests: bool) -> None:
    import json
    from pathlib import Path

    if not is_postgres(cfg.db_path):
        print("Set DATABASE_URL (in .env) to your Postgres connection string first.")
        return
    dest = Ledger(cfg.db_path, cfg.schema)
    if Path(source).exists():
        if dest.fills():
            print("Destination already has fills; skipping ledger copy to avoid duplicates.")
        else:
            counts = Ledger(source).copy_to(dest)
            print(f"Copied {source} -> Postgres: {counts}")
    if upload_backtests:
        for f in sorted(Path("data/backtests").glob("*.json")):
            dest.save_backtest(f.stem, json.loads(f.read_text()))
            print(f"Uploaded backtest {f.stem}")


async def cmd_tune(cfg: DeskConfig, employee: str, sets: list[str], days: float, series: list[str],
                   fill_delay: int, depth: float, top: int) -> None:
    import json
    from datetime import datetime, timezone
    from pathlib import Path

    from desk.backtest import BacktestConfig, load_backtest_data
    from desk.backtest.tune import format_tune, parse_grid, tune

    if employee not in REGISTRY:
        print(f"Unknown employee {employee!r}. Try: {', '.join(REGISTRY)}")
        return
    base = {k: v for k, v in (cfg.strategies.get(employee) or {}).items() if k != "enabled"}
    if employee == "dart_monkey":
        base["seed"] = 42
    grid = parse_grid(sets)
    async with KalshiClient(env=cfg.env, requests_per_second=cfg.requests_per_second) as client:
        data = await load_backtest_data(client, series, days)
        fees = {s: await client.get_fee_schedule(s) for s in series}
    bt_cfg = BacktestConfig(starting_cash=cfg.starting_cash, depth=depth, fill_delay=fill_delay, fees=fees)
    rows = tune(employee, base, grid, data, bt_cfg)
    persona = REGISTRY[employee].persona
    print(f"\nTuning {persona.emoji} {persona.name} on {days:g} days of {', '.join(series)} "
          f"(train first 2/3, test last 1/3; fill delay {fill_delay} min)")
    print(f"Base settings from desk.yaml: {base or '(defaults)'}\n")
    print(format_tune(rows, top))
    out = Path("data/tuning")
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    (out / f"{employee}-{stamp}.json").write_text(json.dumps(
        [{"params": r.params, "train": r.train.__dict__, "test": r.test.__dict__} for r in rows], indent=1))


async def cmd_jobs(cfg: DeskConfig, backfill_minutes: float, force_tune: bool) -> None:
    import json

    from desk.jobs import run_jobs

    if not is_postgres(cfg.db_path):
        print("Jobs need the shared database: set DATABASE_URL.")
        return
    report = await run_jobs(cfg, backfill_seconds=backfill_minutes * 60, force_tune=force_tune)
    print(json.dumps(report, indent=1, default=str))


def cmd_review(cfg: DeskConfig, days: float, out: str | None) -> None:
    from pathlib import Path

    from desk.review import build_review

    text = build_review(Ledger(cfg.db_path, cfg.schema), days)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text)
        print(f"Saved to {out}")
    else:
        print(text)


def cmd_new_season(cfg: DeskConfig, pool: float | None, levels: list[str], why: str) -> None:
    from desk import hr

    ledger = Ledger(cfg.db_path, cfg.schema)
    titles = {t.lower(): i for i, (t, _) in enumerate(hr.LEVELS)}
    wanted = {}
    for item in levels:
        key, _, title = item.partition("=")
        if key not in REGISTRY or title.lower() not in titles:
            raise SystemExit(f"Can't read --level {item!r}: use employee_key=Intern|Associate|Senior|VP|Partner")
        wanted[key] = titles[title.lower()]
    roster = hr.load_roster(ledger, list(REGISTRY))
    config = hr.effective_strategy_config(cfg.strategies, roster, hr.load_policy(ledger).get("hired") or ())
    staff = [k for k in REGISTRY if (config.get(k) or {}).get("enabled", True) and roster[k].status != "fired"]
    if cfg.trading == "live":
        # Real-money book: the pool IS the Kalshi account, so its numbers are Kalshi's from the start
        if pool is not None:
            raise SystemExit("A live book's pool is whatever is in the Kalshi account: leave out --pool")
        pool = asyncio.run(_kalshi_pool(cfg))
    detail = hr.start_season(ledger, staff, cfg.pool_cash if pool is None else pool, cfg.starting_cash, wanted, why)
    print(f"Season {detail['season']} started: ${detail['pool']:,.2f} office pool shared by "
          f"{len(detail['members'])} employees ({', '.join(detail['members'])})")


async def cmd_seed_season(cfg: DeskConfig, days: float, history: str, slippage: list[str], why: str,
                          apply: bool, until: str | None = None, max_bet: float | None = None) -> None:
    """Replay this book's staff over the last `days` of stored markets; with --apply, make it the new season."""
    import json
    from collections import defaultdict
    from datetime import datetime, timedelta, timezone

    from desk import hr
    from desk.backtest.seed import SeasonReplay, write_season
    from desk.backtest.store import load_from_store
    from desk.cloud import LEASE, LEASE_SECONDS, STATE_KEY

    if cfg.trading == "live":
        raise SystemExit("seed-season is for the pretend book: a real-money book's history is Kalshi's")
    ledger = Ledger(cfg.db_path, cfg.schema)
    roster = hr.load_roster(ledger, list(REGISTRY))
    config = hr.effective_strategy_config(cfg.strategies, roster)
    staff = [k for k in REGISTRY if (config.get(k) or {}).get("enabled", True) and roster[k].status != "fired"]
    members = {k for k in staff if not roster[k].control}
    # Only the pool is replayed; the control group (yardsticks with their own money) starts today
    strategies = [REGISTRY[k](**{p: v for p, v in config[k].items() if p != "enabled"}) for k in staff if k in members]
    slip = {k: float(v) for k, _, v in (item.partition("=") for item in slippage)}

    store = Ledger(history)
    last = max(int(r["t"] or 0) for r in store._rows(
        "SELECT max(close_ts) AS t FROM market_history WHERE series IN (%s)" % ",".join("?" * len(cfg.crypto_series)),
        tuple(cfg.crypto_series)))
    end = datetime.fromtimestamp(last, timezone.utc)
    if until:  # a dry run over an earlier stretch, to see how much of the result is luck
        if apply:
            raise SystemExit("--until is for dry runs: a seeded season always ends now")
        end = min(end, datetime.fromisoformat(until).replace(tzinfo=timezone.utc))
    start = end - timedelta(days=days)
    data = load_from_store(store, cfg.crypto_series, start, end)
    async with KalshiClient(env=cfg.env, requests_per_second=cfg.requests_per_second) as client:
        fees = {s: await client.get_fee_schedule(s) for s in cfg.crypto_series}
    policy = hr.load_policy(ledger)
    replay = SeasonReplay(data, strategies, members, {k: roster[k].multiplier for k in staff}, policy["pool"],
                          cfg.pool_cash, cfg.starting_cash, fees, slippage=slip, max_bet=max_bet)
    replay.run()

    print(f"\nReplay {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M} UTC, {', '.join(cfg.crypto_series)}; "
          f"pool ${cfg.pool_cash:,.0f} shared by {', '.join(sorted(members))}; slippage {slip or 'none'}"
          f"{f'; bets capped at ${max_bet:g}' if max_bet else ''}")
    print(f"{replay.stats['fills']} bets from {replay.stats['intents']} ideas\n")
    print(format_scoreboard(scoreboard_rows(replay.accounts, replay.ledger)))
    pool_end = sum(replay.accounts[k].equity({}) for k in members)
    by_day = defaultdict(float)
    for r in replay.ledger._rows("SELECT ts, strategy, pnl FROM settlements"):
        if r["strategy"] in members:
            by_day[r["ts"][:10]] += r["pnl"]
    print(f"\nPool: ${cfg.pool_cash:,.2f} -> ${pool_end:,.2f}; up days {sum(v > 0 for v in by_day.values())} "
          f"of {len(by_day)}; worst day ${min(by_day.values(), default=0):+,.2f}, best ${max(by_day.values(), default=0):+,.2f}")
    if not apply:
        print("\nDry run: nothing written. Add --apply to make this the new season.")
        return

    if not ledger.try_lease(LEASE, LEASE_SECONDS):
        raise SystemExit("A bot run is in progress; try again in a minute.")
    try:
        detail = hr.start_season(ledger, staff, cfg.pool_cash, cfg.starting_cash,
                                 why=why or f"replayed from the last {days:g} days of markets")
        written = write_season(replay, ledger, detail["season"])
        # The bot picks up the replay's day and high-water mark instead of starting them over
        state = ledger.get_status(STATE_KEY) or {}
        ledger.set_status(STATE_KEY, {"season": detail["season"], "budget": state.get("budget"),
                                      "feed": state.get("feed"), "fees": state.get("fees"),
                                      "pool": replay.pool.state.to_dict()})
        ledger.record_event("season", {"action": "seeded from a replay", "season": detail["season"],
                                       "from": start.isoformat(), "to": end.isoformat(), "days": days,
                                       "pool_start": cfg.pool_cash, "pool_end": round(pool_end, 2), "max_bet": max_bet,
                                       "slippage": slip, **written})
    finally:
        ledger.release_lease(LEASE)
    print(f"\nSeason {detail['season']} seeded: {json.dumps(written)}. The bot carries on from here.")


async def _kalshi_pool(cfg: DeskConfig) -> float:
    """The Kalshi account's cash, for a live season's pool. Refuses while bets are open or waiting."""
    from desk.live import live_client

    async with live_client(cfg) as client:
        open_bets = [p for p in await client.get_positions() if abs(float(p.get("position_fp") or 0)) > 0.005]
        waiting = await client.get_orders(status="resting")
        if open_bets or waiting:
            raise SystemExit(f"Kalshi still has {len(open_bets)} open bets and {len(waiting)} waiting orders: "
                             "let them finish (or cancel them) before starting a new live season")
        cash = await client.get_balance()
    print(f"Kalshi ({cfg.env}) holds ${cash:,.2f}: that's the pool")
    return cash


def cmd_log(cfg: DeskConfig, hours: float, verbose: bool, employee: str | None) -> None:
    from datetime import datetime, timedelta, timezone

    from desk.journal import format_runs

    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = Ledger(cfg.db_path, cfg.schema).recent_runs(since)
    if employee:
        for r in rows:
            r["summary"]["employees"] = {k: v for k, v in (r["summary"].get("employees") or {}).items() if k == employee}
    print(format_runs(rows, verbose=verbose))
    errors = Ledger(cfg.db_path, cfg.schema)._rows("SELECT ts, detail FROM events WHERE kind = 'error' AND ts >= ? ORDER BY id",
                                       (since,))
    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  {e['ts'][:19]} {e['detail'][:300]}")


def cmd_health(cfg: DeskConfig, config_path: str = "desk.yaml", max_quiet_minutes: float = 15) -> int:
    from datetime import datetime, timedelta, timezone

    ledger = Ledger(cfg.db_path, cfg.schema)
    live = ledger.get_status("live")
    if not live:
        if cfg.book == "real":
            print("not running yet (waiting for its Kalshi key on the bot)")
            return 0
        print("The bot has never reported.")
        return 1
    quiet = (datetime.now(timezone.utc) - datetime.fromisoformat(live["updated_at"])).total_seconds() / 60
    since = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    errors = ledger._rows("SELECT count(*) AS n FROM events WHERE kind = 'error' AND ts >= ?", (since,))[0]["n"]
    runs = ledger.recent_runs(since)
    warned = sum(1 for r in runs if r["summary"].get("warnings"))
    failed = sum(1 for r in runs if r["summary"].get("failed"))
    pool = live.get("pool") or {}
    print(f"Last report {quiet:.0f} min ago; {len(runs)} runs in 6h ({failed} failed, {warned} with warnings), "
          f"{errors} errors; pool ${pool.get('equity', 0):,.2f}")
    if quiet > max_quiet_minutes:
        print(f"UNHEALTHY: no report for {quiet:.0f} minutes")
        return 1
    if cfg.real_book:
        # The real-money book runs on the same schedule: it has to be reporting too
        real_path = Path(config_path).parent / cfg.real_book
        real = DeskConfig.load(real_path)
        print(f"{real.book.title()} book ({real.env}): ", end="")
        return cmd_health(real, str(real_path), max_quiet_minutes)
    return 0


CRYPTO_SHARD = 2  # Kalshi trades crypto markets on exchange shard 2


async def cmd_live_check(cfg: DeskConfig, order: bool, fund: bool = False) -> int:
    """Check the API key, balance and positions; with --order, place and cancel one tiny resting bid.
    With --fund, move the account's cash onto the crypto shard (and keep it there)."""
    import time

    signer = KalshiSigner.from_env()
    if not signer:
        print("No API key: set KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH (or KALSHI_PRIVATE_KEY) in .env")
        return 1
    async with KalshiClient(env=cfg.env, signer=signer, allow_trading=order,
                            requests_per_second=cfg.requests_per_second) as client:
        print(f"Exchange: {cfg.env} ({client.base_url})")
        print(f"Balance: ${await client.get_balance():,.2f}")
        shards = await client.get_shard_balances()
        if len([v for v in shards.values() if v > 0.005]) > 1 or not shards.get(CRYPTO_SHARD, 0) > 0.005:
            print("  by shard: " + ", ".join(f"#{k} ${v:,.2f}" for k, v in sorted(shards.items())))
        target = await client.get_target_allocation()
        if fund:
            moved = sum(v for k, v in shards.items() if k != CRYPTO_SHARD)
            for k, v in shards.items():
                if k != CRYPTO_SHARD and v >= 0.01:
                    await client.transfer_between_shards(v, k, CRYPTO_SHARD)
            await client.set_target_allocation({CRYPTO_SHARD: 100})
            print(f"Moved ${moved:,.2f} to shard {CRYPTO_SHARD} (crypto) and told Kalshi to keep new deposits there.")
        elif shards.get(CRYPTO_SHARD, 0) < 0.005 or target != {CRYPTO_SHARD: 100}:
            print(f"  Bitcoin markets are paid from shard {CRYPTO_SHARD}, which has "
                  f"${shards.get(CRYPTO_SHARD, 0):,.2f}. Run with --fund to move the cash there.")
        positions = [p for p in await client.get_positions() if abs(float(p.get('position_fp') or 0)) > 0.005]
        print(f"Open positions: {len(positions)}; resting orders: {len(await client.get_orders(status='resting'))}")
        if not order:
            print("Read-only checks passed. Add --order to place and cancel a tiny test bid.")
            return 0
        series = (cfg.crypto_series or ["KXBTC15M"])[0]
        events = await client.get_events(series_ticker=series, status="open", with_markets=True, max_items=5)
        market = next((m for e in events for m in e.markets if m.is_tradeable), None)
        if not market:
            print(f"No open {series} market to test on right now.")
            return 1
        # Half a contract at the lowest price: tests fractional counts; post-only so it can't buy anything now
        price = market.price_ranges[0][0] if market.price_ranges and market.price_ranges[0][0] > 0 else 0.01
        print(f"Placing a post-only bid: 0.5 YES contracts at ${price:.4f} on {market.ticker} ...")
        from desk.kalshi.client import KalshiAPIError

        try:
            resp = await client.create_order(market.ticker, Side.YES, 0.5, price, time_in_force="good_till_canceled",
                                             post_only=True, expiration_ts=int(time.time()) + 120)
        except KalshiAPIError as e:
            print(f"  Kalshi refused the order: {e}")
            if "shard balance" in str(e):
                print(f"  (The request itself was accepted; shard {market.exchange_index} has no cash. Try --fund.)")
            elif "balance" in str(e):
                print("  (The request itself was accepted; the account needs funds.)")
            return 1
        print(f"  accepted: order {resp.get('order_id')}, filled {resp.get('fill_count')}, "
              f"resting {resp.get('remaining_count')}")
        got = {}
        for _ in range(10):  # a new order takes Kalshi a few seconds to show up
            try:
                got = await client.get_order(resp["order_id"], market.ticker)
                break
            except KalshiAPIError as e:
                if e.status != 404:
                    raise
                await asyncio.sleep(1)
        print(f"  Kalshi shows: status {got.get('status')}, count {got.get('initial_count_fp')}, "
              f"price {got.get('yes_price_dollars')}")
        print(f"  cancelled: {(await client.cancel_order(resp['order_id'], market.ticker)).get('reduced_by')} contracts")
        print("Order checks passed: fractional counts, post-only, expiry and cancel all work.")
        return 0


def cmd_halt(cfg: DeskConfig, reason: str, resume: bool, long: bool = False) -> None:
    from desk.live.guard import Guard

    guard = Guard(Ledger(cfg.db_path, cfg.schema), cfg.live)
    if resume:
        guard.resume(by="command line")
        print("Real trading may resume on the bot's next run (books re-checked against Kalshi from scratch).")
    else:
        guard.halt(reason or "stopped from the command line", by="command line", long=long)
        print("Halted: no new real orders, and waiting ones are cancelled on the bot's next run (~2 minutes).")
        if long:
            print("Long pause: the phone widget and the dashboard show Training until you resume.")


def cmd_hire(cfg: DeskConfig, key: str, level: int, why: str) -> int:
    """Put a Training employee on this book mid-season (hr.hire): no new season, no yaml change."""
    from desk import hr

    cls = REGISTRY.get(key)
    if cls is None:
        print(f"No employee {key!r}: see `python -m desk employees`.")
        return 1
    coin = getattr(cls, "coin", "")
    if coin and coin not in cfg.crypto_symbols:
        print(f"{cls.persona.name} needs {coin} prices, which this book's feed doesn't fetch: add {coin} to "
              f"this book's crypto_symbols first.")
        return 1
    if hr.hire(Ledger(cfg.db_path, cfg.schema), key, level, why):
        print(f"{cls.persona.emoji} {cls.persona.name} hired as {hr.level_title(level)}: starts on the bot's next run "
              f"(~2 minutes) with $0 of the pool, betting from the shared pool like everyone else.")
    else:
        print(f"{cls.persona.name} is already hired on this book.")
    return 0


def cmd_employees() -> None:
    for key, cls in REGISTRY.items():
        p = cls.persona
        print(f"{p.emoji} {p.name:<20} {p.title:<18} [{key}]\n     {p.blurb}")


async def cmd_whoami(cfg: DeskConfig) -> None:
    signer = KalshiSigner.from_env()
    if not signer:
        print("No API key found. Set KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH (e.g. in a .env file).")
        return
    async with KalshiClient(env=cfg.env, signer=signer) as client:
        balance = await client.get_balance()
        positions = await client.get_positions()
        print(f"Connected to Kalshi {cfg.env}. Cash balance: ${balance:,.2f}. Open positions: {len(positions)}")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="desk", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="desk.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)
    # --config / -v also work after the command (python -m desk live-check --config desk.real.yaml)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=argparse.SUPPRESS)
    common.add_argument("-v", "--verbose", action="store_true", default=argparse.SUPPRESS)
    _add = sub.add_parser
    sub.add_parser = lambda *a, **kw: _add(*a, parents=[common], **kw)  # type: ignore[method-assign]
    sub.add_parser("scan")
    paper = sub.add_parser("paper")
    paper.add_argument("--record", help="also save market snapshots to this .jsonl.gz file")
    report = sub.add_parser("report")
    report.add_argument("--offline", action="store_true", help="don't fetch live prices for open bets")
    acc = sub.add_parser("accuracy", help="how good are each employee's probabilities?")
    acc.add_argument("--db", help="ledger to analyze (default: the paper ledger)")
    acc.add_argument("--employee", help="show calibration detail for one employee key")
    bt = sub.add_parser("backtest", help="replay settled Kalshi markets with every employee")
    bt.add_argument("--days", type=float, default=7)
    bt.add_argument("--series", default="KXBTC15M")
    bt.add_argument("--fill-delay", type=int, default=0, help="minutes between seeing a price and trading")
    bt.add_argument("--depth", type=float, default=100, help="contracts assumed available at the best quote")
    bt.add_argument("--only", help="comma-separated employee keys to include")
    bt.add_argument("--no-save", action="store_true")
    mig = sub.add_parser("migrate", help="copy the local ledger and backtests into Postgres (DATABASE_URL)")
    mig.add_argument("--from", dest="source", default="data/desk.db")
    mig.add_argument("--skip-backtests", action="store_true")
    tn = sub.add_parser("tune", help="search an employee's settings on history (train/test split)")
    tn.add_argument("employee")
    tn.add_argument("--set", action="append", default=[], metavar="PARAM=V1,V2,...",
                    help="values to try, e.g. --set min_edge=0.02,0.04 --set market_weight=0,0.5,0.8")
    tn.add_argument("--days", type=float, default=30)
    tn.add_argument("--series", default="KXBTC15M")
    tn.add_argument("--fill-delay", type=int, default=1)
    tn.add_argument("--depth", type=float, default=100)
    tn.add_argument("--top", type=int, default=15)
    jb = sub.add_parser("jobs", help="sync history, backfill the archive, autotune when due")
    jb.add_argument("--backfill-minutes", type=float, default=10)
    jb.add_argument("--force-tune", action="store_true")
    rv = sub.add_parser("review", help="performance review of every employee over the last N days")
    rv.add_argument("--days", type=float, default=30)
    rv.add_argument("--out", help="save the Markdown report here instead of printing it")
    ns = sub.add_parser("new-season", help="start everyone fresh with a new office pool")
    ns.add_argument("--pool", type=float, help="dollars in the office pool (default: pool_cash in desk.yaml; "
                    "a live book always uses the Kalshi balance)")
    ns.add_argument("--level", action="append", default=[], help="employee_key=Title, e.g. heavy_maker=Senior")
    ns.add_argument("--why", default="", help="the reason, for the HR log")
    sd = sub.add_parser("seed-season", help="start a new season as if this staff had begun N days ago (replay)")
    sd.add_argument("--days", type=float, default=30)
    sd.add_argument("--history", default="data/research.db", help="history store with the markets to replay")
    sd.add_argument("--slippage", action="append", default=[], help="SERIES=dollars per contract, e.g. KXSOL15M=0.005")
    sd.add_argument("--why", default="")
    sd.add_argument("--apply", action="store_true", help="write it (otherwise a dry run)")
    sd.add_argument("--until", help="dry run ending at this UTC date instead of now (e.g. 2026-09-24)")
    sd.add_argument("--max-bet", type=float, help="no replayed bet above this many dollars (like the real book's order cap)")
    lg = sub.add_parser("log", help="what the bot did each run: bets, skips and why, warnings, errors")
    lg.add_argument("--hours", type=float, default=6)
    lg.add_argument("--employee", help="only this employee key")
    lg.add_argument("--all", action="store_true", help="every run in detail, not just totals")
    sub.add_parser("health", help="is the hosted bot running? exit 1 if it has gone quiet")
    lc = sub.add_parser("live-check", help="check the Kalshi API key; --order places and cancels a tiny bid")
    lc.add_argument("--order", action="store_true")
    lc.add_argument("--fund", action="store_true", help="move the cash to the crypto shard and keep it there")
    ht = sub.add_parser("halt", help="kill switch: stop all real trading")
    ht.add_argument("reason", nargs="?", default="")
    ht.add_argument("--long", action="store_true", help="a long pause: the widget and dashboard show Training")
    sub.add_parser("resume", help="allow real trading again after a halt")
    sub.add_parser("employees")
    hi = sub.add_parser("hire", help="put an employee on this book mid-season (e.g. Training -> real money)")
    hi.add_argument("key")
    hi.add_argument("--level", type=int, default=0, help="0 Intern (half-size bets, the default), 1 Associate...")
    hi.add_argument("--why", default="")
    sub.add_parser("whoami")
    reset = sub.add_parser("pool-reset", help="restart the pool's day and high-water mark at its current value")
    reset.add_argument("equity", type=float, help="the pool's true value now, in dollars")
    sub.add_parser("notify-test", help="send a test phone notification (needs PUSHOVER_TOKEN and PUSHOVER_USER)")
    sub.add_parser("fast", help="run the always-on Fast Sadie and her 2-minute twin (the server's job)")
    sub.add_parser("fast-report", help="Fast Sadie vs her twin by month: is the server worth it?")
    sub.add_parser("tick", help="one run of every book, like the hosted bot's /api/tick (the server's timer, 11-16)")
    p_off = sub.add_parser("offices", help="run the friends' offices every 2 minutes (the server's job, desk/offices.py)")
    p_off.add_argument("--once", action="store_true", help="one round now, then stop")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)
    cfg = DeskConfig.load(args.config)

    try:
        if args.cmd == "scan":
            asyncio.run(cmd_scan(cfg))
        elif args.cmd == "paper":
            asyncio.run(cmd_paper(cfg, args.record))
        elif args.cmd == "report":
            cmd_report(cfg, args.offline)
        elif args.cmd == "accuracy":
            cmd_accuracy(cfg, args.db, args.employee)
        elif args.cmd == "backtest":
            asyncio.run(cmd_backtest(cfg, args.days, args.series.split(","), args.fill_delay, args.depth,
                                     args.only.split(",") if args.only else None, not args.no_save))
        elif args.cmd == "migrate":
            cmd_migrate(cfg, args.source, not args.skip_backtests)
        elif args.cmd == "tune":
            asyncio.run(cmd_tune(cfg, args.employee, args.set, args.days, args.series.split(","),
                                 args.fill_delay, args.depth, args.top))
        elif args.cmd == "jobs":
            asyncio.run(cmd_jobs(cfg, args.backfill_minutes, args.force_tune))
        elif args.cmd == "review":
            cmd_review(cfg, args.days, args.out)
        elif args.cmd == "new-season":
            cmd_new_season(cfg, args.pool, args.level, args.why)
        elif args.cmd == "seed-season":
            asyncio.run(cmd_seed_season(cfg, args.days, args.history, args.slippage, args.why, args.apply, args.until,
                                        args.max_bet))
        elif args.cmd == "log":
            cmd_log(cfg, args.hours, args.all, args.employee)
        elif args.cmd == "health":
            return cmd_health(cfg, args.config)
        elif args.cmd == "live-check":
            return asyncio.run(cmd_live_check(cfg, args.order, args.fund))
        elif args.cmd in ("halt", "resume"):
            cmd_halt(cfg, getattr(args, "reason", ""), args.cmd == "resume", getattr(args, "long", False))
        elif args.cmd == "employees":
            cmd_employees()
        elif args.cmd == "hire":
            return cmd_hire(cfg, args.key, args.level, args.why)
        elif args.cmd == "pool-reset":
            from desk.cloud import reset_pool_day

            done = reset_pool_day(Ledger(cfg.db_path, cfg.schema), args.equity)
            print(f"Pool day restarted: {done}" if done else "A bot run is in progress; try again in a minute.")
        elif args.cmd == "notify-test":
            from desk import notify

            if not notify.configured():
                print("Set PUSHOVER_TOKEN and PUSHOVER_USER first (in .env, or on the bot's Vercel project).")
                return 1
            ok = notify.daily(1.42, 6, 5, ("Nickel Nora", 0.88), 103.21, 2.10, 3)
            print("Sent: check your phone." if ok else "Pushover refused it (see the warning above).")
        elif args.cmd == "whoami":
            asyncio.run(cmd_whoami(cfg))
        elif args.cmd == "fast":
            from desk.fast import run_fast

            asyncio.run(run_fast(cfg.db_path))
        elif args.cmd == "tick":
            from desk.cloud import run_all_books

            result = asyncio.run(run_all_books())
            from desk.cloud import warm_site

            result["warm"] = warm_site() or {"ok": False}
            print(json.dumps({k: (v if not isinstance(v, dict) else {x: v[x] for x in ("ok", "skipped", "error", "fills",
                              "seconds") if x in v}) for k, v in result.items()}))
            if not result.get("ok"):
                sys.exit(1)
        elif args.cmd == "offices":
            from desk.offices import run_offices

            asyncio.run(run_offices(once=args.once))
        elif args.cmd == "fast-report":
            from desk.fast import SCHEMA, fast_report

            print(fast_report(Ledger(cfg.db_path, SCHEMA)))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
