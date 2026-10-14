"""Replay the 55-day bets with each bet sized as a % of the whole office pool."""
import math, sys
from collections import defaultdict
from twins_candles import load, run, edie, nick, betty
from tapelib import Spot, taker_fee

ms = load()
spot = Spot("binance1m")
roster = {}
for label, sig in (("Ellie", edie), ("Nora", nick), ("Bonnie", betty)):
    roster[label] = run(ms, sig, spot=spot, mode="maker", improve=1)
for label, sig in (("Edie", edie), ("Nick", nick), ("Betty", betty)):
    roster[label] = run(ms, sig, spot=spot, mode="taker")

def per_dollar(b):
    tk, side, px, n, fee, yes, t = b
    won = yes if side == "yes" else 1 - yes
    return (won - px) / px - (fee / (n * px) if n else 0)

def bets_for(names, shift=0.0):
    out = []
    for nm in names:
        rs = roster[nm]
        mu = sum(per_dollar(b) for b in rs) / len(rs)
        for b in rs:
            r = per_dollar(b)
            if shift is not None:
                r = r - mu * shift  # shift=1 removes the edge entirely, 2 flips it
            out.append((b[6], b[0], nm, r))
    out.sort()
    return out

def sim(bets, f, cap_window=None):
    pool, peak, worst_dd = 100.0, 100.0, 0.0
    by_day = defaultdict(float)
    start_of_day = {}
    windows = defaultdict(list)
    for t, tk, nm, r in bets:
        windows[tk].append((t, r))
    days = {}
    for tk in sorted(windows, key=lambda k: windows[k][0][0]):
        stake_total = 0
        pnl = 0
        for t, r in windows[tk]:
            stake = f * pool
            if cap_window and stake_total + stake > cap_window * pool:
                stake = max(0, cap_window * pool - stake_total)
            stake_total += stake
            pnl += stake * r
        d = int(windows[tk][0][0] // 86400)
        days.setdefault(d, pool)
        pool += pnl
        peak = max(peak, pool)
        worst_dd = max(worst_dd, 1 - pool / peak)
        days[d + 1] = pool
    ds = sorted(days)
    daily = [days[ds[i + 1]] / days[ds[i]] - 1 for i in range(len(ds) - 1)]
    return pool, min(daily), worst_dd

names = sys.argv[1].split(",") if len(sys.argv) > 1 else ["Ellie", "Nora", "Bonnie"]
for nm in roster:
    rs = roster[nm]
    print(nm, len(rs), "bets", f"{sum(per_dollar(b) for b in rs) / len(rs) * 100:+.2f}c per $1")
for label, shift in (("as backtested", 0.0), ("half the edge", 0.5), ("no edge at all", 1.0), ("edge reversed", 2.0)):
    print(f"\n== {label} ({'+'.join(names)}, $100 start, 55 days) ==")
    bets = bets_for(names, shift)
    for f in (0.01, 0.02, 0.03, 0.05, 0.08, 0.12):
        end, worst_day, dd = sim(bets, f, cap_window=0.25)
        print(f"  {f*100:4.0f}% per bet: ends ${end:8.2f}   worst day {worst_day*100:+6.1f}%   worst drop from peak {dd*100:5.1f}%")
