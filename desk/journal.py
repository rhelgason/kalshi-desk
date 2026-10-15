"""
The run journal: one short summary per desk run, kept in the database.

Vercel's free plan keeps function logs for well under an hour, so anything
worth knowing about a run is written here instead (`runs` table, 14 days):

  phases      seconds spent fetching, deciding, settling, reporting
  market      windows open, markets seen, bitcoin's price (and how fresh it is)
  pool        equity, today's change, money in play, stop/brake state
  employees   per employee: ideas, bets, bids posted, maker fills, payouts,
              and why ideas didn't become bets ("window cap full", ...)
  warnings    every WARNING or worse logged by the desk during the run

Read it with `python -m desk log`.
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from typing import Iterator, Optional

MAX_WARNINGS = 25


def short_reason(reason: str) -> str:
    """'insufficient cash ($3.10 < $9.80)' -> 'insufficient cash', so reasons group together."""
    return re.sub(r"\s*\(.*\)\s*$", "", reason or "").strip() or "not filled"


class _Capture(logging.Handler):
    def __init__(self, journal: "RunJournal"):
        super().__init__(logging.WARNING)
        self.journal = journal

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = record.getMessage()
        except Exception:  # a bad format string must never break a run
            text = str(record.msg)
        if record.exc_info and record.exc_info[1] is not None:
            text += f" [{type(record.exc_info[1]).__name__}: {record.exc_info[1]}]"
        self.journal.warn(f"{record.levelname} {record.name}: {text}")


class RunJournal:
    def __init__(self) -> None:
        self._t0 = time.monotonic()
        self.phases: dict[str, float] = {}
        self.employees: dict[str, Counter] = defaultdict(Counter)
        self.warnings: list[str] = []
        self.dropped_warnings = 0
        self.info: dict = {}
        self._handler: Optional[_Capture] = None

    # Collecting ------------------------------------------------------------

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        t = time.monotonic()
        try:
            yield
        finally:
            self.phases[name] = round(self.phases.get(name, 0.0) + time.monotonic() - t, 3)

    def count(self, who: str, what: str, n: float = 1) -> None:
        self.employees[who][what] += n

    def skipped(self, who: str, reason: str) -> None:
        self.count(who, f"skipped: {short_reason(reason)}")

    def warn(self, text: str) -> None:
        if text in self.warnings:
            return
        if len(self.warnings) >= MAX_WARNINGS:
            self.dropped_warnings += 1
            return
        self.warnings.append(text[:500])

    def capture(self, logger_name: str = "desk") -> None:
        """Start collecting warnings logged under `logger_name` (the whole desk package)."""
        if self._handler is None:
            self._handler = _Capture(self)
            logging.getLogger(logger_name).addHandler(self._handler)

    def release(self, logger_name: str = "desk") -> None:
        if self._handler is not None:
            logging.getLogger(logger_name).removeHandler(self._handler)
            self._handler = None

    # Reporting -------------------------------------------------------------

    def summary(self) -> dict:
        return {
            "seconds": round(time.monotonic() - self._t0, 2),
            "phases": self.phases,
            **self.info,
            "employees": {k: {w: round(n, 2) for w, n in sorted(c.items())} for k, c in sorted(self.employees.items())},
            "warnings": self.warnings + ([f"...and {self.dropped_warnings} more"] if self.dropped_warnings else []),
        }


def format_runs(rows: list[dict], verbose: bool = False) -> str:
    """Plain-text view of recent runs (newest last) for `python -m desk log`."""
    lines = []
    totals: dict[str, Counter] = defaultdict(Counter)
    warned = Counter()
    for r in rows:
        s = r["summary"]
        pool = s.get("pool") or {}
        bets = sum(c.get("bets", 0) + c.get("bids posted", 0) for c in s.get("employees", {}).values())
        head = (f"{r['ts'][:19]}  {s.get('seconds', 0):5.1f}s  pool ${pool.get('equity', 0):,.2f}"
                f" ({pool.get('today', 0):+.1%} today)  in play ${pool.get('in_play', 0):,.2f}  bets/bids {bets}")
        flags = [f for f, on in (("STOPPED", pool.get("stopped")), ("BRAKED", pool.get("braked"))) if on]
        if s.get("warnings"):
            flags.append(f"{len(s['warnings'])} warning(s)")
        lines.append(head + ("  " + " ".join(flags) if flags else ""))
        for k, c in (s.get("employees") or {}).items():
            totals[k].update(c)
            if verbose:
                lines.append(f"    {k:<16} " + ", ".join(f"{w} {n:g}" for w, n in c.items()))
        for w in s.get("warnings") or []:
            warned[w] += 1
            if verbose:
                lines.append(f"    ! {w}")
    if not rows:
        return "No runs recorded yet."
    lines += ["", f"Totals over {len(rows)} runs ({rows[0]['ts'][:16]} to {rows[-1]['ts'][:16]}):"]
    for k, c in sorted(totals.items()):
        lines.append(f"  {k:<16} " + ", ".join(f"{w} {n:g}" for w, n in sorted(c.items(), key=lambda x: -x[1])))
    if warned:
        lines += ["", "Warnings:"] + [f"  {n:>4}x {w}" for w, n in warned.most_common(15)]
    return "\n".join(lines)
