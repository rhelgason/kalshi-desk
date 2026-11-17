"""
The prediction model (11-17): where an office's money is likely to be in the months ahead, and why it won't keep
growing the way it did in its first weeks.

How money grows here. Each closing moment (every 15 minutes) some employees bid on that moment's favourites; a bid is
a share of the pool (bet_pct x level), so as the pool grows, every bid grows with it. Profit per day is

    profit = sum over bids of  (dollars filled) x (profit per $1 filled)

and both factors shrink as bids get bigger:
  * each 15-minute market only has so many sellers dipping into our price in its 5-9 minutes: past a few hundred
    dollars a bigger bid fills little more (the "capacity" of a coin's window);
  * the extra dollars fill at worse moments, so the profit per $1 falls, and for thin coins turns negative;
  * friends' offices bid in the same markets, beside the owner (Desk.family), so they share that capacity;
  * all coins closing at one moment share one window cap (16% of the pool), and some moments every coin loses
    at once: the bad days. The daily stop (15%) and slump brake (half-size bets 25% under the high) follow.

So a small pool compounds fast (each dollar is bet ~4-5 times a day at ~2c per $1), then the growth rate tapers as
bids reach each window's capacity, and with bets as a % of the pool it settles where the extra dollars stop earning.

The model replays it: a library of every coin window on Kalshi's real trade tape (research/forecast/library.py: the
live rule with the coin check, what a bid of any size would have filled and made, Aug 25 - Nov 2), sampled a whole
day at a time so coins that lose together still lose together. Each employee's profit per $1 is the tape's,
pulled toward what they've actually made on real money (more real bets, more weight), with that number's own
uncertainty drawn afresh for each simulated future. Weekly reviews promote and demote by the same thresholds the
office uses. Hourly Hazel and Weather Wendell have no tape library: they run on their real betting rate and edge,
with a size limit that is an assumption (marked in the output).

    from desk.forecast import Forecaster;  Forecaster.load().run(book)   ->  dict for the status row `_forecast`
"""

from __future__ import annotations

import gzip
import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from desk.hr import LEVELS

LIBRARY = Path(__file__).with_name("forecast_library.json.gz")
COIN_OF = {"maker_btc": "BTC", "maker_eth": "ETH", "maker_sol": "SOL", "maker_xrp": "XRP", "maker_doge": "DOGE",
           "maker_bnb": "BNB", "maker_near": "NEAR", "maker_zec": "ZEC", "maker_hype": "HYPE"}
PRIOR_BETS = 300  # how many real bets the tape's number counts for when the two are blended
PAPER_WEIGHT = 0.5  # a Training bet (paper, filled from Kalshi's real trades) counts as half a real one
BET_SD = 0.20  # one bet's profit per $1 varies by about this much (a 96c favourite: +4c or -100c)
# ...and however many bets we have, the market itself can change (more makers, calmer coins): at least this much
# doubt about any edge, shared by all employees (they all lean on the same dips)
REGIME_SD = 0.006
SLOTS = 96  # closing moments a day
HORIZON = 180
# Real bids so far fill like the tape up to ~$60 a window (11-17: 95-100% of the bid in windows that filled). Bigger
# bids are untested: past `tested` (the family's biggest real bids that filled, measured each run; at least TESTED),
# fills shrink by 1 / (1 + extra / room), room drawn per future around ROOM (x/÷ 2.5)
TESTED, ROOM, ROOM_SPREAD = 60.0, 1000.0, 2.5

# The two without a tape library (assumptions, shown as such): bets a day and edge come from their real record;
# `room` is the dollars one bet can fill before more stops filling, `zero` the size where the edge would be gone
SYNTHETIC = {
    "hourly_btc": {"prior_edge": 0.006, "prior_rate": 60.0, "room": 400.0, "zero": 2000.0, "fill": 0.45, "slot": 0},
    "weather_maker": {"prior_edge": 0.038, "prior_rate": 6.0, "room": 40.0, "zero": 300.0, "fill": 1.0, "slot": None},
}


