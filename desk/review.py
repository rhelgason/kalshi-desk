"""
Performance review: everything needed to judge each employee over a period,
as a Markdown report.

    python -m desk review --days 30 [--out data/reviews/2026-11-12.md]

For every employee who bet in the period: results, skill-or-luck, where the
money came from (price paid, minutes left, side, time of day), how real the
fills were, the bets they tried but didn't get, and every settings change.
Plus how the market itself behaved, so changes can be judged against it.

Sources (all written by the bot as it runs):
  fills          every paper bet, with `context` JSON (what the employee saw)
  settlements    payouts per employee and market
  decisions      every attempted bet, filled or not, and why not
  market_tape    each run's quote for every watched market, plus bitcoin's price
  market_history settled markets with 1-minute candles (from the background job)
  events         HR actions, settings changes, tuning, roster snapshots
  tuning_runs    autotune results
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from desk.paper.ledger import Ledger
from desk.strategies import EVERYONE


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _name(key: str) -> str:
    cls = EVERYONE.get(key)
    return f"{cls.persona.emoji} {cls.persona.name} ({key})" if cls else key


def _money(x: float) -> str:
    return f"{'+' if x >= 0 else '-'}${abs(x):,.2f}"


def _bucket(x: Optional[float], edges: list[float], fmt) -> str:
    if x is None:
        return "unknown"
    for lo, hi in zip(edges, edges[1:]):
        if lo <= x < hi:
            return fmt(lo, hi)
    return fmt(edges[-1], None)


def _table(head: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _skill(edges: list[float]) -> str:
    """t-statistic of per-dollar results: above ~2 is unlikely to be luck."""
    n = len(edges)
    if n < 5:
        return "too few bets"
    mean = sum(edges) / n
    sd = math.sqrt(sum((e - mean) ** 2 for e in edges) / (n - 1)) or 1e-9
    t = mean / (sd / math.sqrt(n))
    verdict = "probably skill" if t > 2 else "probably losing" if t < -2 else "could be luck"
    return f"t = {t:+.2f} ({verdict})"


def build_review(ledger: Ledger, days: float = 30, now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    s = since.isoformat()
    fills = ledger._rows("SELECT * FROM fills WHERE ts >= ? ORDER BY ts", (s,))
    setts = ledger._rows("SELECT * FROM settlements WHERE ts >= ? ORDER BY ts", (s,))
    # Settlements can land after the period's fills; look a day past for payouts of in-period bets
    outcome: dict[str, float] = {}
    for r in ledger._rows("SELECT ticker, yes_value FROM settlements WHERE ts >= ?", (s,)):
        outcome[r["ticker"]] = r["yes_value"]
    tickers = sorted({f["ticker"] for f in fills})
    close_ts: dict[str, int] = {}
    for i in range(0, len(tickers), 500):
        chunk = tickers[i:i + 500]
        marks = ",".join("?" * len(chunk))
        for r in ledger._rows(f"SELECT ticker, close_ts, data FROM market_history WHERE ticker IN ({marks})", tuple(chunk)):
            close_ts[r["ticker"]] = int(r["close_ts"])
            if r["ticker"] not in outcome:
                m = json.loads(r["data"])["m"]
                if m.get("result") in ("yes", "no"):
                    outcome[r["ticker"]] = 1.0 if m["result"] == "yes" else 0.0
    decisions = _safe_rows(ledger, "SELECT strategy, outcome, filled, count FROM decisions WHERE ts >= ?", (s,))
    events = ledger._rows("SELECT ts, strategy, kind, detail FROM events WHERE ts >= ? ORDER BY ts", (s,))
    tuning = ledger._rows("SELECT created_at, strategy, summary FROM tuning_runs WHERE created_at >= ? ORDER BY created_at", (s,))

    lines = [f"# Desk review: {since:%b %d} to {now:%b %d, %Y} ({days:g} days)", ""]
    lines += _market_section(ledger, since, now)

    # Per-fill results
    per: dict[str, list[dict]] = defaultdict(list)
    for f in fills:
        ctx = json.loads(f["context"]) if f.get("context") else {}
        leg = (ctx.get("legs") or [{}])[0]
        y = outcome.get(f["ticker"])
        payout = None if y is None else f["count"] * (y if f["side"] == "yes" else 1 - y)
        secs = leg.get("secs_left")
        if secs is None and f["ticker"] in close_ts:
            secs = close_ts[f["ticker"]] - _dt(f["ts"]).timestamp()
        per[f["strategy"]].append({
            **f, "ctx": ctx, "leg": leg, "secs_left": secs, "y": y,
            "pnl": None if payout is None else payout - f["count"] * f["price"] - f["fee"],
            "cost": f["count"] * f["price"] + f["fee"],
        })

    lines += ["## Scoreboard", ""]
    rows = []
    for k, fs in sorted(per.items(), key=lambda kv: -sum(x["pnl"] or 0 for x in kv[1])):
        done = [x for x in fs if x["pnl"] is not None]
        pnl = sum(x["pnl"] for x in done)
        wins = sum(1 for x in done if x["pnl"] > 0)
        cost = sum(x["cost"] for x in done) or 1
        rows.append([_name(k), len(fs), len(done), f"{wins / len(done):.0%}" if done else "-", _money(pnl),
                     f"{pnl / cost:+.1%}", f"${sum(x['fee'] for x in fs):,.2f}"])
    lines += [_table(["employee", "bets", "settled", "won", "profit", "per $ bet", "fees"], rows) if rows
              else "No bets in this period.", ""]
    settled_pnl = defaultdict(float)
    for r in setts:
        settled_pnl[r["strategy"]] += r["pnl"]
    if settled_pnl:
        lines += ["Ledger settlement P&L in the period (cross-check): " +
                  ", ".join(f"{k} {_money(v)}" for k, v in sorted(settled_pnl.items())), ""]

    dec = defaultdict(Counter)
    for d in decisions:
        dec[d["strategy"]][d["outcome"]] += 1

    for k, fs in per.items():
        lines += _employee_section(k, fs, dec.get(k), events, tuning)

    quiet = [k for k in EVERYONE if k not in per and any(e["strategy"] == k for e in events)]
    if quiet:
        lines += ["## Employees with no bets", "", ", ".join(_name(k) for k in quiet), ""]

    lines += ["## Desk events", ""]
    kinds = Counter(e["kind"] for e in events)
    lines += [", ".join(f"{k}: {v}" for k, v in kinds.most_common()) or "none", ""]
    for e in events:
        if e["kind"] in ("hr", "admin", "season", "error", "tune"):
            lines.append(f"- {e['ts'][:16]} {e['kind']} {e['strategy'] or ''} {e['detail'][:200]}")
    return "\n".join(lines) + "\n"


def _safe_rows(ledger: Ledger, sql: str, params: tuple) -> list[dict]:
    try:
        return ledger._rows(sql, params)
    except Exception:  # older databases without the table
        return []


def _market_section(ledger: Ledger, since: datetime, now: datetime) -> list[str]:
    rows = ledger._rows("SELECT data FROM market_history WHERE series = 'KXBTC15M' AND close_ts > ? AND close_ts <= ?",
                        (int(since.timestamp()), int(now.timestamp())))
    results = Counter()
    for r in rows:
        results[json.loads(r["data"])["m"].get("result")] += 1
    n = results["yes"] + results["no"]
    out = ["## The market", ""]
    if n:
        out.append(f"- {n} fifteen-minute bitcoin windows settled; bitcoin finished up in {results['yes'] / n:.0%}.")
    tape = _safe_rows(ledger, "SELECT spot, ts FROM market_tape WHERE ts >= ? AND spot IS NOT NULL ORDER BY ts",
                      (since.isoformat(),))
    if tape:
        first, last = tape[0]["spot"], tape[-1]["spot"]
        out.append(f"- Bitcoin went from ${first:,.0f} to ${last:,.0f} ({(last / first - 1):+.1%}) "
                   f"between {tape[0]['ts'][:10]} and {tape[-1]['ts'][:10]}.")
    out.append("")
    return out


def _employee_section(key: str, fs: list[dict], dec: Optional[Counter], events: list[dict],
                      tuning: list[dict]) -> list[str]:
    done = [x for x in fs if x["pnl"] is not None]
    out = [f"## {_name(key)}", ""]
    if done:
        per_dollar = [x["pnl"] / x["cost"] for x in done if x["cost"] > 0]
        out.append(f"- {len(fs)} bets, {len(done)} settled, profit {_money(sum(x['pnl'] for x in done))}; "
                   f"skill or luck: {_skill(per_dollar)}")
        slip = [x["price"] - x["seen_price"] for x in fs if x.get("seen_price") is not None]
        if slip:
            out.append(f"- Fill reality: paid {sum(slip) / len(slip) * 100:+.2f}c vs. the price seen on average; "
                       f"median depth at limit {sorted(x['book_depth'] or 0 for x in fs)[len(fs) // 2]:.0f} contracts")
    if dec:
        total = sum(dec.values())
        out.append(f"- Tried {total} bets, filled {dec.get('filled', 0)} ({dec.get('filled', 0) / total:.0%}); misses: " +
                   (", ".join(f"{k} x{v}" for k, v in dec.most_common() if k != "filled") or "none"))
    out.append("")

    def breakdown(title: str, keyf) -> list[str]:
        g = defaultdict(list)
        for x in done:
            g[keyf(x)].append(x)
        rows = [[k, len(v), f"{sum(1 for x in v if x['pnl'] > 0) / len(v):.0%}", _money(sum(x['pnl'] for x in v)),
                 f"{sum(x['pnl'] for x in v) / (sum(x['cost'] for x in v) or 1):+.1%}"] for k, v in sorted(g.items())]
        return [f"**By {title}**", "", _table([title, "bets", "won", "profit", "per $"], rows), ""] if rows else []

    out += breakdown("price paid", lambda x: _bucket(x["price"], [0, .1, .2, .4, .6, .75, .85, .9, .95, 1.0],
                                                   lambda lo, hi: f"{lo:.2f}-{hi:.2f}" if hi else f"{lo:.2f}+"))
    out += breakdown("minutes left", lambda x: _bucket(None if x["secs_left"] is None else x["secs_left"] / 60,
                                                     [0, 2, 5, 8, 11, 15, 60],
                                                     lambda lo, hi: f"{lo:g}-{hi:g}m" if hi else f"{lo:g}m+"))
    out += breakdown("side", lambda x: x["side"].upper())
    out += breakdown("hour (UTC)", lambda x: f"{_dt(x['ts']).hour // 6 * 6:02d}-{_dt(x['ts']).hour // 6 * 6 + 6:02d}")
    out += breakdown("bitcoin's 15-min move", lambda x: _bucket(
        ((x["leg"].get("momentum") or {}).get("15") or (x["leg"].get("momentum") or {}).get(15)),
        [-1, -0.003, -0.001, 0.001, 0.003], lambda lo, hi: f"{lo * 100:+.1f}%..{hi * 100:+.1f}%" if hi else f"{lo * 100:+.1f}%+"))

    daily = defaultdict(float)
    for x in done:
        daily[x["ts"][:10]] += x["pnl"]
    if daily:
        run, pts = 0.0, []
        for d in sorted(daily):
            run += daily[d]
            pts.append(f"{d[5:]} {_money(run)}")
        out += ["**Running profit by day:** " + " · ".join(pts), ""]

    params = [x["ctx"].get("params") for x in fs if x["ctx"].get("params")]
    if params:
        seen = []
        for p in params:
            if p not in seen:
                seen.append(p)
        out += ["**Settings used:** " + " → ".join(json.dumps(p, sort_keys=True) for p in seen), ""]
    hr_events = [e for e in events if e["strategy"] == key and e["kind"] in ("hr", "admin", "tune", "award")]
    if hr_events:
        out += ["**HR and settings changes:**", ""] + [f"- {e['ts'][:16]} {e['kind']}: {e['detail'][:200]}" for e in hr_events] + [""]
    tunes = [t for t in tuning if t["strategy"] == key]
    if tunes:
        out += [f"**Autotune runs:** {len(tunes)}; latest: {json.loads(tunes[-1]['summary']).get('why', '')}", ""]
    return out
