"""
Archive, then trim, the database's logs (11-17: 480 of the free plan's 500 MB). Runs on the server:

    python deploy/archive_logs.py /home/desk/archive

For every schema: each row Ledger.prune_logs would remove is first saved to <dir>/<date>/<schema>.<table>.csv.gz
(COPY ... TO STDOUT, with a header), then prune_logs runs, then VACUUM FULL gives the space back (a table is locked
for a few seconds while it's rewritten). Bets, payouts, orders and money moves are never touched.
Restore: COPY <schema>.<table> FROM a gunzipped file with CSV HEADER.

11-23 (460 of 500 MB): every office schema (office_*), the shorter OFFICE_RETENTION for offices, and Training's past
seasons (fills, settlements, equity of every season before the current one: 73% of its bets; nothing reads them,
the bot and the site only read the current season) are archived and deleted too.
"""
import gzip
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desk.paper.ledger import OFFICE_RETENTION, RETENTION, Ledger  # noqa: E402

SEASON_TABLES = ["fills", "settlements", "equity"]  # Training's past seasons


def doomed(now: datetime, office: bool = False) -> dict[str, str]:
    keep = OFFICE_RETENTION if office else RETENTION
    ago = lambda d: (now - timedelta(days=d)).isoformat()
    cut = ago(keep["equity_full"])
    return {
        "runs": f"ts < '{ago(keep['runs'])}'",
        "decisions": f"ts < '{ago(keep['decisions'])}'",
        "market_tape": f"ts < '{ago(keep['market_tape'])}'",
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
    schemas = ["public", "real", "fast"] + [r[0] for r in conn.execute(
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'office\\_%' ORDER BY 1").fetchall()]
    for schema in schemas:
        have = {r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s", (schema,)).fetchall()}
        if "runs" not in have:
            continue
        jobs = dict(doomed(now, schema.startswith("office_")))
        if schema == "public":  # Training's past seasons
            season = conn.execute("SELECT max(season) FROM public.equity").fetchone()[0]
            for tb in SEASON_TABLES:
                jobs[f"{tb}@seasons"] = f"season < {int(season)}"
        for key, where in jobs.items():
            table = key.split("@")[0]
            if table not in have:
                continue
            t = f"{schema}.{table}"
            cond = where.replace("{t}", t)
            path = folder / f"{t}{'.past_seasons' if '@' in key else ''}.csv.gz"
            n = 0
            with gzip.open(path, "wb") as f, conn.cursor().copy(f"COPY (SELECT * FROM {t} WHERE {cond}) TO STDOUT WITH CSV HEADER") as cp:
                for chunk in cp:
                    b = bytes(chunk)
                    f.write(b)
                    n += b.count(b"\n")
            print(f"  {t}: archived ~{max(0, n - 1)} rows -> {path.name} ({path.stat().st_size // 1024} KB)")
            if "@" in key:
                conn.execute(f"DELETE FROM {t} WHERE {cond}")
        Ledger(url, schema).prune_logs(force=True)
        for table in {k.split("@")[0] for k in jobs}:
            if table in have:
                conn.execute(f"VACUUM FULL {schema}.{table}")
        print(f"{schema}: trimmed and compacted; database now {size()}")
    print("after:", size())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/home/desk/archive")
