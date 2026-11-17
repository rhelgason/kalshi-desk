

def test_prune_logs_keeps_bets_and_thins_old_history():
    from datetime import datetime, timedelta, timezone
    from desk.paper.ledger import Ledger
    led = Ledger(":memory:")
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=30)
    iso = lambda t: t.isoformat()
    for m in range(0, 120, 10):  # two hours of old snapshots, six per hour
        led._write("INSERT INTO equity(ts, strategy, cash, equity, season) VALUES (?, ?, ?, ?, ?)",
                   (iso(old + timedelta(minutes=m)), "a", 1, 1, 1))
    led._write("INSERT INTO equity(ts, strategy, cash, equity, season) VALUES (?, ?, ?, ?, ?)", (iso(now), "a", 1, 1, 1))
    led._write("INSERT INTO decisions(ts, season, strategy, ticker, side, limit_price, count, filled, outcome, reason)"
               " VALUES (?, 1, 'a', 'T', 'yes', 0.9, 1, 0, 'x', 'y')", (iso(old),))
    led._write("INSERT INTO market_tape(ts, ticker) VALUES (?, 'T')", (iso(old),))
    led._write("INSERT INTO market_tape(ts, ticker) VALUES (?, 'T')", (iso(now),))
    led._write("INSERT INTO settlements(ts, strategy, ticker, yes_value, pnl, season) VALUES (?, 'a', 'T', 1, 0.1, 1)", (iso(old),))
    assert led.prune_logs()
    n = lambda t: led._rows(f"SELECT count(*) AS n FROM {t}")[0]["n"]
    assert 3 <= n("equity") <= 5  # 13 before: the season start, the last of each old clock hour (2-3), and today's
    assert n("decisions") == 0 and n("market_tape") == 1 and n("settlements") == 1
    assert not led.prune_logs()  # not again within 6 hours
