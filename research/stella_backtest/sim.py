"""
Shared pieces for the Stella backtests: load the fetched candles, replay one rule over
every market the way the bot trades, and run a money-managed pool over the resulting bets.

How a market is replayed (same as desk/backtest/seed.py, which mirrors the hosted bot):
  - the bot looks every 2 minutes, on even minutes, at the candle that just closed
  - taker: the order goes in at the ask it saw and fills at the NEXT minute's ask, only
    if that's still at or under it (otherwise nothing; it looks again 2 minutes later).
    "taker0" instead fills right away at the ask it saw: the hosted bot sends its order
    seconds after looking, so the truth is between the two
  - maker (the patient twin): a bid one tick above the best bid (never at the ask),
    left for ~110 seconds; it fills if the best bid later drops below it (sellers went
    through us), the same rule as research/fast_bot/twins_candles.py
  - at most one bet per market, held to settlement
"""
from __future__ import annotations

import glob
import gzip
import json
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

COIN = {"KXBTC15M": "BTC", "KXETH15M": "ETH", "KXSOL15M": "SOL", "KXXRP15M": "XRP", "KXDOGE15M": "DOGE"}
TZ = "America/Vancouver"


def tick(p: float) -> float:
    """Kalshi's tapered_deci_cent ladder: 0.1c steps under 10c and over 90c, 1c between."""
    return 0.001 if p < 0.10 - 1e-9 or p > 0.90 + 1e-9 else 0.01


def load(data_dir: str, series: list[str]) -> list[dict]:
    out = {}
    for s in series:  # live-window files and archive files (-a) can overlap: one copy per ticker
        for path in sorted(glob.glob(f"{data_dir}/{s}-*.json.gz")):
            for tk, m in json.load(gzip.open(path, "rt")).items():
                if m["result"] not in ("yes", "no") or m["close"] - m["open"] != 900 or not m["c"]:
                    continue
                out[tk] = ({"coin": COIN[s], "ticker": tk, "open": m["open"], "close": m["close"],
                            "y": 1 if m["result"] == "yes" else 0, "c": {r[0]: r[1:] for r in m["c"]}})
    return sorted(out.values(), key=lambda m: m["close"])


@dataclass(frozen=True)
class Rule:
    lo: float = 0.92
    hi: float = 0.99
    min_s: int = 300
    max_s: int = 540
    max_spread: float = 0.02
    mode: str = "taker"  # taker (next-minute fill) | taker0 (fill at the ask seen) | maker (bid + `improve` ticks)
    improve: int = 1

    @property
    def name(self) -> str:
        how = self.mode if self.mode.startswith("taker") else f"maker+{self.improve}"
        return f"{self.lo:.2f}-{self.hi:.2f} {self.min_s // 60}-{self.max_s // 60}m {how}"