def level_mult(level: int) -> float:
    return LEVELS[max(0, min(level, len(LEVELS) - 1))][1]


@dataclass
class Staff:
    """One employee as the model sees them."""
    key: str
    level: int
    edge: float  # profit per $1, blended (tape + real)
    edge_sd: float
    tape_edge: Optional[float]  # the tape's, at small sizes (None: no library)
    keep: float = 1.0  # share of the tape's windows they actually bet (real betting rate vs the tape's)
    rate: float = 0.0  # synthetic: bets a day
    real_bets: int = 0
    real_edge: Optional[float] = None
    paper_bets: int = 0
    paper_edge: Optional[float] = None


@dataclass
class Book:
    """What the model starts from: one office's money, rules and staff, and the family's other money."""
    name: str
    equity: float
    settings: dict
    staff: list[Staff]
    others: float = 0.0  # the other offices' money (they bid beside this one, sharing each window, and grow with it)
    policy: dict = field(default_factory=dict)
    tested: float = TESTED  # the biggest family bid (one window) that real fills have vouched for
    history: list = field(default_factory=list)  # [(day, value)] of this season, for the model's own check


class Library:
    def __init__(self, data: dict):
        self.caps: list[float] = [float(c) for c in data["caps"]]
        # coin -> day -> [(slot, curve)], curve = [(spent, pnl) per cap]
        self.days: dict[str, dict[int, list]] = {}
        self.tape_edge: dict[str, float] = {}
        self.tape_rate: dict[str, float] = {}
        for coin, wins in data["coins"].items():
            by: dict[int, list] = {}
            spent = pnl = 0.0
            first = min(w[0] for w in wins); last = max(w[0] for w in wins)
            n = 0
            for w in wins:
                if not w[1]:
                    continue
                t = int(w[0]); by.setdefault(t // 86400, []).append(((t % 86400) // 900, w[2]))
                spent += w[2][1][0]; pnl += w[2][1][1]; n += 1
            self.days[coin] = by
            self.tape_edge[coin] = pnl / spent if spent else 0.0
            self.tape_rate[coin] = n / max(1.0, (last - first) / 86400)
        self.all_days = sorted(set().union(*(set(d) for d in self.days.values())))

    @classmethod
    def load(cls, path: Path = LIBRARY) -> "Library":
        with gzip.open(path, "rt") as f:
            return cls(json.load(f))

    def at(self, curve: list, bid: float) -> tuple[float, float]:
        """Dollars filled and profit for a bid of `bid` in one window (straight lines between the replayed sizes)."""
        caps = self.caps
        if bid <= caps[0]:
            s, p = curve[0]
            return s * bid / caps[0], p * bid / caps[0]
        if bid >= caps[-1]:
            return curve[-1][0], curve[-1][1]
        i = min(len(caps) - 2, int(math.log2(bid / caps[0])))
        while caps[i + 1] < bid:
            i += 1
        f = (bid - caps[i]) / (caps[i + 1] - caps[i])
        (s0, p0), (s1, p1) = curve[i], curve[i + 1]
        return s0 + f * (s1 - s0), p0 + f * (p1 - p0)


def synthetic_fill(key: str, bid: float) -> tuple[float, float]:
    """(dollars filled, edge multiplier) for one synthetic bet: fills flatten past `room`, the edge fades to `zero`."""
    s = SYNTHETIC[key]
    filled = s["fill"] * bid / (1 + bid / s["room"])
    return filled, max(-1.0, 1 - filled / s["zero"])


class Forecaster:
    def __init__(self, library: Library):
        self.lib = library

    @classmethod
    def load(cls) -> "Forecaster":
        return cls(Library.load())

    # -- one day of trading ------------------------------------------------------------------------------------
    def _day(self, rng: random.Random, staff: list[Staff], edges: dict[str, float], equity: float, st: dict,
             others_ratio: float, settings: dict, stats: Optional[dict], compound: bool = True, room: float = ROOM,
             tested: float = TESTED) -> float:
        """Trade one sampled day; returns the pool's value at its end. `st` carries peak across days."""
        lib = self.lib
        day = rng.choice(lib.all_days)
        moments: dict[int, list] = {}
        for s in staff:
            coin = COIN_OF.get(s.key)
            if coin:
                by = lib.days.get(coin)
                if not by:
                    continue
                wins = by.get(day)
                if wins is None:  # this coin's tape doesn't cover that day: one of its own days instead
                    wins = by[rng.choice(list(by))]
                for slot, curve in wins:
                    if s.keep >= 1 or rng.random() < s.keep:
                        moments.setdefault(slot, []).append((s, curve))
            elif s.key in SYNTHETIC and SYNTHETIC[s.key]["slot"] is not None:
                n = _poisson(rng, s.rate)
                for _ in range(n):
                    moments.setdefault(rng.randrange(0, SLOTS, 4), []).append((s, None))
        pct, cap_share = float(settings["bet_pct"]), float(settings["window_cap"])
        stop, brake_dd, brake_f = float(settings["daily_stop"]), float(settings["brake_drawdown"]), float(settings["brake_factor"])
        max_bet = float(settings.get("max_bet") or 0)
        open_, eq = equity, equity
        for slot in sorted(moments):
            if open_ > 0 and eq <= open_ * (1 - stop):
                break  # the daily stop: no new bets until midnight
            size = eq if compound else equity
            braked = st["peak"] > 0 and eq < st["peak"] * (1 - brake_dd)
            bids = []
            for s, curve in moments[slot]:
                b = size * pct * level_mult(s.level) * (brake_f if braked else 1.0)
                bids.append(min(b, max_bet) if max_bet > 0 else b)
            room = max(size, 0) * cap_share
            total = sum(bids)
            scale = min(1.0, room / total) if total > 0 else 0.0
            for (s, curve), b in zip(moments[slot], bids):
                b *= scale
                if b < 0.25:
                    continue
                e = edges[s.key]
                if curve is not None:
                    together = b * (1 + others_ratio)  # the family's bids share the window
                    spent, pnl = self.lib.at(curve, together)
                    share = b / together / (1 + max(0.0, together - tested) / room)
                    spent, pnl = spent * share, pnl * share
                    pnl += (e - s.tape_edge) * spent  # the tape's luck in this window, shifted to the blended edge
                else:
                    spent, fade = synthetic_fill(s.key, b * (1 + others_ratio))
                    spent *= b / (b * (1 + others_ratio))
                    pnl = spent * _outcome(rng, e * fade)
                eq += pnl
                if stats is not None:
                    r = stats.setdefault(s.key, [0, 0.0, 0.0]); r[0] += 1; r[1] += spent; r[2] += pnl
            st["peak"] = max(st["peak"], eq)
        # Weather settles once a day (each city-day its own market: no shared window)
        for s in staff:
            if s.key in SYNTHETIC and SYNTHETIC[s.key]["slot"] is None:
                for _ in range(_poisson(rng, s.rate)):
                    b = (eq if compound else equity) * pct * level_mult(s.level)
                    spent, fade = synthetic_fill(s.key, b)
                    pnl = spent * _outcome(rng, edges[s.key] * fade)
                    eq += pnl
                    if stats is not None:
                        r = stats.setdefault(s.key, [0, 0.0, 0.0]); r[0] += 1; r[1] += spent; r[2] += pnl
        st["peak"] = max(st["peak"], eq)
        return eq

    # -- many futures --------------------------------------------------------------------------------------------
    def paths(self, book: Book, n: int = 200, days: int = HORIZON, seed: int = 7, start: Optional[float] = None,
              reviews: bool = True) -> dict:
        rng = random.Random(seed)
        start = book.equity if start is None else start
        policy = book.policy or {}
        promote, demote = float(policy.get("promote_roi", 0.02)), float(policy.get("demote_roi", -0.03))
        min_bets = int(policy.get("min_settled", 20))
        confident = float(policy.get("promote_min_confidence", 0.8))
        ends: list[list[float]] = []
        levels: dict[str, list[list[int]]] = {s.key: [] for s in book.staff}
        worst_days: list[float] = []
        for _ in range(n):
            common = rng.gauss(0, 1)
            room = ROOM * ROOM_SPREAD ** rng.gauss(0, 1)
            edges = {s.key: s.edge + s.edge_sd * (0.8 * common + 0.6 * rng.gauss(0, 1)) for s in book.staff}
            staff = [Staff(**{**s.__dict__}) for s in book.staff]
            eq, st, line, week, worst = start, {"peak": start}, [start], {}, 0.0
            lv = {s.key: [s.level] for s in staff}
            season: dict[str, list] = {}
            # Every family office runs the same rules on the same markets, so they grow at about the same pace:
            # the others' share of each family bid stays what it is today
            ratio = book.others / start if start > 0 else 0.0
            for d in range(1, days + 1):
                before = eq
                eq = max(0.0, self._day(rng, staff, edges, eq, st, ratio, book.settings, week, room=room, tested=book.tested))
                worst = min(worst, eq / before - 1 if before > 0 else 0)
                line.append(eq)
                if reviews and d % 7 == 0:
                    for s in staff:
                        bets, spent, pnl = week.get(s.key, (0, 0.0, 0.0))
                        c = season.setdefault(s.key, [0, 0.0, 0.0])
                        c[0] += bets; c[1] += spent; c[2] += pnl
                        if bets >= min_bets and spent > 0:
                            roi = pnl / spent
                            # the office's skill-or-luck check on the season so far (hr: promote_min_confidence)
                            z = (c[2] / c[1]) / (BET_SD / math.sqrt(c[0])) if c[1] > 0 and c[0] else 0.0
                            sure = 0.5 * (1 + math.erf(z / math.sqrt(2))) if c[0] >= 30 else 0.5
                            if roi >= promote and s.level < len(LEVELS) - 1 and sure >= confident:
                                s.level += 1
                            elif roi <= demote and s.level > 0 and edges[s.key] <= 0:
                                s.level -= 1  # a bad week with an edge that's really there is "kept", as the office does
                        lv[s.key].append(s.level)
                    week = {}
            ends.append(line)
            worst_days.append(worst)
            for k in lv:
                levels[k].append(lv[k])
        return {"lines": ends, "levels": levels, "worst": worst_days}

    # -- did the model see the real book's season coming? -------------------------------------------------------
    def check(self, book: Book, n: int = 200) -> Optional[dict]:
        """Start from the season's first value with today's rules and staff (no reviews, levels at Associate) and see
        where the real value today falls among the model's futures: a percentile far from 50 means it's off."""
        h = book.history
        if not h or len(h) < 4:
            return None
        start, now = h[0][1], h[-1][1]
        days = len(h) - 1
        import copy
        b = copy.deepcopy(book)
        b.equity = start
        for s in b.staff:
            s.level = 0 if s.key in SYNTHETIC and SYNTHETIC[s.key]["slot"] is None else 1
        lines = self.paths(b, n=n, days=days, seed=3, reviews=False)["lines"]
        col = sorted(l[-1] for l in lines)
        return {"from": h[0][0], "start": round(start, 2), "days": days, "actual": round(now, 2),
                "p10": round(_q(col, 0.1), 2), "p50": round(_q(col, 0.5), 2), "p90": round(_q(col, 0.9), 2),
                "percentile": round(sum(x <= now for x in col) / len(col), 3),
                "actual_line": [[d, round(v, 2)] for d, v in h]}

    # -- the growth engine: profit a day at each pool size ------------------------------------------------------
    def engine(self, book: Book, sizes: list[float], settings: Optional[dict] = None, samples: int = 3) -> list[dict]:
        """Expected profit a day if the pool were `size` (no compounding, levels as now): the taper, as a curve."""
        settings = settings or book.settings
        edges = {s.key: s.edge for s in book.staff}
        out = []
        for size in sizes:
            rng = random.Random(11)
            stats: dict = {}
            total, n = 0.0, 0
            for day in self.lib.all_days * samples:
                rng.seed(hash((day, size, n)) & 0xFFFFFFFF)
                st = {"peak": size}
                total += self._fixed_day(rng, book, edges, size, st, day, settings, stats)
                n += 1
            per = {k: {"profit_day": round(v[2] / n, 2), "filled_day": round(v[1] / n, 2),
                       "per_dollar": round(v[2] / v[1], 4) if v[1] else 0.0} for k, v in stats.items()}
            out.append({"size": size, "profit_day": round(total / n, 2), "pct_day": round(total / n / size, 5),
                        "staff": per})
        return out

    def _fixed_day(self, rng, book, edges, size, st, day, settings, stats) -> float:
        lib = self.lib
        real = lib.all_days
        lib.all_days = [day]  # this exact day, every coin together
        try:
            ratio = book.others / book.equity if book.equity > 0 else 0.0
            # no daily stop or brake here: the engine is the average day's earning power
            s2 = {**settings, "daily_stop": 9.0, "brake_drawdown": 9.0}
            return self._day(rng, book.staff, edges, size, st, ratio, s2, stats, compound=False, tested=book.tested) - size
        finally:
            lib.all_days = real

    # -- a new friend's office -----------------------------------------------------------------------------------
    def newcomer(self, owner: Book, family: float, starts: tuple = (50, 100, 250, 500, 1000, 2500, 5000), n: int = 50) -> list:
        """What a new office would do from each starting amount: the owner's staff at the owner's levels (friends
        join that way), the whole family's money bidding beside it."""
        import copy
        out = []
        for amount in starts:
            b = copy.deepcopy(owner)
            b.equity, b.others, b.history = float(amount), family, []
            lines = self.paths(b, n=n, seed=21)["lines"]
            row = {"start": amount}
            for d in (30, len(lines[0]) - 1):
                col = sorted(l[d] for l in lines)
                row[f"d{d}"] = {"p10": round(_q(col, 0.1), 2), "p50": round(_q(col, 0.5), 2), "p90": round(_q(col, 0.9), 2)}
            out.append(row)
        # Fewer futures per amount, so a little noise: more money never shows a smaller result
        for k in [k for k in out[0] if k.startswith("d")]:
            for q in ("p10", "p50", "p90"):
                for i in range(1, len(out)):
                    out[i][k][q] = max(out[i][k][q], out[i - 1][k][q])
        return out

    # -- everything the cockpit shows ---------------------------------------------------------------------------
    def run(self, book: Book, n: int = 200, deposits: tuple = (0, 250, 500, 1000, 2500, 5000)) -> dict:
        res = self.paths(book, n=n)
        check = self.check(book)
        lines = res["lines"]
        days = len(lines[0]) - 1
        fan = []
        for d in range(0, days + 1, 3 if days > 60 else 1):
            col = sorted(l[d] for l in lines)
            fan.append({"day": d, **{f"p{q}": round(_q(col, q / 100), 2) for q in (10, 25, 50, 75, 90)}})
        end = sorted(l[-1] for l in lines)
        start = book.equity
        sizes = sorted({round(x, -1) for x in _logspace(max(50.0, start / 8), max(start * 40, 50_000), 22)} | {round(start, 2)})
        engine = self.engine(book, sizes)
        best = max(engine, key=lambda r: r["profit_day"])
        now = min(engine, key=lambda r: abs(r["size"] - start))
        stall = next((r["size"] for r in engine if r["size"] > best["size"] and r["profit_day"] <= 0.25 * best["profit_day"]), None)
        # With bets capped where the engine peaks (max_bet), past the peak profit holds instead of fading
        peak_bet = round(best["size"] * float(book.settings["bet_pct"]) * 2, 0)
        capped = self.engine(book, [r["size"] for r in engine if r["size"] >= best["size"]][:8],
                             settings={**book.settings, "max_bet": peak_bet}, samples=1)
        # More money in: the same futures (same days, same luck) from a bigger start, so the difference is the money
        what_if = []
        for dep in deposits:
            r = self.paths(book, n=max(80, n // 2), start=start + dep, seed=13)["lines"]
            row = {"deposit": dep}
            for d in (30, 90, days):
                col = sorted(l[min(d, days)] for l in r)
                row[f"d{d}"] = {"p10": round(_q(col, 0.1), 2), "p50": round(_q(col, 0.5), 2), "p90": round(_q(col, 0.9), 2)}
            what_if.append(row)
        staff = []
        for s in book.staff:
            lv = res["levels"][s.key]
            staff.append({
                "key": s.key, "level": s.level,
                "level_later": round(sorted(x[-1] for x in lv)[len(lv) // 2], 0) if lv and lv[0] else s.level,
                "edge": round(s.edge, 4), "edge_sd": round(s.edge_sd, 4),
                "tape_edge": None if s.tape_edge is None else round(s.tape_edge, 4),
                "real_edge": None if s.real_edge is None else round(s.real_edge, 4), "real_bets": s.real_bets,
                "paper_edge": None if s.paper_edge is None else round(s.paper_edge, 4), "paper_bets": s.paper_bets,
                "now": now["staff"].get(s.key, {}), "at_peak": best["staff"].get(s.key, {}),
                "assumed": s.key in SYNTHETIC,
            })
        worst = sorted(res["worst"])
        return {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "book": book.name, "start": round(start, 2),
            "others": round(book.others, 2), "days": days, "paths": n, "fan": fan,
            "chance_up": round(sum(x > start for x in end) / len(end), 3),
            "chance_double": round(sum(x > 2 * start for x in end) / len(end), 3),
            "chance_half": round(sum(x < 0.5 * start for x in end) / len(end), 3),
            "worst_day_typical": round(_q(worst, 0.5), 4),
            "engine": [{k: v for k, v in r.items() if k != "staff"} for r in engine],
            "engine_capped": [{k: v for k, v in r.items() if k != "staff"} for r in capped], "peak_bet": peak_bet,
            "peak": {"size": best["size"], "profit_day": best["profit_day"]},
            "stall": stall, "now": {"size": now["size"], "profit_day": now["profit_day"], "pct_day": now["pct_day"]},
            "what_if": what_if, "staff": staff, "settings": book.settings, "tested_bid": round(book.tested, 2),
            # the pool size where a VP's bid (with the family's beside it) passes what real fills have vouched for
            "tested_pool": round(book.tested / (float(book.settings["bet_pct"]) * level_mult(len(LEVELS) - 1)
                                                * (1 + (book.others / book.equity if book.equity else 0))), 2),
            "check": check,
        }


# -- reading a book from the database -----------------------------------------------------------------------------

def real_record(ledgers: list, days: int = 30) -> dict[str, dict]:
    """Every family book's settled real bets per employee over `days`: bets, dollars, profit, first bet."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    out: dict[str, dict] = {}
    for led in ledgers:
        rows = led._rows(
            "SELECT s.strategy, COUNT(*) AS n, SUM(f.c) AS spent, SUM(s.pnl) AS pnl, MIN(s.ts) AS first FROM settlements s"
            " JOIN (SELECT strategy, ticker, SUM(count * price + fee) AS c FROM fills WHERE ts >= ? GROUP BY strategy, ticker) f"
            " ON f.strategy = s.strategy AND f.ticker = s.ticker WHERE s.ts >= ? GROUP BY s.strategy", (since, since))
        for r in rows:
            o = out.setdefault(r["strategy"], {"bets": 0, "spent": 0.0, "pnl": 0.0, "first": r["first"], "home_bets": 0, "home_days": 0.0})
            o["bets"] += int(r["n"]); o["spent"] += float(r["spent"] or 0); o["pnl"] += float(r["pnl"] or 0)
            o["first"] = min(o["first"], r["first"])
            if led is ledgers[0]:  # the betting rate comes from the first (the owner's) book only
                o["home_bets"] = int(r["n"])
                first = datetime.fromisoformat(str(r["first"]).replace("Z", "+00:00"))
                o["home_days"] = max(3.0, (datetime.now(timezone.utc) - first).total_seconds() / 86400)
    return out


def build_staff(lib: Library, members: list[str], levels: dict[str, int], record: dict[str, dict],
                paper: Optional[dict[str, dict]] = None) -> list[Staff]:
    """Edges: the tape's (or the assumed prior), Training's recent paper bets at half weight, and real bets, blended
    by how many of each there are."""
    out = []
    paper = paper or {}
    for k in members:
        r = record.get(k) or {}
        n, spent = int(r.get("bets", 0)), float(r.get("spent", 0))
        real = (float(r["pnl"]) / spent) if spent > 0 else None
        coin = COIN_OF.get(k)
        if coin and coin in lib.tape_edge:
            prior = lib.tape_edge[coin]
            tape_rate = lib.tape_rate[coin]
            live_rate = r.get("home_bets", 0) / r["home_days"] if r.get("home_days") else None
            ratio = live_rate / tape_rate if live_rate else 1.0
            w = r.get("home_bets", 0) / (r.get("home_bets", 0) + 100)  # a few days of real betting sets the rate
            keep = min(1.0, w * ratio + (1 - w) * 1.0)
        elif k in SYNTHETIC:
            prior, keep = SYNTHETIC[k]["prior_edge"], 1.0
        else:
            continue  # no model for them (yet)
        pp = paper.get(k) or {}
        pn = PAPER_WEIGHT * int(pp.get("bets", 0)) if float(pp.get("spent", 0)) > 0 else 0.0
        pe = float(pp["pnl"]) / float(pp["spent"]) if pn else 0.0
        weight = PRIOR_BETS + pn + (n if real is not None else 0)
        edge = (PRIOR_BETS * prior + pn * pe + (n * real if real is not None else 0)) / weight
        sd = math.hypot(BET_SD / math.sqrt(weight), REGIME_SD)
        rate = 0.0
        if k in SYNTHETIC:
            live_rate = r.get("home_bets", 0) / r["home_days"] if r.get("home_days") else None
            w = r.get("home_bets", 0) / (r.get("home_bets", 0) + 100)
            rate = w * live_rate + (1 - w) * SYNTHETIC[k]["prior_rate"] if live_rate else SYNTHETIC[k]["prior_rate"]
        out.append(Staff(key=k, level=int(levels.get(k, 1)), edge=edge, edge_sd=sd,
                         tape_edge=lib.tape_edge.get(coin) if coin else None, keep=keep, rate=rate,
                         real_bets=n, real_edge=real, paper_bets=int(pp.get("bets", 0)), paper_edge=pe if pn else None))
    return out


def book_from(ledger, family: list, lib: Library, name: str, paper: Optional[dict] = None) -> Optional[Book]:
    """One office's starting point: its pool now (status `live`), rules, levels, and the family's record."""
    from desk import hr

    live = ledger.get_status("live") or {}
    pool = live.get("pool") or {}
    if not pool.get("equity"):
        return None
    policy = hr.load_policy(ledger)
    settings = {**policy["pool"], **(pool.get("settings") or {})}
    members = list(pool.get("members") or [])
    levels = {r["key"]: int(r["level"]) for r in ledger.employee_rows()}
    record = real_record([ledger] + [f for f in family if f is not ledger])
    others = 0.0
    for f in family:
        if f is ledger:
            continue
        p = (f.get_status("live") or {}).get("pool") or {}
        others += float(p.get("equity") or 0)
    return Book(name=name, equity=float(pool["equity"]), settings=settings,
                staff=build_staff(lib, members, levels, record, paper), others=others, policy=policy,
                tested=tested_bid([ledger] + [f for f in family if f is not ledger]),
                history=season_days(ledger, int(policy.get("season", 1)), settings.get("timezone") or "America/Vancouver"))


def tested_bid(ledgers: list, days: int = 30) -> float:
    """The family's biggest real coin bids (one window, all offices together) that filled at least 90%: the 95th
    percentile, so one lucky window doesn't count. Never below TESTED."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    per: dict[tuple, list] = {}
    for led in ledgers:
        for r in led._rows(
                "SELECT ticker, MAX(price * count) AS budget, SUM(price * filled) AS got FROM orders WHERE ts >= ?"
                " AND kind = 'maker' AND strategy LIKE 'maker_%' GROUP BY strategy, ticker HAVING SUM(filled) > 0", (since,)):
            p = per.setdefault((r["ticker"],), [0.0, 0.0])
            p[0] += float(r["budget"] or 0); p[1] += float(r["got"] or 0)
    full = sorted(b for b, g in per.values() if b > 0 and g >= 0.9 * b)
    return max(TESTED, _q(full, 0.95)) if len(full) >= 20 else TESTED


def season_days(ledger, season: int, tz: str) -> list:
    """The pool's value at the end of each day this season (members' last snapshot each day, added up)."""
    from zoneinfo import ZoneInfo

    rows = ledger._rows("SELECT strategy, ts, equity FROM equity WHERE season = ? ORDER BY ts", (season,))
    zone = ZoneInfo(tz)
    last: dict[str, dict[str, float]] = {}
    for r in rows:
        d = datetime.fromisoformat(str(r["ts"]).replace("Z", "+00:00")).astimezone(zone).date().isoformat()
        last.setdefault(d, {})[r["strategy"]] = float(r["equity"])
    out, running = [], {}
    for d in sorted(last):
        running.update(last[d])
        out.append((d, sum(running.values())))
    return out


def family_schemas(url: str) -> list[str]:
    """The owner's real book first, then every friend's office that is trading."""
    import psycopg

    from desk.offices import schema_of

    with psycopg.connect(url) as c:
        slugs = [r[0] for r in c.execute("SELECT slug FROM public.offices WHERE status = 'active' ORDER BY slug")]
    return ["real"] + [schema_of(x) for x in slugs]


def run_family(url: str, schemas: list[str], n: int = 200) -> dict[str, dict]:
    """Forecast every family book and save each as its status row `_forecast`. The owner's also carries the newcomer
    table (what a new friend's office would do from each starting amount: the tour quotes it) and a log of past
    predictions, to grade the model on later."""
    from desk.paper.ledger import Ledger

    ledgers = [Ledger(url, s, shared=True) for s in schemas]
    paper = real_record([Ledger(url, "public", shared=True)])  # Training's paper bets: recent, from the real tape
    fc = Forecaster.load()
    done = {}
    for led, s in zip(ledgers, schemas):
        book = book_from(led, ledgers, fc.lib, s, paper)
        if book is None:
            continue
        out = fc.run(book, n=n)
        if s == schemas[0]:
            family = book.equity + book.others
            out["newcomer"] = fc.newcomer(book, family)
        out["log"] = prediction_log(led.get_status("_forecast"), out)
        led.set_status("_forecast", out)
        done[s] = out
    return done


def prediction_log(before: Optional[dict], now: dict, keep: int = 120) -> list:
    """One line a day: the start and the 7- and 30-day predictions, so later days can say how they turned out."""
    log = list((before or {}).get("log") or [])
    day = now["at"][:10]
    pick = {f["day"]: f for f in now["fan"]}
    row = {"day": day, "start": now["start"]}
    for d in (7, 30):
        f = pick.get(d) or min(now["fan"], key=lambda x: abs(x["day"] - d))
        row[f"d{d}"] = [round(f["p10"], 2), round(f["p50"], 2), round(f["p90"], 2)]
    log = [r for r in log if r.get("day") != day] + [row]
    return log[-keep:]


# -- small helpers ------------------------------------------------------------------------------------------------

def _q(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    i = q * (len(sorted_vals) - 1)
    lo = int(i); hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (i - lo)


def _logspace(a: float, b: float, n: int) -> list[float]:
    return [a * (b / a) ** (i / (n - 1)) for i in range(n)]


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def _outcome(rng: random.Random, edge: float, price: float = 0.96) -> float:
    """Profit per $1 on one favourite at `price` that wins often enough to earn `edge` on average."""
    win = min(1.0, max(0.0, price * (1 + edge)))
    return (1 / price - 1) if rng.random() < win else -1.0
