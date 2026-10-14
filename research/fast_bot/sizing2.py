import sys
from collections import defaultdict
import sizing as S

def sim(bets, f, window_cap, day_stop):
    pool, peak, dd = 100.0, 100.0, 0.0
    windows = defaultdict(list)
    for t, tk, nm, r in bets:
        windows[tk].append((t, r))
    day, day_open, stopped, daily, stops = None, pool, False, [], 0
    for tk in sorted(windows, key=lambda k: windows[k][0][0]):
        d = int(windows[tk][0][0] // 86400)
        if d != day:
            if day is not None:
                daily.append(pool / day_open - 1)
            day, day_open, stopped = d, pool, False
        if stopped:
            continue
        used, pnl = 0.0, 0.0
        for t, r in windows[tk]:
            stake = min(f * pool, window_cap * pool - used)
            if stake <= 0:
                break
            used += stake
            pnl += stake * r
        pool += pnl
        peak = max(peak, pool); dd = max(dd, 1 - pool / peak)
        if pool / day_open - 1 <= -day_stop:
            stopped, stops = True, stops + 1
    daily.append(pool / day_open - 1)
    return pool, min(daily), dd, stops

names = ["Ellie", "Nora", "Bonnie"]
for label, shift in (("as backtested", 0.0), ("half the edge", 0.5), ("no edge", 1.0)):
    bets = S.bets_for(names, shift)
    print(f"\n== {label} ==")
    for f in (0.005, 0.01, 0.015, 0.02):
        for cap, stop in ((1.0, 9.0), (0.03, 0.10)):
            end, wd, dd, stops = sim(bets, f, cap, stop)
            g = "no guardrails      " if cap == 1.0 else f"window cap {cap*100:.0f}%, stop -{stop*100:.0f}%/day"
            print(f"  {f*100:4.1f}%/bet, {g}: ends ${end:7.2f}  worst day {wd*100:+6.1f}%  worst drop {dd*100:5.1f}%  stopped days {stops}")
