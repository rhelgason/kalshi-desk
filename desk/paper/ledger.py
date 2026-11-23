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

Diagnostics:
  runs            one summary per desk run, kept 14 days (desk/journal.py)

Real money (desk/live):
  orders          every order sent to Kalshi and what became of it
"""

from __future__ import annotations

import json
from zoneinfo import ZoneInfo
import logging
import re
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
-- Every bet an employee tried, filled or not, with what they saw (for reviews)
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    season INTEGER NOT NULL DEFAULT 1,
    strategy TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    limit_price REAL NOT NULL,
    count REAL NOT NULL,
    filled REAL NOT NULL,
    outcome TEXT NOT NULL,
    reason TEXT,
    context TEXT
);
-- Each run's quote for every open market the desk watches, plus bitcoin's price
CREATE TABLE IF NOT EXISTS market_tape (
    ts TEXT NOT NULL,
    ticker TEXT NOT NULL,
    secs_left REAL,
    yes_bid REAL,
    yes_ask REAL,
    yes_bid_size REAL,
    yes_ask_size REAL,
    volume REAL,
    strike REAL,
    spot REAL
);
-- One summary per desk run (desk/journal.py): the hosted bot's logs don't last
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    season INTEGER NOT NULL DEFAULT 1,
    seconds REAL,
    warnings INTEGER NOT NULL DEFAULT 0,
    summary TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_ts ON runs(ts);
-- Every real order sent to Kalshi (desk/live), and what became of it
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    season INTEGER NOT NULL DEFAULT 1,
    env TEXT NOT NULL,
    strategy TEXT NOT NULL,
    order_id TEXT,
    client_order_id TEXT,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    kind TEXT NOT NULL,
    price REAL NOT NULL,
    count REAL NOT NULL,
    filled REAL NOT NULL DEFAULT 0,
    fees REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS orders_ts ON orders(ts);
CREATE INDEX IF NOT EXISTS orders_order_id ON orders(order_id);
CREATE INDEX IF NOT EXISTS decisions_strategy_ts ON decisions(strategy, ts);
CREATE INDEX IF NOT EXISTS market_tape_ticker_ts ON market_tape(ticker, ts);
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
SCHEMA_VERSION = 8

TABLES = ("accounts", "fills", "settlements", "equity", "events", "status", "backtests", "transfers",
          "employees", "settings", "tuning_runs", "market_history", "price_history", "decisions", "market_tape",
          "runs", "orders")
SEASONED = ("fills", "settlements", "equity")
# Market data both books read; everything else belongs to one book (see Ledger's `schema`)
SHARED_TABLES = ("backtests", "tuning_runs", "market_history", "price_history")
BOOK_TABLES = tuple(t for t in TABLES if t not in SHARED_TABLES)
# A book table right after a keyword that names a table (not `equity.ts`-style column references)
_BOOK_TABLE_RE = re.compile(r"\b(FROM|INTO|UPDATE|JOIN|TABLE|EXISTS|ON)(\s+)(" + "|".join(BOOK_TABLES) + r")\b(?!\.)",
                            re.IGNORECASE)


def qualify(sql: str, schema: Optional[str]) -> str:
    """Point a query's book tables at `schema` (real money lives in its own); shared tables stay in public."""
    if not schema or schema == "public":
        return sql
    return _BOOK_TABLE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{schema}.{m.group(3)}", sql)
