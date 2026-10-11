"""
SQLite ledger for paper trading.

Every fill and settlement is appended as a row, and accounts are rebuilt by
replaying those rows. That means you can stop the bot, restart it days later,
and every employee picks up where they left off, with a full trade history
to analyze.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from desk.kalshi.models import Side
from desk.paper.account import PaperAccount

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    strategy TEXT PRIMARY KEY,
    starting_cash REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    strategy TEXT NOT NULL,
    intent_id TEXT,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    count REAL NOT NULL,
    price REAL NOT NULL,
    fee REAL NOT NULL,
    model_prob REAL,
    expected_edge REAL,
    reason TEXT
);
CREATE TABLE IF NOT EXISTS settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    strategy TEXT NOT NULL,
    ticker TEXT NOT NULL,
    yes_value REAL NOT NULL,
    pnl REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS equity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    strategy TEXT NOT NULL,
    cash REAL NOT NULL,
    equity REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    strategy TEXT,
    kind TEXT NOT NULL,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS fills_strategy ON fills(strategy);
CREATE INDEX IF NOT EXISTS settlements_strategy ON settlements(strategy);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Ledger:
    def __init__(self, path: str | Path = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    # Writes ------------------------------------------------------------

    def ensure_account(self, strategy: str, starting_cash: float) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO accounts(strategy, starting_cash, created_at) VALUES (?, ?, ?)",
            (strategy, starting_cash, _now()),
        )
        self.db.commit()

    def record_fill(self, strategy: str, ticker: str, side: Side, count: float, price: float, fee: float,
                    intent_id: str = "", model_prob: Optional[float] = None,
                    expected_edge: Optional[float] = None, reason: str = "", ts: Optional[str] = None) -> None:
        self.db.execute(
            "INSERT INTO fills(ts, strategy, intent_id, ticker, side, count, price, fee, model_prob, expected_edge, reason)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ts or _now(), strategy, intent_id, ticker, side.value, count, price, fee, model_prob, expected_edge, reason),
        )
        self.db.commit()

    def record_settlement(self, strategy: str, ticker: str, yes_value: float, pnl: float,
                          ts: Optional[str] = None) -> None:
        self.db.execute(
            "INSERT INTO settlements(ts, strategy, ticker, yes_value, pnl) VALUES (?, ?, ?, ?, ?)",
            (ts or _now(), strategy, ticker, yes_value, pnl),
        )
        self.db.commit()

    def record_equity(self, strategy: str, cash: float, equity: float, ts: Optional[str] = None) -> None:
        self.db.execute(
            "INSERT INTO equity(ts, strategy, cash, equity) VALUES (?, ?, ?, ?)",
            (ts or _now(), strategy, cash, equity),
        )
        self.db.commit()

    def record_event(self, kind: str, detail: dict | str, strategy: Optional[str] = None) -> None:
        text = detail if isinstance(detail, str) else json.dumps(detail, default=str)
        self.db.execute(
            "INSERT INTO events(ts, strategy, kind, detail) VALUES (?, ?, ?, ?)",
            (_now(), strategy, kind, text),
        )
        self.db.commit()

    # Reads -------------------------------------------------------------

    def load_accounts(self, default_cash: float, strategies: list[str]) -> dict[str, PaperAccount]:
        """Rebuild every account by replaying its fills and settlements in order."""
        for s in strategies:
            self.ensure_account(s, default_cash)
        accounts = {
            r["strategy"]: PaperAccount(r["strategy"], r["starting_cash"])
            for r in self.db.execute("SELECT * FROM accounts")
        }
        rows = self.db.execute(
            "SELECT ts, 'fill' AS kind, id, strategy, ticker, side, count, price, fee, NULL AS yes_value FROM fills"
            " UNION ALL "
            "SELECT ts, 'settle' AS kind, id, strategy, ticker, NULL, NULL, NULL, NULL, yes_value FROM settlements"
            " ORDER BY ts, kind, id"
        )
        for r in rows:
            acct = accounts.get(r["strategy"])
            if not acct:
                continue
            if r["kind"] == "fill":
                acct.apply_fill(r["ticker"], Side(r["side"]), r["count"], r["price"], r["fee"])
            else:
                acct.settle(r["ticker"], r["yes_value"])
        return accounts

    def fills(self, strategy: Optional[str] = None) -> list[sqlite3.Row]:
        if strategy:
            return list(self.db.execute("SELECT * FROM fills WHERE strategy = ? ORDER BY id", (strategy,)))
        return list(self.db.execute("SELECT * FROM fills ORDER BY id"))

    def settlements(self, strategy: Optional[str] = None) -> list[sqlite3.Row]:
        if strategy:
            return list(self.db.execute("SELECT * FROM settlements WHERE strategy = ? ORDER BY id", (strategy,)))
        return list(self.db.execute("SELECT * FROM settlements ORDER BY id"))

    def equity_curve(self, strategy: str) -> list[tuple[str, float]]:
        return [(r["ts"], r["equity"]) for r in
                self.db.execute("SELECT ts, equity FROM equity WHERE strategy = ? ORDER BY id", (strategy,))]
