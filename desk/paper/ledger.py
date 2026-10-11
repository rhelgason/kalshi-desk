"""
The ledger: every paper fill and settlement, appended as a row.

Accounts are rebuilt by replaying those rows, so you can stop the bot, restart
it days later (or on a different machine), and every employee picks up where
they left off.

Two backends with the same tables:
  - SQLite file (default, data/desk.db): local runs, tests, backtests
  - Postgres (any postgres:// URL, e.g. Supabase): the hosted bot, which the
    web dashboard reads directly

The `status` table holds small JSON blobs the bot refreshes for the dashboard
(live scoreboard, open positions, accuracy). `backtests` holds saved runs.

Control plane (written by the website and the HR system, read by the bot):
  employees       one row per employee: status, level, setting overrides, autotune
  settings        desk-wide policy (season, review rules, reserve, autotune)
  transfers       paper cash moved to or from an employee (bonuses, not profit)

Seasons: fills, settlements, equity and transfers carry a season number; a new
season starts every employee fresh while keeping the old rows.

History store (for backtests and autotuning; filled by the background jobs):
  market_history  settled markets with their 1-minute bid/ask candles
  price_history   1-minute coin prices and hourly implied vol, one row per day
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from desk.kalshi.models import Side
from desk.paper.account import PaperAccount

logger = logging.getLogger(__name__)

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
CREATE TABLE IF NOT EXISTS status (
    key TEXT PRIMARY KEY,
    updated_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backtests (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    summary TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    season INTEGER NOT NULL DEFAULT 1,
    strategy TEXT NOT NULL,
    amount REAL NOT NULL,
    reason TEXT
);
CREATE TABLE IF NOT EXISTS employees (
    key TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'active',
    suspended_until TEXT,
    level INTEGER NOT NULL DEFAULT 1,
    strikes INTEGER NOT NULL DEFAULT 0,
    params TEXT NOT NULL DEFAULT '{}',
    autotune INTEGER NOT NULL DEFAULT 1,
    control INTEGER NOT NULL DEFAULT 0,
    awards INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    updated_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tuning_runs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    strategy TEXT NOT NULL,
    summary TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS market_history (
    ticker TEXT PRIMARY KEY,
    series TEXT NOT NULL,
    close_ts BIGINT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_history (
    symbol TEXT NOT NULL,
    day TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (symbol, day)
);
CREATE INDEX IF NOT EXISTS market_history_series_close ON market_history(series, close_ts);
CREATE INDEX IF NOT EXISTS fills_strategy ON fills(strategy);
CREATE INDEX IF NOT EXISTS settlements_strategy ON settlements(strategy);
CREATE INDEX IF NOT EXISTS equity_strategy_ts ON equity(strategy, ts);
CREATE INDEX IF NOT EXISTS settlements_strategy_ticker ON settlements(strategy, ticker);
"""


# Bump when SCHEMA, SEASONED columns, or RLS setup change. On Postgres the setup
# below only runs when this differs from what the database records, because
# ALTER TABLE takes a full-table lock even when there's nothing to change, and
# running it every 2 minutes can pile up behind a slow query.
SCHEMA_VERSION = 4

TABLES = ("accounts", "fills", "settlements", "equity", "events", "status", "backtests", "transfers",
          "employees", "settings", "tuning_runs", "market_history", "price_history")
