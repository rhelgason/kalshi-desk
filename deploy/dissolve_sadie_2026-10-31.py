"""Hand Steady Sadie's season-7 bets to the coin specialists who would have placed them (2026-10-31).

Per book, in one transaction while holding the bot's tick lease:
  - fills/settlements/decisions/orders: heavy_maker -> maker_<coin> by ticker
  - accounts: Sadie's starting money split evenly across that book's specialists; Sadie -> $0
  - equity: each specialist gets a history from the season start (share + their settled profit, plus an even
    share of whatever Sadie's snapshot held beyond that, i.e. open bets); their own rows since 10-31 get the offset
  - saved bot state: Sadie's and the specialists' saved accounts/peaks dropped (rebuilt from the records)
DRY=1 (default) rolls back.  BOOKS=public,real
"""
import json, os, time
from bisect import bisect_right
from datetime import datetime, timedelta, timezone

import psycopg

SEASON = 7
COIN = {"KXBTC15M": "maker_btc", "KXETH15M": "maker_eth", "KXSOL15M": "maker_sol",
        "KXXRP15M": "maker_xrp", "KXDOGE15M": "maker_doge"}
DRY = os.environ.get("DRY", "1") != "0"
BOOKS = os.environ.get("BOOKS", "public,real").split(",")
t = lambda s: datetime.fromisoformat(s)

