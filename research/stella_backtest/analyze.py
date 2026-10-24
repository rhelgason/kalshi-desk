"""
The big Stella backtest: every 15-minute BTC/ETH/SOL (and XRP/DOGE when fetched) market Kalshi has.

    python analyze.py data/ out/

1. Stella exactly as hired (92-99c, 5-9 minutes left), taker vs the patient twin, by coin and by
   period, including all the history the Oct 23 scan never looked at.
2. A grid of nearby rules, picked on the first half of history and judged on the second.
3. Bet sizing: pool sizes x bet sizes with Kalshi's fee rounded up to the cent per order.
4. 30-day outcomes by resampling whole days, for the setups worth considering with real money.
"""
from __future__ import annotations

import itertools
import json
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

from sim import Rule, bets, load, per_dollar, rows_of, run_pool, tstat

DATA, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
SERIES = [s for s in os.environ.get("SERIES", "KXBTC15M,KXETH15M,KXSOL15M,KXXRP15M,KXDOGE15M").split(",")
          if any(f.startswith(s) for f in os.listdir(DATA))]
MAKER_RATE = json.load(open(f"{DATA}/maker_rates.json")) if os.path.exists(f"{DATA}/maker_rates.json") else {}
SCAN_TRAIN, SCAN_TEST, SCAN_END = "2026-07-25", "2026-09-23", "2026-10-22"
MARKETS: list[dict] = []
lines: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    lines.append(s)


def table(df: pd.DataFrame, floatfmt: str = "{:.2f}") -> None:
    cols = list(df.columns)
    say("| " + " | ".join(str(c) for c in cols) + " |")
    say("|" + "---|" * len(cols))
    for _, r in df.iterrows():
        say("| " + " | ".join(floatfmt.format(v) if isinstance(v, float) else str(v) for v in r.values) + " |")
    say()


def maker_rate(df: pd.DataFrame) -> pd.Series:
    return df.coin.map(lambda c: MAKER_RATE.get(c, 0.0))


def roi(df: pd.DataFrame, maker: bool) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    if not maker:
        return per_dollar(df, False)
    f = maker_rate(df) * df.price * (1 - df.price)
    return (df.won.astype(float) - df.price - f) / (df.price + f)


def stats(df: pd.DataFrame, maker: bool) -> dict:
    if df.empty:
        return {"bets": 0}
    r = roi(df, maker)
    days = df.day.nunique()
    months = r.groupby(df.month).mean()
    return {"bets": len(df), "per_day": round(len(df) / max(days, 1), 1), "won": round(df.won.mean() * 100, 1),
            "avg_price": round(df.price.mean(), 3), "c_per_$1": round(r.mean() * 100, 2), "t": round(tstat(df, r), 2),
            "months_up": f"{(months > 0).sum()}/{len(months)}"}


def run_rule(r: Rule) -> tuple[Rule, pd.DataFrame]:
    return r, bets(MARKETS, r)


