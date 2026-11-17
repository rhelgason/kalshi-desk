"""
Archive, then trim, the database's logs (11-17: 480 of the free plan's 500 MB). Runs on the server:

    python deploy/archive_logs.py /home/desk/archive

For every schema: each row Ledger.prune_logs would remove is first saved to <dir>/<date>/<schema>.<table>.csv.gz
(COPY ... TO STDOUT, with a header), then prune_logs runs, then VACUUM FULL gives the space back (a table is locked
for a few seconds while it's rewritten). Bets, payouts, orders and money moves are never touched.
Restore: COPY <schema>.<table> FROM a gunzipped file with CSV HEADER.
"""
import gzip
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desk.paper.ledger import RETENTION, Ledger  # noqa: E402

SCHEMAS = ["public", "real", "office_judson", "office_colin", "fast"]


def doomed(now: datetime) -> dict[str, str]:
    ago = lambda d: (now - timedelta(days=d)).isoformat()
    cut = ago(RETENTION["equity_full"])
    return {
        "runs": f"ts < '{ago(RETENTION['runs'])}'",
        "decisions": f"ts < '{ago(RETENTION['decisions'])}'",
        "market_tape": f"ts < '{ago(RETENTION['market_tape'])}'",
        "equity": (f"ts < '{cut}' AND id NOT IN (SELECT MAX(id) FROM {{t}} WHERE ts < '{cut}' GROUP BY strategy, season,"
                   f" substr(ts, 1, 13)) AND id NOT IN (SELECT MIN(id) FROM {{t}} GROUP BY strategy, season)"),
        "market_history": f"close_ts < {int((now - timedelta(days=RETENTION['market_history'])).timestamp())}",
    }


def main(out: str) -> None:
    url = os.environ["DATABASE_URL"]
    now = datetime.now(timezone.utc)
    folder = Path(out) / now.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    conn = psycopg.connect(url, autocommit=True)
    size = lambda: conn.execute("SELECT pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]
    print("before:", size())
    for schema in SCHEMAS:
        have = {r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s", (schema,)).fetchall()}
        if "runs" not in have:
            continue
        for table, where in doomed(now).items():
            if table not in have:
                continue
            t = f"{schema}.{table}"
            cond = where.replace("{t}", t)
            path = folder / f"{t}.csv.gz"
            n = 0
            with gzip.open(path, "wb") as f, conn.cursor().copy(f"COPY (SELECT * FROM {t} WHERE {cond}) TO STDOUT WITH CSV HEADER") as cp:
                for chunk in cp:
                    f.write(chunk)
                    n += chunk.count(b"\n")
            print(f"  {t}: archived ~{max(0, n - 1)} rows -> {path.name} ({path.stat().st_size // 1024} KB)")
        Ledger(url, schema).prune_logs(force=True)
        for table in doomed(now):
            if table in have:
                conn.execute(f"VACUUM FULL {schema}.{table}")
        print(f"{schema}: trimmed and compacted; database now {size()}")
    print("after:", size())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/home/desk/archive")
