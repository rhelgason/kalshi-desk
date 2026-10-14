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
    python -m desk new-season --level nickel_picker=Senior ...   fresh start: split the office pool
    python -m desk employees     who works here
    python -m desk whoami        check your Kalshi API key (read-only)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

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
    ledger = Ledger(cfg.db_path)
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
    ledger = Ledger(cfg.db_path)
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

    ledger = Ledger(db or cfg.db_path)
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
            Ledger(cfg.db_path).save_backtest(stamp, summary)
            print("Uploaded summary to the dashboard database.")
        print(f"\nSaved to data/backtests/{stamp}.db and .json "
              f"(try: python -m desk accuracy --db data/backtests/{stamp}.db --employee fair_value)")


def cmd_migrate(cfg: DeskConfig, source: str, upload_backtests: bool) -> None:
    import json
    from pathlib import Path

    if not is_postgres(cfg.db_path):
        print("Set DATABASE_URL (in .env) to your Postgres connection string first.")
        return
    dest = Ledger(cfg.db_path)
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

    text = build_review(Ledger(cfg.db_path), days)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text)
        print(f"Saved to {out}")
    else:
        print(text)


def cmd_new_season(cfg: DeskConfig, pool: float | None, levels: list[str], why: str) -> None:
    from desk import hr

    ledger = Ledger(cfg.db_path)
    titles = {t.lower(): i for i, (t, _) in enumerate(hr.LEVELS)}
    wanted = {}
    for item in levels:
        key, _, title = item.partition("=")
        if key not in REGISTRY or title.lower() not in titles:
            raise SystemExit(f"Can't read --level {item!r}: use employee_key=Intern|Associate|Senior|VP|Partner")
        wanted[key] = titles[title.lower()]
    roster = hr.load_roster(ledger, list(REGISTRY))
    config = hr.effective_strategy_config(cfg.strategies, roster)
    staff = [k for k in REGISTRY if (config.get(k) or {}).get("enabled", True) and roster[k].status != "fired"]
    detail = hr.start_season(ledger, staff, cfg.pool_cash if pool is None else pool, cfg.starting_cash, wanted, why)
    print(f"Season {detail['season']} started: ${detail['pool']:,.2f} office pool shared by "
          f"{len(detail['members'])} employees ({', '.join(detail['members'])})")


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
    ns.add_argument("--pool", type=float, help="dollars in the office pool (default: pool_cash in desk.yaml)")
    ns.add_argument("--level", action="append", default=[], help="employee_key=Title, e.g. nickel_picker=Senior")
    ns.add_argument("--why", default="", help="the reason, for the HR log")
    sub.add_parser("employees")
    sub.add_parser("whoami")
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
        elif args.cmd == "employees":
            cmd_employees()
        elif args.cmd == "whoami":
            asyncio.run(cmd_whoami(cfg))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