def replay(m: dict, r: Rule) -> Optional[tuple]:
    """(fill ts, side, price, won, minute volume) for this market, or None."""
    c, close = m["c"], m["close"]
    t = (m["open"] // 120 + 1) * 120
    while t < close - 60:
        row = c.get(t)
        secs = close - t
        if row and r.min_s <= secs <= r.max_s:
            bid, ask = row[0], row[1]
            if 0 < bid < ask < 1 and ask - bid <= r.max_spread + 1e-9:
                side = None
                if r.lo <= ask <= r.hi:
                    side, s_bid, s_ask = "yes", bid, ask
                elif r.lo <= 1 - bid <= r.hi:
                    side, s_bid, s_ask = "no", 1 - ask, 1 - bid
                if side:
                    won = (m["y"] == 1) == (side == "yes")
                    if r.mode == "taker0":
                        return (t, side, round(s_ask, 4), won, row[4])
                    if r.mode == "taker":
                        n = c.get(t + 60)
                        if n:
                            fa = n[1] if side == "yes" else 1 - n[0]
                            if 0 < fa <= s_ask + 1e-9:
                                return (t + 60, side, round(fa, 4), won, n[4])
                    else:
                        px = min(s_bid + r.improve * tick(s_bid), s_ask - tick(s_ask - 1e-6))
                        px = round(max(px, s_bid), 4)
                        for k in (t + 60, t + 120):
                            if k >= close:
                                break
                            n = c.get(k)
                            if n and ((side == "yes" and n[2] < px - 1e-9) or (side == "no" and n[3] > 1 - px + 1e-9)):
                                return (k, side, px, won, n[4])
        t += 120
    return None


def bets(markets: list[dict], r: Rule) -> pd.DataFrame:
    rows = []
    for m in markets:
        b = replay(m, r)
        if b:
            rows.append((m["coin"], m["ticker"], m["close"], *b))
    df = pd.DataFrame(rows, columns=["coin", "ticker", "close", "t", "side", "price", "won", "vol"])
    if len(df):
        local = pd.to_datetime(df.close, unit="s", utc=True).dt.tz_convert(TZ)
        df["day"] = local.dt.strftime("%Y-%m-%d")
        df["month"] = local.dt.strftime("%Y-%m")
    return df


def fee_exact(p, maker: bool, maker_rate: float = 0.0):
    return (maker_rate if maker else 0.07) * p * (1 - p)


def per_dollar(df: pd.DataFrame, maker: bool, maker_rate: float = 0.0) -> pd.Series:
    """Profit per $1 staked at a size big enough that fee rounding doesn't matter."""
    f = fee_exact(df.price, maker, maker_rate)
    return (df.won.astype(float) - df.price - f) / (df.price + f)


def tstat(df: pd.DataFrame, roi: pd.Series) -> float:
    """Skill-or-luck: t of daily totals (bets in one window win or lose together)."""
    if df.empty:
        return float("nan")
    daily = roi.groupby(df.day).sum()
    return float(daily.mean() / daily.std(ddof=1) * math.sqrt(len(daily))) if len(daily) > 2 and daily.std() > 0 else float("nan")


# --- Money management -------------------------------------------------------------------------


def order_fee(p: float, n: float, maker: bool, rounding: str, maker_rate: float = 0.0) -> float:
    raw = fee_exact(p, maker, maker_rate) * n
    if raw <= 0:
        return 0.0
    return math.ceil(raw * 100 - 1e-9) / 100 if rounding == "cent" else raw


def rows_of(df: pd.DataFrame) -> list[tuple]:
    """The bets as (fill ts, close ts, price, won, minute volume, day), in fill order."""
    d = df.sort_values("t")
    return list(zip(d.t.tolist(), d.close.tolist(), d.price.tolist(), d.won.tolist(), d.vol.tolist(), d.day.tolist()))


def run_pool(rows, start: float, pct: float = 0.0, fixed: float = 0.0, maker: bool = False,
             rounding: str = "cent", liq: float = 0.25, daily_stop: float = 0.10, brake_dd: float = 0.25,
             brake: float = 0.5, min_bet: float = 0.25, maker_rate: float = 0.0, whole: bool = False) -> dict:
    """
    One pool, compounding, with the bot's guardrails: each bet is `pct` of the pool (or `fixed`
    dollars), in 0.01-contract steps (or whole contracts), never more than `liq` of what traded in
    the fill minute, nothing new after a `daily_stop` down day, bets halved `brake_dd` below the high.
    """
    cash, peak = start, start
    open_: list[tuple[int, float, float, float]] = []  # (close ts, contracts, payout per contract, cost)
    eq_by_day: dict[str, float] = {}
    day, day_open = None, start
    fees = staked = 0.0
    n_bets = capped = skipped = 0
    if isinstance(rows, pd.DataFrame):
        rows = rows_of(rows)
    for t, close, price, won, vol, bday in rows:
        # settle everything that closed before this fill
        if open_ and min(o[0] for o in open_) <= t:
            keep = []
            for o in open_:
                if o[0] <= t:
                    cash += o[1] * o[2]
                else:
                    keep.append(o)
            open_ = keep
        equity = cash + sum(o[3] for o in open_)  # open bets at what they cost
        if bday != day:
            if day:
                eq_by_day[day] = equity
            day, day_open = bday, equity
        peak = max(peak, equity)
        if day_open > 0 and equity / day_open - 1 <= -daily_stop:
            skipped += 1
            continue
        size = equity * pct if pct else fixed
        if pct and equity < peak * (1 - brake_dd):
            size *= brake
        if size < min_bet:
            skipped += 1
            continue
        n = size / price
        n = math.floor(n) if whole else math.floor(n * 100 + 1e-6) / 100
        cap = liq * vol
        if n > cap:
            n = math.floor(cap) if whole else math.floor(cap * 100) / 100
            capped += 1
        if n < (1 if whole else 0.01):
            skipped += 1
            continue
        fee = order_fee(price, n, maker, rounding, maker_rate)
        cost = n * price + fee
        if cost > cash:
            skipped += 1
            continue
        cash -= cost
        fees += fee
        staked += n * price
        n_bets += 1
        open_.append((close, n, 1.0 if won else 0.0, cost))
    for o in open_:
        cash += o[1] * o[2]
    if day:
        eq_by_day[day] = cash
    eq = pd.Series(eq_by_day)
    dd = (eq / eq.cummax() - 1).min() if len(eq) else 0.0
    daily = eq.pct_change().fillna(eq.iloc[0] / start - 1) if len(eq) else pd.Series(dtype=float)
    return {"end": cash, "ret": cash / start - 1, "max_dd": float(dd), "worst_day": float(daily.min()) if len(daily) else 0,
            "bets": n_bets, "capped": capped, "skipped": skipped, "fees": fees, "staked": staked,
            "fee_per_dollar": fees / staked if staked else 0, "days": len(eq), "equity": eq}