c = psycopg.connect(os.environ["DATABASE_URL"])
for sch in BOOKS:
    print(f"== {sch} {'(dry run)' if DRY else ''}")
    # Hold the bot off this book while we work (the cloud runner's own lock)
    for _ in range(120):
        now = datetime.now(timezone.utc)
        got = c.execute(f"INSERT INTO {sch}.status(key, updated_at, data) VALUES ('_lease:tick', %s, '{{}}')"
                        f" ON CONFLICT(key) DO UPDATE SET updated_at = excluded.updated_at"
                        f" WHERE {sch}.status.updated_at < %s RETURNING key",
                        (now.isoformat(), (now - timedelta(seconds=150)).isoformat())).fetchall()
        c.commit()
        if got:
            break
        time.sleep(1)
    assert got, "could not take the lease"

    acc = {r[0]: (float(r[1]), r[2]) for r in c.execute(f"SELECT strategy, starting_cash, created_at FROM {sch}.accounts")}
    start, created = acc["heavy_maker"]
    team = sorted(k for k in COIN.values() if k in acc)
    share = start / len(team)
    print(f"  Sadie started with ${start:,.4f}; {len(team)} specialists get ${share:,.4f} each: {team}")

    before = c.execute(f"SELECT sum(pnl), count(*) FROM {sch}.settlements WHERE season = %s", (SEASON,)).fetchone()
    sets = [(t(ts), COIN[tk.split("-")[0]], float(p)) for ts, tk, p in c.execute(
        f"SELECT ts, ticker, pnl FROM {sch}.settlements WHERE season = %s AND strategy = 'heavy_maker'", (SEASON,))]
    sets.sort()
    assert all(k in team for _, k, _ in sets), "a bet on a coin with no specialist on this book"
    times = [x[0] for x in sets]
    cum, cum_k = [0.0], {k: [0.0] for k in team}
    for _, k, p in sets:
        cum.append(cum[-1] + p)
        for j in team:
            cum_k[j].append(cum_k[j][-1] + (p if j == k else 0.0))

    def settled(ts):
        i = bisect_right(times, ts)
        return cum[i], {k: cum_k[k][i] for k in team}

    # The bets themselves
    case = "CASE split_part(ticker, '-', 1) " + " ".join(f"WHEN '{s}' THEN '{k}'" for s, k in COIN.items()) + " END"
    tables = ["fills", "settlements", "decisions"] + (["orders"] if sch == "real" else [])
    for tb in tables:
        n = c.execute(f"UPDATE {sch}.{tb} SET strategy = {case} WHERE season = %s AND strategy = 'heavy_maker'",
                      (SEASON,)).rowcount
        print(f"  {tb}: {n} rows moved")

    # Equity history
    switch = t(c.execute(f"SELECT min(ts) FROM {sch}.equity WHERE season = %s AND strategy = ANY(%s)",
                         (SEASON, team)).fetchone()[0])
    sadie = [(t(ts), float(cash), float(eq)) for ts, cash, eq in c.execute(
        f"SELECT ts, cash, equity FROM {sch}.equity WHERE season = %s AND strategy = 'heavy_maker'", (SEASON,))]
    new, worst = [], 0.0
    for ts, cash, eq in sadie:
        if ts >= switch:
            continue
        s, sk = settled(ts)
        extra_eq, extra_cash = (eq - start - s) / len(team), (cash - start - s) / len(team)
        worst = max(worst, abs(extra_eq) * len(team))
        for k in team:
            base = share + sk[k]
            new.append((ts.isoformat(), SEASON, k, base + extra_cash, base + extra_eq))
    print(f"  equity: {len(sadie)} Sadie snapshots -> {len(new)} specialist snapshots before {switch:%m-%d %H:%M}"
          f" (most riding in open bets at a snapshot: ${worst:,.2f})")
    with c.cursor() as cur, cur.copy(f"COPY {sch}.equity(ts, season, strategy, cash, equity) FROM STDIN") as cp:
        for r in new:
            cp.write_row(r)
    mine = c.execute(f"SELECT id, ts, strategy FROM {sch}.equity WHERE season = %s AND strategy = ANY(%s) AND ts >= %s",
                     (SEASON, team, switch.isoformat())).fetchall()
    with c.cursor() as cur:
        cur.executemany(f"UPDATE {sch}.equity SET cash = cash + %s, equity = equity + %s WHERE id = %s",
                        [(share + settled(t(ts))[1][k],) * 2 + (i,) for i, ts, k in mine])
    print(f"  equity: {len(mine)} specialist snapshots since the split shifted up by their share + Sadie's old profit")
    n = c.execute(f"DELETE FROM {sch}.equity WHERE season = %s AND strategy = 'heavy_maker'", (SEASON,)).rowcount
    print(f"  equity: {n} Sadie snapshots removed")

    # Starting money
    c.execute(f"UPDATE {sch}.accounts SET starting_cash = %s, created_at = %s WHERE strategy = ANY(%s)",
              (share, created, team))
    c.execute(f"UPDATE {sch}.accounts SET starting_cash = 0 WHERE strategy = 'heavy_maker'")

    # The bot's saved state: let it rebuild these accounts from the records
    row = c.execute(f"SELECT data FROM {sch}.status WHERE key = '_state'").fetchone()
    if row:
        st = json.loads(row[0])
        for k in ["heavy_maker", *team]:
            (st.get("accounts") or {}).pop(k, None)
            (st.get("peaks") or {}).pop(k, None)
        c.execute(f"UPDATE {sch}.status SET data = %s WHERE key = '_state'", (json.dumps(st),))

    # Checks
    after = c.execute(f"SELECT sum(pnl), count(*) FROM {sch}.settlements WHERE season = %s", (SEASON,)).fetchone()
    assert abs(after[0] - before[0]) < 1e-6 and after[1] == before[1]
    for tb in tables + ["equity"]:
        left = c.execute(f"SELECT count(*) FROM {sch}.{tb} WHERE season = %s AND strategy = 'heavy_maker'",
                         (SEASON,)).fetchone()[0]
        assert left == 0, (tb, left)
    tot = c.execute(f"SELECT sum(starting_cash) FROM {sch}.accounts WHERE strategy = ANY(%s)", (team,)).fetchone()[0]
    assert abs(tot - start) < 1e-6
    for k in team:
        p = c.execute(f"SELECT coalesce(sum(pnl), 0), count(*) FROM {sch}.settlements WHERE season = %s AND strategy = %s",
                      (SEASON, k)).fetchone()
        print(f"  {k:10s} {p[1]:6d} settled bets, profit ${p[0]:+,.2f}, worth ${share + p[0]:,.2f}")

    if DRY:
        c.rollback()
    c.execute(f"DELETE FROM {sch}.status WHERE key = '_lease:tick'")
    c.commit()
    print("  rolled back" if DRY else "  committed")
