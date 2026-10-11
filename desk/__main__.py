"""
Command line for the desk.

    python -m desk scan          one look at the market: what would each employee do?
    python -m desk paper         run the paper-trading loop (Ctrl+C to stop)
    python -m desk report        scoreboard from the saved ledger
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
from desk.paper.ledger import Ledger
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
    return Desk(cfg, client, build_strategies(cfg.strategies), ledger, feed=feed, record_path=record)


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


def cmd_report(cfg: DeskConfig) -> None:
    ledger = Ledger(cfg.db_path)
    strategies = build_strategies(cfg.strategies)
    accounts = ledger.load_accounts(cfg.starting_cash, [s.key for s in strategies])
    personas = {s.key: f"{s.persona.emoji} {s.persona.name} ({s.key})" for s in strategies}
    print(format_scoreboard(scoreboard_rows(accounts, ledger), personas))
    print("\n(Open positions are valued at cost here; run `paper` for live marks.)")


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
    sub.add_parser("report")
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
            cmd_report(cfg)
        elif args.cmd == "employees":
            cmd_employees()
        elif args.cmd == "whoami":
            asyncio.run(cmd_whoami(cfg))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
