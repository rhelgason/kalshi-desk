"""
Does the candle rule for the twin's fills hold up against Kalshi's real trade tape?

    python validate_tape.py data/ out/ [markets=400]

The backtest says a resting bid fills if the minute's best bid later drops below it. Here,
for a random sample of markets since Kalshi's trade-history cutoff, every bid the twin would
have posted is checked against the real trades in its ~110 seconds:
  - YES bid at p: filled if a taker SOLD yes (taker_book_side "ask") at a yes price below p
    (they went through us) or at p (we'd be filled if no one else bid p first)
  - NO bid at p: the same for takers BUYING yes at a yes price above 1 - p (or at it)
and how many contracts sellers traded through our price, which caps how much the twin could buy.
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
from datetime import datetime

import httpx
import pandas as pd

from fetch import get
from sim import Rule, load, tick

DATA, OUT = sys.argv[1], sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 400
CUTOFF = datetime.fromisoformat("2026-08-26T00:00:00+00:00").timestamp()


def attempts(m: dict, r: Rule) -> list[tuple]:
    """Every bid the twin posts in this market: (ts, side, price, candle says filled)."""
    out = []
    c, close = m["c"], m["close"]
    t = (m["open"] // 120 + 1) * 120
    while t < close - 60:
        row = c.get(t)
        if row and r.min_s <= close - t <= r.max_s:
            bid, ask = row[0], row[1]
            side = None
            if 0 < bid < ask < 1 and ask - bid <= r.max_spread + 1e-9:
                if r.lo <= ask <= r.hi:
                    side, s_bid, s_ask = "yes", bid, ask
                elif r.lo <= 1 - bid <= r.hi:
                    side, s_bid, s_ask = "no", 1 - ask, 1 - bid
            if side:
                px = round(max(min(s_bid + r.improve * tick(s_bid), s_ask - tick(s_ask - 1e-6)), s_bid), 4)
                filled = False
                for k in (t + 60, t + 120):
                    n = c.get(k)
                    if k < close and n and ((side == "yes" and n[2] < px - 1e-9) or (side == "no" and n[3] > 1 - px + 1e-9)):
                        filled = True
                        break
                out.append((t, side, px, filled))
                if filled:
                    return out
        t += 120
    return out


async def main() -> None:
    random.seed(11)
    ms = [m for m in load(DATA, ["KXBTC15M", "KXETH15M", "KXSOL15M", "KXXRP15M", "KXDOGE15M"]) if m["open"] > CUTOFF]
    rule = Rule(mode="maker", improve=1)
    pool = [(m, a) for m in ms for a in [attempts(m, rule)] if a]
    sample = random.sample(pool, min(N, len(pool)))
    rows = []
    async with httpx.AsyncClient(timeout=60) as http:
        sem = asyncio.Semaphore(4)

        async def one(m, atts):
            for t, side, px, cfill in atts:
                trades, cur = [], None
                while True:  # busy markets trade thousands of times in two minutes: page through all of it
                    async with sem:
                        d = await get(http, "/markets/trades", {"ticker": m["ticker"], "limit": 1000, "min_ts": t,
                                                                "max_ts": t + 110, **({"cursor": cur} if cur else {})})
                    trades += d.get("trades") or []
                    cur = d.get("cursor")
                    if not cur or not d.get("trades"):
                        break
                through = at = 0.0
                for tr in trades:
                    yp, n = float(tr["yes_price_dollars"]), float(tr["count_fp"])
                    book = tr.get("taker_book_side") or ("bid" if tr["taker_side"] == "yes" else "ask")
                    if side == "yes" and book == "ask":
                        through += n if yp < px - 1e-9 else 0
                        at += n if abs(yp - px) < 1e-9 else 0
                    if side == "no" and book == "bid":
                        through += n if yp > 1 - px + 1e-9 else 0
                        at += n if abs(yp - (1 - px)) < 1e-9 else 0
                won = (m["y"] == 1) == (side == "yes")
                rows.append({"coin": m["coin"], "ticker": m["ticker"], "t": t, "side": side, "px": px, "won": won,
                             "candle": cfill, "tape_through": through, "tape_at": at})

        await asyncio.gather(*(one(m, a) for m, a in sample))
    df = pd.DataFrame(rows)
    os.makedirs(OUT, exist_ok=True)
    df.to_csv(f"{OUT}/tape_check.csv", index=False)
    df["tape"] = df.tape_through > 0
    df["tape_or_at"] = (df.tape_through + df.tape_at) > 0
    print(f"{len(df)} bids in {df.ticker.nunique()} markets")
    print(pd.crosstab(df.candle, df.tape, rownames=["candle says filled"], colnames=["tape: sellers went through"]))
    print(pd.crosstab(df.candle, df.tape_or_at, rownames=["candle says filled"], colnames=["tape: through or at our price"]))
    # Per market: the first bid the tape fills, vs the candle's first fill
    def first(g, col):
        f = g[g[col]]
        return f.iloc[0] if len(f) else None
    res = []
    for col in ("candle", "tape", "tape_or_at"):
        picks = [r for _, g in df.groupby("ticker") for r in [first(g, col)] if r is not None]
        p = pd.DataFrame(picks)
        roi = (p.won.astype(float) - p.px) / p.px
        res.append({"fills by": col, "markets filled": len(p), "won": f"{p.won.mean() * 100:.1f}%",
                    "avg price": round(p.px.mean(), 4), "c per $1": round(roi.mean() * 100, 2)})
    print(pd.DataFrame(res).to_string(index=False))
    f = df[df.tape]
    print("contracts sellers traded through our bid, when they did: median",
          f.tape_through.median(), " 10th pct", f.tape_through.quantile(0.1))


asyncio.run(main())