# Fill reality check: what the employee saw vs. what the paper fill got
FILL_REALISM = (("seen_price", "REAL"), ("book_depth", "REAL"), ("latency_ms", "INTEGER"),
                # JSON: what the employee saw when deciding (prices, bitcoin, time left, settings)
                ("context", "TEXT"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_postgres(url: str) -> bool:
    return str(url).startswith(("postgres://", "postgresql://"))



# How long the logs stay in the database, in days (Ledger.prune_logs; older rows are archived on the server first)
RETENTION = {"runs": 3, "decisions": 7, "market_tape": 7, "equity_full": 14, "market_history": 30}
# 11-23 (database at 460 of 500 MB): shorter on the owner's books (runs 7 -> 3 days, decisions and tape 14 -> 7; the
# weekly review reads 7 days of decisions, `desk log`/health read hours), and a friend's office keeps run journals
# 2 days and no market tape at all (it never records one: the owner's books already record the same markets)
OFFICE_RETENTION = {**RETENTION, "runs": 2, "market_tape": 0}
PRUNE_KEY = "_prune"

class _Postgres:
    """Thin adapter so Ledger can speak SQLite-flavored SQL to Postgres."""

    # One connection per database URL for ledgers made with shared=True: the friends' offices (desk/offices.py)
    # run one after another in one process, and Supabase's pooler only takes 15 clients in all
    _shared: dict[str, Any] = {}

    def __init__(self, url: str, schema: Optional[str] = None, shared: bool = False):
        import psycopg
        from psycopg.rows import dict_row

        self._psycopg = psycopg
        self._url = url
        self._dict_row = dict_row
        self.schema = schema
        self.shared = shared
        if shared and url in self._shared and not self._shared[url].closed:
            self.conn = self._shared[url]
        else:
            self._connect()
        if schema and schema != "public":
            self.conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

    def _connect(self) -> None:
        # prepare_threshold=None: Supabase's pooler doesn't support prepared statements
        self.conn = self._psycopg.connect(self._url, autocommit=True, row_factory=self._dict_row,
                                          prepare_threshold=None)
        if self.shared:
            self._shared[self._url] = self.conn

    @staticmethod
    def translate(sql: str) -> str:
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
        sql = sql.replace(" REAL", " DOUBLE PRECISION")
        if "INSERT OR IGNORE" in sql:
            sql = sql.replace("INSERT OR IGNORE", "INSERT") + " ON CONFLICT DO NOTHING"
        # psycopg treats % as the start of a placeholder: escape literal ones
        # (e.g. LIKE 'maker fill%') before turning ? into %s
        return sql.replace("%", "%%").replace("?", "%s")

    def execute(self, sql: str, params: tuple = ()):
        sql = self.translate(qualify(sql, self.schema))
        if self.shared:  # another office may have reconnected it
            self.conn = self._shared.get(self._url, self.conn)
        if self.conn.closed:  # given back on purpose between rounds (desk/offices.py): reopen without a warning
            self._connect()
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
        if not self.shared:
            self.conn.close()


class Ledger:
    def __init__(self, path: str | Path = ":memory:", schema: Optional[str] = None, shared: bool = False):
        """`schema` keeps a book's tables apart on Postgres (the real-money book uses "real");
        on SQLite each book simply uses its own file."""
        self.url = str(path)
        if schema and not re.fullmatch(r"[a-z_]+", schema):
            raise ValueError(f"bad schema name {schema!r}")
        self.schema = schema if is_postgres(self.url) and schema != "public" else None
        if is_postgres(self.url):
            self.db = _Postgres(self.url, self.schema, shared)
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
            # Portfolio charts read one season's equity over a time range
            self.db.execute("CREATE INDEX IF NOT EXISTS equity_season_ts ON equity(season, ts)")
            # The website reads recent bets and fills by date (11-16: a season-long scan made Training slow)
            self.db.execute("CREATE INDEX IF NOT EXISTS settlements_season_ts ON settlements(season, ts)")
            self.db.execute("CREATE INDEX IF NOT EXISTS fills_season_ts ON fills(season, ts)")
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
        if self.db.execute(f"SELECT to_regclass('{self.schema or 'public'}.settings') AS t").fetchone()["t"] is None:
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

    def set_starting_cash(self, strategy: str, starting_cash: float) -> None:
        self._write("INSERT INTO accounts(strategy, starting_cash, created_at) VALUES (?, ?, ?)"
                    " ON CONFLICT(strategy) DO UPDATE SET starting_cash = excluded.starting_cash",
                    (strategy, starting_cash, _now()))

    def record_fill(self, strategy: str, ticker: str, side: Side, count: float, price: float, fee: float,
                    intent_id: str = "", model_prob: Optional[float] = None,
                    expected_edge: Optional[float] = None, reason: str = "", ts: Optional[str] = None,
                    seen_price: Optional[float] = None, book_depth: Optional[float] = None,
                    latency_ms: Optional[int] = None, context: Optional[dict] = None) -> None:
        row = dict(ts=ts or _now(), strategy=strategy, intent_id=intent_id, ticker=ticker, side=side.value,
                   count=count, price=price, fee=fee, model_prob=model_prob, expected_edge=expected_edge,
                   reason=reason, season=self.season, seen_price=seen_price, book_depth=book_depth,
                   latency_ms=latency_ms)
        self._write(
            "INSERT INTO fills(ts, strategy, intent_id, ticker, side, count, price, fee, model_prob, expected_edge,"
            " reason, season, seen_price, book_depth, latency_ms, context)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (*row.values(), json.dumps(context, default=str) if context else None),
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

    def record_decision(self, strategy: str, ticker: str, side: str, limit_price: float, count: float,
                        filled: float, outcome: str, reason: str = "", context: Optional[dict] = None,
                        ts: Optional[str] = None) -> None:
        """One attempted bet, filled or not ("filled", "no liquidity at limit price", ...)."""
        self._write(
            "INSERT INTO decisions(ts, season, strategy, ticker, side, limit_price, count, filled, outcome, reason,"
            " context) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ts or _now(), self.season, strategy, ticker, side, limit_price, count, filled, outcome, reason,
             json.dumps(context, default=str) if context else None),
        )

    def record_tape(self, rows: list[tuple]) -> None:
        """(ts, ticker, secs_left, yes_bid, yes_ask, bid_size, ask_size, volume, strike, spot) per market."""
        for r in rows:
            self._write("INSERT INTO market_tape(ts, ticker, secs_left, yes_bid, yes_ask, yes_bid_size,"
                        " yes_ask_size, volume, strike, spot) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", r)

    def record_run(self, summary: dict, ts: Optional[str] = None) -> None:
        """One run's journal (desk/journal.py)."""
        self._write("INSERT INTO runs(ts, season, seconds, warnings, summary) VALUES (?, ?, ?, ?, ?)",
                    (ts or _now(), self.season, summary.get("seconds"), len(summary.get("warnings") or []),
                     json.dumps(summary, default=str)))

    def prune_runs(self, keep_days: float = RETENTION["runs"]) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat()
        self._write("DELETE FROM runs WHERE ts < ?", (cutoff,))

    def prune_logs(self, every_hours: float = 6, force: bool = False) -> bool:
        """
        Keep the logs from outgrowing the free database (11-17: 480 of 500 MB, growing ~10 MB a day): run journals,
        decisions and the market tape past RETENTION days go; equity snapshots older than RETENTION["equity_full"]
        days thin to the last one per employee per hour (plus each season's first, its start); closed-market
        history past RETENTION["market_history"] days goes. Bets, payouts, orders and money moves are never touched.
        At most every `every_hours` (a status row remembers when), since each owner run is a fresh process.
        Returns whether it pruned.
        """
        now = datetime.now(timezone.utc)
        last = (self.get_status(PRUNE_KEY) or {}).get("at")
        if not force and last and datetime.fromisoformat(last) > now - timedelta(hours=every_hours):
            return False
        ago = lambda d: (now - timedelta(days=d)).isoformat()
        keep = OFFICE_RETENTION if (self.schema or "").startswith("office_") else RETENTION
        self.prune_runs(keep["runs"])
        self._write("DELETE FROM decisions WHERE ts < ?", (ago(keep["decisions"]),))
        self._write("DELETE FROM market_tape WHERE ts < ?", (ago(keep["market_tape"]),))
        cut = ago(keep["equity_full"])
        self._write(
            "DELETE FROM equity WHERE ts < ?"
            " AND id NOT IN (SELECT MAX(id) FROM equity WHERE ts < ? GROUP BY strategy, season, substr(ts, 1, 13))"
            " AND id NOT IN (SELECT MIN(id) FROM equity GROUP BY strategy, season)", (cut, cut))
        try:
            self._write("DELETE FROM market_history WHERE close_ts < ?",
                        (int((now - timedelta(days=RETENTION["market_history"])).timestamp()),))
        except Exception:  # only the Training schema keeps closed-market history (autocommit: nothing to undo)
            pass
        self.set_status(PRUNE_KEY, {"at": now.isoformat()})
        return True

    def recent_runs(self, since: str, limit: int = 2000) -> list[dict]:
        rows = self._rows("SELECT ts, season, seconds, warnings, summary FROM runs WHERE ts >= ? ORDER BY ts DESC LIMIT ?",
                          (since, limit))
        return [{**dict(r), "summary": json.loads(r["summary"])} for r in reversed(rows)]

    def record_order(self, env: str, strategy: str, ticker: str, side: str, kind: str, price: float, count: float,
                     status: str, order_id: Optional[str] = None, client_order_id: Optional[str] = None,
                     filled: float = 0.0, fees: float = 0.0, error: Optional[str] = None) -> None:
        """A real order sent to Kalshi (kind: taker or maker)."""
        now = _now()
        self._write(
            "INSERT INTO orders(ts, season, env, strategy, order_id, client_order_id, ticker, side, kind, price, count,"
            " filled, fees, status, error, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now, self.season, env, strategy, order_id, client_order_id, ticker, side, kind, price, count, filled,
             fees, status, error, now))

    def update_order(self, order_id: str, filled: float, fees: float, status: str) -> None:
        self._write("UPDATE orders SET filled = ?, fees = ?, status = ?, updated_at = ? WHERE order_id = ?",
                    (filled, fees, status, _now(), order_id))

    def record_event(self, kind: str, detail: dict | str, strategy: Optional[str] = None) -> None:
        text = detail if isinstance(detail, str) else json.dumps(detail, default=str)
        self._write("INSERT INTO events(ts, strategy, kind, detail) VALUES (?, ?, ?, ?)",
                    (_now(), strategy, kind, text))

    def set_status(self, key: str, data: Any) -> str:
        """Save a status row; returns its new updated_at (the stamp a local copy can be checked against)."""
        stamp = _now()
        self._write(
            "INSERT INTO status(key, updated_at, data) VALUES (?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET updated_at = excluded.updated_at, data = excluded.data",
            (key, stamp, json.dumps(data, default=str)),
        )
        return stamp

    def status_stamp(self, key: str) -> Optional[str]:
        """A status row's updated_at alone (a few bytes, where the row itself can be tens of KB)."""
        rows = self._rows("SELECT updated_at FROM status WHERE key = ?", (key,))
        return str(rows[0]["updated_at"]) if rows else None

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
        """11-23 (download allowance): read 2-3 times a run per book, and the website changes rows too. On Postgres
        the whole table is fetched again only when its 32-byte fingerprint changes."""
        if not self.is_postgres:
            return [dict(r) for r in self._rows("SELECT * FROM employees")]
        mark = self._rows("SELECT md5(coalesce(string_agg(e::text, '|' ORDER BY e.key), '')) AS m FROM employees e")
        mark = mark[0]["m"] if mark else None
        kept = getattr(self, "_employees_kept", None)
        if kept and mark and kept[0] == mark:
            return [dict(r) for r in kept[1]]
        rows = [dict(r) for r in self._rows("SELECT * FROM employees")]
        self._employees_kept = (mark, rows)
        return [dict(r) for r in rows]

    def upsert_employee(self, row: dict) -> None:
        cols = ["key", "status", "suspended_until", "level", "strikes", "params", "autotune", "control",
                "awards", "note", "updated_at"]
        vals = {**row, "updated_at": _now()}
        if not isinstance(vals.get("params"), str):
            vals["params"] = json.dumps(vals.get("params") or {})
        updates = ", ".join(f"{c} = excluded.{c}" for c in cols[1:])
        self._employees_kept = None
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

    def publish_page_summary(self, tz: str) -> bool:
        """
        The website's season in small pieces (11-16): one row per employee per day (in the office's time zone) with
        bets, wins, profit, money bet, best and worst bet and when the day's last bet finished, kept in the status row
        `_page`. Training's season is ~40,000 bets; this is ~1,300 rows, so a page reads one small row instead.
        On Postgres it's added up and written inside the database, so nothing big crosses the network each run.
        Only redone when a bet has finished since last time. Returns whether it wrote.
        """
        last = self._rows("SELECT max(id) AS m, count(*) AS n FROM settlements WHERE season = ?", (self.season,))
        key = (last[0]["m"], last[0]["n"], tz) if last else None
        if key is not None and key == getattr(self, "_page_key", None):
            return False
        now = _now()
        if self.is_postgres:
            self._write("""
                INSERT INTO status(key, updated_at, data)
                SELECT '_page', ?, json_build_object('at', ?::text, 'season', ?::int, 'tz', ?::text, 'days', coalesce(json_agg(json_build_array(
                    d, strategy, n, won, round(pnl::numeric, 4), round(cost::numeric, 4), round(best::numeric, 4),
                    round(worst::numeric, 4), last) ORDER BY d, strategy), '[]'::json))::text
                FROM (
                    SELECT to_char(s.ts::timestamptz AT TIME ZONE ?::text, 'YYYY-MM-DD') AS d, s.strategy, count(*) AS n,
                           count(*) FILTER (WHERE s.pnl > 0) AS won, sum(s.pnl) AS pnl, coalesce(sum(f.cost), 0) AS cost,
                           max(s.pnl) AS best, min(s.pnl) AS worst,
                           (extract(epoch FROM max(s.ts::timestamptz)) * 1000)::bigint AS last
                    FROM settlements s
                    LEFT JOIN (SELECT strategy, ticker, sum(count * price + fee) AS cost FROM fills WHERE season = ?
                               GROUP BY strategy, ticker) f ON f.strategy = s.strategy AND f.ticker = s.ticker
                    WHERE s.season = ?
                    GROUP BY 1, 2
                ) x
                ON CONFLICT(key) DO UPDATE SET updated_at = excluded.updated_at, data = excluded.data""",
                (now, now, self.season, tz, tz, self.season, self.season))
        else:
            zone = ZoneInfo(tz)
            cost = {(r["strategy"], r["ticker"]): r["c"] for r in self._rows(
                "SELECT strategy, ticker, sum(count * price + fee) AS c FROM fills WHERE season = ? GROUP BY strategy, ticker",
                (self.season,))}
            days: dict[tuple[str, str], list] = {}
            for r in self._rows("SELECT ts, strategy, ticker, pnl FROM settlements WHERE season = ? ORDER BY ts", (self.season,)):
                t = datetime.fromisoformat(r["ts"])
                d = t.astimezone(zone).strftime("%Y-%m-%d")
                row = days.setdefault((d, r["strategy"]), [d, r["strategy"], 0, 0, 0.0, 0.0, r["pnl"], r["pnl"], 0])
                row[2] += 1
                row[3] += r["pnl"] > 0
                row[4] += r["pnl"]
                row[5] += cost.get((r["strategy"], r["ticker"])) or 0.0
                row[6], row[7] = max(row[6], r["pnl"]), min(row[7], r["pnl"])
                row[8] = int(t.timestamp() * 1000)
            out = [[*r[:4], *(round(v, 4) for v in r[4:8]), r[8]] for _, r in sorted(days.items())]
            self.set_status("_page", {"at": now, "season": self.season, "tz": tz, "days": out})
        self._page_key = key
        return True

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
        wanted = set(strategies)
        accounts = {
            r["strategy"]: PaperAccount(r["strategy"], r["starting_cash"])
            for r in self._rows("SELECT * FROM accounts") if r["strategy"] in wanted
        }
        if not accounts:
            return accounts
        # Only these employees' rows: a seeded season holds ~70k, and every byte read counts against
        # the database's monthly download allowance (2026-10-27: a benched employee's empty account
        # pulled the whole season on each of the bot's cold starts)
        who = " AND strategy IN (%s)" % ",".join("?" * len(accounts))
        keys = tuple(accounts)
        rows = self._rows(
            "SELECT ts, 'fill' AS kind, id, strategy, ticker, side, count, price, fee, NULL AS yes_value FROM fills"
            " WHERE season = ?" + who +
            " UNION ALL "
            "SELECT ts, 'settle' AS kind, id, strategy, ticker, NULL, NULL, NULL, NULL, yes_value FROM settlements"
            " WHERE season = ?" + who +
            " UNION ALL "
            "SELECT ts, 'transfer' AS kind, id, strategy, NULL, NULL, NULL, amount, NULL, NULL FROM transfers"
            " WHERE season = ?" + who +
            " ORDER BY ts, kind, id",
            (self.season, *keys, self.season, *keys, self.season, *keys),
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