def main() -> None:
    global MARKETS
    MARKETS = load(DATA, SERIES)
    say(f"# Stella backtest ({pd.Timestamp.now(tz='America/Vancouver'):%Y-%m-%d})")
    say()
    cov = pd.DataFrame([(m["coin"], m["close"]) for m in MARKETS], columns=["coin", "close"])
    cov["day"] = pd.to_datetime(cov.close, unit="s", utc=True).dt.tz_convert("America/Vancouver").dt.strftime("%Y-%m-%d")
    say("## Data")
    say()
    table(cov.groupby("coin").agg(markets=("close", "size"), first=("day", "min"), last=("day", "max")).reset_index())
    if MAKER_RATE:
        say(f"Maker fee rates by coin (from GET /series): {MAKER_RATE}")
        say()

    stella = Rule()
    instant = Rule(mode="taker0")
    twin = Rule(mode="maker", improve=1)
    join = Rule(mode="maker", improve=0)
    with Pool(4) as pool:
        base = dict(pool.map(run_rule, [stella, instant, twin, join]))

    say("## 1. Stella as hired: 92-99c favorites, 5-9 minutes left")
    say()
    say("c_per_$1 is profit per $1 bet at a size where fee rounding doesn't matter (taker pays 7% x P x (1-P);")
    say("the twin pays the series' maker fee, zero on most). t is the daily-totals t-statistic: about 2+ is hard to get by luck.")
    say()
    rows = []
    for label, r in (("Stella (taker, next-minute fill)", stella), ("Stella (taker, instant fill)", instant),
                     ("Twin: bid +1 tick", twin), ("Twin: join the bid", join)):
        df = base[r]
        maker = r.mode == "maker"
        rows.append({"who": label, "coins": "all", **stats(df, maker)})
        for coin in sorted(df.coin.unique()):
            rows.append({"who": label, "coins": coin, **stats(df[df.coin == coin], maker)})
    table(pd.DataFrame(rows).fillna(""))

    say("### By period (all coins)")
    say()
    say(f"The Oct 23 scan picked Stella on {SCAN_TRAIN} to {SCAN_TEST} and checked her to {SCAN_END}.")
    say("Everything before and after was never used to choose her: the honest test.")
    say()
    periods = [("before the scan (unseen)", None, SCAN_TRAIN), ("scan: picked on", SCAN_TRAIN, SCAN_TEST),
               ("scan: checked on", SCAN_TEST, SCAN_END), ("after the scan (unseen)", SCAN_END, None)]
    rows = []
    for label, r in (("Stella", stella), ("Stella instant", instant), ("Twin +1", twin)):
        df = base[r]
        for pname, a, b in periods:
            sel = df[((df.day >= a) if a else True) & ((df.day < b) if b else True)]
            rows.append({"who": label, "period": pname, **stats(sel, r.mode == "maker")})
    table(pd.DataFrame(rows).fillna(""))

    say("### Month by month (c per $1, all coins)")
    say()
    mm = []
    for label, r in (("Stella", stella), ("Twin +1", twin)):
        df = base[r]
        g = roi(df, r.mode == "maker").groupby(df.month)
        mm.append(pd.DataFrame({"month": g.mean().index, f"{label} c/$1": (g.mean() * 100).round(2).values,
                                f"{label} bets": g.size().values}))
    month_tbl = mm[0].merge(mm[1], on="month", how="outer").sort_values("month")
    table(month_tbl.fillna(""))

    say("### How the twin's fills differ")
    say()
    s, t = base[stella], base[twin]
    both = s.merge(t, on="ticker", suffixes=("_s", "_t"))
    only_s, only_t = s[~s.ticker.isin(t.ticker)], t[~t.ticker.isin(s.ticker)]
    say(f"- Stella bet {len(s):,} markets, the twin got filled in {len(t):,}. Stella's next-minute rule skips a market "
        f"whenever the price rose in that minute; the twin's bid usually fills because prices at 92-99c wobble by tenths of a cent.")
    say(f"- Where both bet ({len(both):,}): Stella won {both.won_s.mean() * 100:.1f}% at {both.price_s.mean():.4f}, "
        f"the twin {both.won_t.mean() * 100:.1f}% at {both.price_t.mean():.4f}.")
    if len(only_s):
        say(f"- Only Stella ({len(only_s):,}): won {only_s.won.mean() * 100:.1f}%, {roi(only_s, False).mean() * 100:.2f}c per $1.")
    if len(only_t):
        say(f"- Only the twin ({len(only_t):,}): won {only_t.won.mean() * 100:.1f}%, {roi(only_t, True).mean() * 100:.2f}c per $1.")
    say()

    # 2. Grid, picked on the first half
    grid = [Rule(lo, hi, a, b, mode=mode, improve=imp)
            for lo, hi in [(0.85, 0.95), (0.88, 0.99), (0.90, 0.99), (0.92, 0.99), (0.94, 0.99), (0.92, 0.97), (0.95, 0.99)]
            for a, b in [(120, 300), (180, 420), (300, 540), (300, 780), (420, 660), (540, 780)]
            for mode, imp in [("taker", 1), ("taker0", 1), ("maker", 1), ("maker", 0)]]
    with Pool(4) as pool:
        res = pool.map(run_rule, grid)
    days = sorted({m_["day"] for m_ in []} | set(pd.concat([df.day for _, df in res if len(df)]).unique()))
    mid = days[len(days) // 2]
    rows = []
    for r, df in res:
        maker = r.mode == "maker"
        a, b = df[df.day < mid], df[df.day >= mid]
        ra, rb = roi(a, maker), roi(b, maker)
        months = roi(df, maker).groupby(df.month).mean() if len(df) else pd.Series(dtype=float)
        rows.append({"rule": r.name, "bets/day": round(len(df) / max(len(days), 1), 1),
                     "1st half c/$1": round(ra.mean() * 100, 2) if len(a) else np.nan, "1st t": round(tstat(a, ra), 2),
                     "2nd half c/$1": round(rb.mean() * 100, 2) if len(b) else np.nan, "2nd t": round(tstat(b, rb), 2),
                     "months up": f"{(months > 0).sum()}/{len(months)}"})
    g = pd.DataFrame(rows)
    say(f"## 2. {len(grid)} nearby rules: picked on the first half (to {mid}), judged on the second")
    say()
    say("Top 15 by first-half t. If the first half's winners keep winning in the second, the edge is real;")
    say("if they fall apart, the first half was luck.")
    say()
    table(g.sort_values("1st t", ascending=False).head(15))
    say(f"Of {len(g)} rules, {(g['1st t'] > 2).sum()} cleared t > 2 in the first half, {(g['2nd t'] > 2).sum()} in the "
        f"second, {((g['1st t'] > 2) & (g['2nd t'] > 2)).sum()} in both. "
        f"{(g['2nd half c/$1'] > 0).mean() * 100:.0f}% made money in the second half.")
    say()
    g.to_csv(f"{OUT}/grid.csv", index=False)

    # 3. Sizing
    say("## 3. Bet sizing with real fees (rounded up to the cent on every order)")
    say()
    say("Whole history, compounding, the bot's guardrails (10% daily stop, half-size bets 25% below the high),")
    say("bets in 0.01-contract steps, never more than a quarter of what traded in the fill minute.")
    say()
    cands = {"Stella": (stella, False), "Stella instant": (instant, False), "Twin +1": (twin, True)}
    best = g.sort_values("1st t", ascending=False).iloc[0]["rule"]
    if best not in (stella.name, twin.name):
        br = next(r for r, _ in res if r.name == best)
        cands[f"Grid pick ({best})"] = (br, br.mode == "maker")
    rmap = {r: df for r, df in res}
    rmap.update(base)
    sizing = []
    for label, (r, maker) in cands.items():
        df = rows_of(rmap[r])
        for start in (100, 250, 500, 1000, 2500, 5000):
            for kind, val in [("pct", 0.005), ("pct", 0.01), ("pct", 0.02), ("pct", 0.03), ("pct", 0.05), ("pct", 0.08),
                              ("fixed", 1), ("fixed", 2), ("fixed", 5), ("fixed", 10), ("fixed", 25), ("fixed", 50)]:
                if kind == "fixed" and val > start * 0.1:
                    continue
                kw = {"pct": val} if kind == "pct" else {"fixed": float(val)}
                out = run_pool(df, start, maker=maker, rounding="cent", **kw)
                ex = run_pool(df, start, maker=maker, rounding="exact", **kw)
                eq = out["equity"]
                monthly = eq.groupby(eq.index.str[:7]).last()
                prev = monthly.shift(1).fillna(start)
                sizing.append({"who": label, "start": start, "bet": f"{val * 100:g}%" if kind == "pct" else f"${val}",
                               "end": round(out["end"], 0), "return": f"{out['ret'] * 100:.0f}%",
                               "median month": f"{((monthly / prev - 1).median()) * 100:.1f}%",
                               "worst month": f"{((monthly / prev - 1).min()) * 100:.1f}%",
                               "max drop": f"{out['max_dd'] * 100:.0f}%", "worst day": f"{out['worst_day'] * 100:.0f}%",
                               "fee c/$1": round(out["fee_per_dollar"] * 100, 2),
                               "if fees were exact": f"{ex['ret'] * 100:.0f}%",
                               "capped": out["capped"]})
    sz = pd.DataFrame(sizing)
    sz.to_csv(f"{OUT}/sizing.csv", index=False)
    for label in cands:
        say(f"### {label}")
        say()
        table(sz[sz.who == label].drop(columns="who"))

    # 4. 30-day outcomes by resampling days
    say("## 4. What 30 days could look like (2,000 resampled months of real days)")
    say()
    rng = np.random.default_rng(7)
    boot = []
    for label, (r, maker) in cands.items():
        df = rmap[r].sort_values("t").reset_index(drop=True)
        days_rows = [rows_of(g_) for _, g_ in df.groupby("day")]
        for start, kw in [(100, {"pct": 0.01}), (100, {"fixed": 1.0}), (250, {"pct": 0.01}), (500, {"pct": 0.01}),
                          (500, {"pct": 0.02}), (1000, {"pct": 0.01}), (1000, {"pct": 0.02}), (2500, {"pct": 0.01})]:
            ends = []
            for _ in range(2000):
                sample = []
                for i, k in enumerate(rng.choice(len(days_rows), 30)):
                    day_rows = days_rows[k]
                    shift = i * 86400 - day_rows[0][0] + 1_800_000_000  # lay the days end to end
                    sample += [(t + shift, c + shift, p, w, v, f"d{i:02d}") for t, c, p, w, v, _ in day_rows]
                ends.append(run_pool(sample, start, maker=maker, rounding="cent", **kw)["ret"])
            e = np.array(ends)
            boot.append({"who": label, "start": start, "bet": f"{kw.get('pct', 0) * 100:g}%" if "pct" in kw else f"${kw['fixed']:g}",
                         "chance of a loss": f"{(e < 0).mean() * 100:.0f}%", "bad month (5%)": f"{np.percentile(e, 5) * 100:.1f}%",
                         "typical": f"{np.median(e) * 100:.1f}%", "good month (95%)": f"{np.percentile(e, 95) * 100:.1f}%",
                         "typical $": round(np.median(e) * start, 2)})
    table(pd.DataFrame(boot))
    say("Resampling assumes the future looks like the whole history. If the edge is fading, it won't.")
    with open(f"{OUT}/REPORT.md", "w") as fh:
        fh.write("\n".join(lines) + "\n")
    for label, (r, _) in cands.items():
        rmap[r].to_csv(f"{OUT}/bets_{label.split(' (')[0].replace(' ', '_').replace('+', '').lower()}.csv.gz", index=False)


if __name__ == "__main__":
    main()