SEASONED = ("fills", "settlements", "equity")
# Fill reality check: what the employee saw vs. what the paper fill got
FILL_REALISM = (("seen_price", "REAL"), ("book_depth", "REAL"), ("latency_ms", "INTEGER"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_postgres(url: str) -> bool:
    return str(url).startswith(("postgres://", "postgresql://"))


class _Postgres:
    """Thin adapter so Ledger can speak SQLite-flavored SQL to Postgres."""

    def __init__(self, url: str):
        import psycopg
        from psycopg.rows import dict_row

        self._psycopg = psycopg
        self._url = url
        self._dict_row = dict_row
        self._connect()

    def _connect(self) -> None:
        # prepare_threshold=None: Supabase's pooler doesn't support prepared statements
        self.conn = self._psycopg.connect(self._url, autocommit=True, row_factory=self._dict_row,
                                          prepare_threshold=None)

    @staticmethod
    def translate(sql: str) -> str:
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
        sql = sql.replace(" REAL", " DOUBLE PRECISION")
        if "INSERT OR IGNORE" in sql:
            sql = sql.replace("INSERT OR IGNORE", "INSERT") + " ON CONFLICT DO NOTHING"
        return sql.replace("?", "%s")

    def execute(self, sql: str, params: tuple = ()):
        sql = self.translate(sql)
        for attempt in range(2):
            try:
                return self.conn.execute(sql, params)
            except self._psycopg.OperationalError:
                if attempt:
                    raise
                logger.warning("Postgres connection lost; reconnecting")
                self._connect()

    def executescript(self, script: str) -> None:
        for stmt in script.split(";"):
            if stmt.strip():
                self.execute(stmt)

    def commit(self) -> None:
        pass  # autocommit

    def close(self) -> None:
        self.conn.close()


class Ledger:
    def __init__(self, path: str | Path = ":memory:"):
        self.url = str(path)
        if is_postgres(self.url):
            self.db = _Postgres(self.url)
        else:
            if self.url != ":memory:":
                Path(self.url).parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(self.url)
            self.db.row_factory = sqlite3.Row
        if not (self.is_postgres and self._schema_is_current()):
            self.db.executescript(SCHEMA)
            for table in SEASONED:
                self._add_column(table, "season", "INTEGER NOT NULL DEFAULT 1")
            for col, decl in FILL_REALISM:
                self._add_column("fills", col, decl)
            if self.is_postgres:
                # Supabase exposes the public schema through its auto-generated REST
                # API. Row-level security with no policies blocks that API entirely;
                # the bot and dashboard connect as the table owner, which RLS skips.
                for table in TABLES:
                    self.db.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
                self.db.execute(
                    "INSERT INTO settings(key, updated_at, data) VALUES ('schema', ?, ?)"
                    " ON CONFLICT(key) DO UPDATE SET updated_at = excluded.updated_at, data = excluded.data",
                    (_now(), json.dumps({"version": SCHEMA_VERSION})),
                )
        # In-memory copies of append-only tables, loaded on first read. The bot
        # rebuilds its scoreboard every minute; rereading every row from a
        # remote database each time would waste bandwidth.
        self._fills: Optional[list[dict]] = None
        self._settlements: Optional[list[dict]] = None
        self._equity: dict[str, list[tuple[str, float]]] = {}
        self.season = 1
        self.refresh_season()

    @property
    def is_postgres(self) -> bool:
        return isinstance(self.db, _Postgres)

    def _schema_is_current(self) -> bool:
        if self.db.execute("SELECT to_regclass('public.settings') AS t").fetchone()["t"] is None:
            return False
        row = self.db.execute("SELECT data FROM settings WHERE key = 'schema'").fetchone()
        return bool(row) and json.loads(row["data"]).get("version") == SCHEMA_VERSION

    def _add_column(self, table: str, column: str, decl: str) -> None:
        if self.is_postgres:
            self.db.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {decl}")
            return
        cols = {r[1] for r in self.db.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
            self.db.commit()

    def refresh_season(self) -> int:
        """Pick up the current season from settings (the website can start a new one)."""
        desk = self.get_setting("desk") or {}
        season = int(desk.get("season") or 1)
        if season != self.season:
            self._fills, self._settlements, self._equity = None, None, {}
        self.season = season
        return season

    def close(self) -> None:
        self.db.close()

    def _write(self, sql: str, params: tuple) -> None:
        self.db.execute(sql, params)
        self.db.commit()

    # Writes ------------------------------------------------------------

    def ensure_account(self, strategy: str, starting_cash: float) -> None:
        self._write("INSERT OR IGNORE INTO accounts(strategy, starting_cash, created_at) VALUES (?, ?, ?)",
                    (strategy, starting_cash, _now()))

    def record_fill(self, strategy: str, ticker: str, side: Side, count: float, price: float, fee: float,
                    intent_id: str = "", model_prob: Optional[float] = None,
                    expected_edge: Optional[float] = None, reason: str = "", ts: Optional[str] = None,
                    seen_price: Optional[float] = None, book_depth: Optional[float] = None,
                    latency_ms: Optional[int] = None) -> None:
        row = dict(ts=ts or _now(), strategy=strategy, intent_id=intent_id, ticker=ticker, side=side.value,
                   count=count, price=price, fee=fee, model_prob=model_prob, expected_edge=expected_edge,
                   reason=reason, season=self.season, seen_price=seen_price, book_depth=book_depth,
                   latency_ms=latency_ms)
        self._write(
            "INSERT INTO fills(ts, strategy, intent_id, ticker, side, count, price, fee, model_prob, expected_edge,"
            " reason, season, seen_price, book_depth, latency_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(row.values()),
        )
        if self._fills is not None:
            self._fills.append(row)

    def record_settlement(self, strategy: str, ticker: str, yes_value: float, pnl: float,
                          ts: Optional[str] = None) -> None:
        row = dict(ts=ts or _now(), strategy=strategy, ticker=ticker, yes_value=yes_value, pnl=pnl,
                   season=self.season)
        self._write("INSERT INTO settlements(ts, strategy, ticker, yes_value, pnl, season) VALUES (?, ?, ?, ?, ?, ?)",
                    tuple(row.values()))
        if self._settlements is not None:
            self._settlements.append(row)

    def record_equity(self, strategy: str, cash: float, equity: float, ts: Optional[str] = None) -> None:
        ts = ts or _now()
        self._write("INSERT INTO equity(ts, strategy, cash, equity, season) VALUES (?, ?, ?, ?, ?)",
                    (ts, strategy, cash, equity, self.season))
        if strategy in self._equity:
            self._equity[strategy].append((ts, equity))

    def record_transfer(self, strategy: str, amount: float, reason: str = "", ts: Optional[str] = None) -> None:
        """Paper cash given to (+) or taken from (-) an employee. Not profit or loss."""
        self._write("INSERT INTO transfers(ts, season, strategy, amount, reason) VALUES (?, ?, ?, ?, ?)",
                    (ts or _now(), self.season, strategy, amount, reason))

    def record_event(self, kind: str, detail: dict | str, strategy: Optional[str] = None) -> None:
        text = detail if isinstance(detail, str) else json.dumps(detail, default=str)
        self._write("INSERT INTO events(ts, strategy, kind, detail) VALUES (?, ?, ?, ?)",
                    (_now(), strategy, kind, text))

    def set_status(self, key: str, data: Any) -> None:
        self._write(
            "INSERT INTO status(key, updated_at, data) VALUES (?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET updated_at = excluded.updated_at, data = excluded.data",
            (key, _now(), json.dumps(data, default=str)),
        )

    def try_lease(self, name: str, seconds: float) -> bool:
        """
        Take a named lock that expires on its own after `seconds`, so a crashed
        run can't block the next one forever. Returns False if someone else holds it.
        """
        now = datetime.now(timezone.utc)
        stale = (now - timedelta(seconds=seconds)).isoformat()
        rows = self._rows(
            "INSERT INTO status(key, updated_at, data) VALUES (?, ?, '{}')"
            " ON CONFLICT(key) DO UPDATE SET updated_at = excluded.updated_at"
            " WHERE status.updated_at < ? RETURNING key",
            (f"_lease:{name}", now.isoformat(), stale),
        )
        self.db.commit()
        return bool(rows)

    def release_lease(self, name: str) -> None:
        self._write("DELETE FROM status WHERE key = ?", (f"_lease:{name}",))

    def get_setting(self, key: str) -> Optional[dict]:
        rows = self._rows("SELECT data FROM settings WHERE key = ?", (key,))
        return json.loads(rows[0]["data"]) if rows else None

    def set_setting(self, key: str, data: Any) -> None:
        self._write(
            "INSERT INTO settings(key, updated_at, data) VALUES (?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET updated_at = excluded.updated_at, data = excluded.data",
            (key, _now(), json.dumps(data, default=str)),
        )

    def employee_rows(self) -> list[dict]:
        return [dict(r) for r in self._rows("SELECT * FROM employees")]

    def upsert_employee(self, row: dict) -> None:
        cols = ["key", "status", "suspended_until", "level", "strikes", "params", "autotune", "control",
                "awards", "note", "updated_at"]
        vals = {**row, "updated_at": _now()}
        if not isinstance(vals.get("params"), str):
            vals["params"] = json.dumps(vals.get("params") or {})
        updates = ", ".join(f"{c} = excluded.{c}" for c in cols[1:])
        self._write(
            f"INSERT INTO employees({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})"
            f" ON CONFLICT(key) DO UPDATE SET {updates}",
            tuple(vals.get(c) for c in cols),
        )

    def events_since(self, since_id: int = 0, limit: int = 200) -> list[dict]:
        return [dict(r) for r in self._rows(
            "SELECT * FROM events WHERE id > ? ORDER BY id DESC LIMIT ?", (since_id, limit))]

    def save_tuning_run(self, run_id: str, strategy: str, summary: dict) -> None:
        self._write(
            "INSERT INTO tuning_runs(id, created_at, strategy, summary) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET summary = excluded.summary",
            (run_id, _now(), strategy, json.dumps(summary, default=str)),
        )

    def save_backtest(self, run_id: str, summary: dict) -> None:
        self._write(
            "INSERT INTO backtests(id, created_at, summary) VALUES (?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET summary = excluded.summary",
            (run_id, _now(), json.dumps(summary, default=str)),
        )

    # Reads -------------------------------------------------------------

    def _rows(self, sql: str, params: tuple = ()) -> list:
        return list(self.db.execute(sql, params).fetchall())

    def get_status(self, key: str) -> Optional[dict]:
        rows = self._rows("SELECT data FROM status WHERE key = ?", (key,))
        return json.loads(rows[0]["data"]) if rows else None

    def load_accounts(self, default_cash: float, strategies: list[str]) -> dict[str, PaperAccount]:
        """Rebuild every account by replaying its fills and settlements in order."""
        for s in strategies:
            self.ensure_account(s, default_cash)
        accounts = {
            r["strategy"]: PaperAccount(r["strategy"], r["starting_cash"])
            for r in self._rows("SELECT * FROM accounts")
        }
        rows = self._rows(
            "SELECT ts, 'fill' AS kind, id, strategy, ticker, side, count, price, fee, NULL AS yes_value FROM fills"
            " WHERE season = ?"
            " UNION ALL "
            "SELECT ts, 'settle' AS kind, id, strategy, ticker, NULL, NULL, NULL, NULL, yes_value FROM settlements"
            " WHERE season = ?"
            " UNION ALL "
            "SELECT ts, 'transfer' AS kind, id, strategy, NULL, NULL, NULL, amount, NULL, NULL FROM transfers"
            " WHERE season = ?"
            " ORDER BY ts, kind, id",
            (self.season, self.season, self.season),
        )
        for r in rows:
            acct = accounts.get(r["strategy"])
            if not acct:
                continue
            if r["kind"] == "fill":
                acct.apply_fill(r["ticker"], Side(r["side"]), r["count"], r["price"], r["fee"])
            elif r["kind"] == "settle":
                acct.settle(r["ticker"], r["yes_value"])
            else:
                acct.apply_transfer(r["price"])
        return accounts

    def fills(self, strategy: Optional[str] = None) -> list[dict]:
        if self._fills is None:
            self._fills = [dict(r) for r in self._rows("SELECT * FROM fills WHERE season = ? ORDER BY id",
                                                       (self.season,))]
        return [f for f in self._fills if strategy is None or f["strategy"] == strategy]

    def settlements(self, strategy: Optional[str] = None) -> list[dict]:
        if self._settlements is None:
            self._settlements = [dict(r) for r in self._rows(
                "SELECT * FROM settlements WHERE season = ? ORDER BY id", (self.season,))]
        return [s for s in self._settlements if strategy is None or s["strategy"] == strategy]

    def equity_curve(self, strategy: str) -> list[tuple[str, float]]:
        if strategy not in self._equity:
            self._equity[strategy] = [(r["ts"], r["equity"]) for r in self._rows(
                "SELECT ts, equity FROM equity WHERE strategy = ? AND season = ? ORDER BY id",
                (strategy, self.season))]
        return self._equity[strategy]

    # Copying -----------------------------------------------------------

    def copy_to(self, other: "Ledger") -> dict[str, int]:
        """Copy every row into another ledger (e.g. local SQLite -> Postgres)."""
        counts = {}
        for r in self._rows("SELECT * FROM accounts"):
            other.ensure_account(r["strategy"], r["starting_cash"])
        counts["accounts"] = len(self._rows("SELECT strategy FROM accounts"))
        for table, cols in (
            ("fills", "ts, strategy, intent_id, ticker, side, count, price, fee, model_prob, expected_edge, reason,"
                      " season"),
            ("settlements", "ts, strategy, ticker, yes_value, pnl, season"),
            ("equity", "ts, strategy, cash, equity, season"),
            ("transfers", "ts, season, strategy, amount, reason"),
            ("events", "ts, strategy, kind, detail"),
        ):
            rows = self._rows(f"SELECT {cols} FROM {table} ORDER BY id")
            marks = ", ".join("?" for _ in cols.split(","))
            for r in rows:
                other.db.execute(f"INSERT INTO {table}({cols}) VALUES ({marks})", tuple(r[c.strip()] for c in cols.split(",")))
            other.db.commit()
            counts[table] = len(rows)
        return counts
