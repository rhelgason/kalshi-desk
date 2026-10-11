"""
Compare strategies side by side.

Metrics, in plain English:
  P&L          profit or loss vs. starting cash (open bets valued at what
               you could sell them for right now)
  ROI          P&L as a % of starting cash
  Win rate     settled bets that made money / all settled bets
  Fees         total paid to Kalshi (fees often decide winner vs loser)
  Max DD       "max drawdown": worst drop from a high point; measures pain
  Brier        for strategies that state a probability: average squared
               error between their forecast and what happened. 0 is perfect,
               0.25 is what you'd get always guessing 50%. Lower is better.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from desk.paper.account import PaperAccount
from desk.paper.ledger import Ledger


@dataclass
class ScoreRow:
    strategy: str
    starting_cash: float  # capital: starting cash plus any transfers (bonuses)
    equity: float
    realized_pnl: float
    open_positions: int
    fills: int
    wins: int
    losses: int
    fees: float
    max_drawdown: float
    brier: Optional[float]

    @property
    def pnl(self) -> float:
        return self.equity - self.starting_cash

    @property
    def roi(self) -> float:
        return self.pnl / self.starting_cash if self.starting_cash else 0.0

    @property
    def win_rate(self) -> Optional[float]:
        n = self.wins + self.losses
        return self.wins / n if n else None


def max_drawdown(curve: list[float]) -> float:
    peak, worst = float("-inf"), 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
    return worst


def brier_score(ledger: Ledger, strategy: str) -> Optional[float]:
    """Brier score over settled fills that carried a model probability."""
    outcomes = {r["ticker"]: r["yes_value"] for r in ledger.settlements(strategy)}
    errs = []
    for f in ledger.fills(strategy):
        if f["model_prob"] is None or f["ticker"] not in outcomes:
            continue
        yes_value = outcomes[f["ticker"]]
        won = yes_value if f["side"] == "yes" else 1 - yes_value
        errs.append((f["model_prob"] - won) ** 2)
    return sum(errs) / len(errs) if errs else None


def scoreboard_rows(accounts: dict[str, PaperAccount], ledger: Ledger,
                    marks: Optional[dict[str, float]] = None,
                    drawdowns: Optional[dict[str, float]] = None,
                    briers: Optional[dict[str, Optional[float]]] = None) -> list[ScoreRow]:
    """
    drawdowns/briers, when given, are used instead of reading the equity and
    fills tables (the cloud runner tracks them incrementally).
    """
    rows = []
    for name, acct in accounts.items():
        equity = acct.equity(marks or {})
        if drawdowns is not None:
            dd = drawdowns.get(name, 0.0)
        else:
            dd = max_drawdown([e for _, e in ledger.equity_curve(name)] + [equity])
        rows.append(ScoreRow(
            strategy=name,
            starting_cash=acct.capital,
            equity=equity,
            realized_pnl=acct.realized_pnl,
            open_positions=len(acct.open_tickers),
            fills=acct.trades,
            wins=acct.settled_wins,
            losses=acct.settled_losses,
            fees=acct.fees_paid,
            max_drawdown=dd,
            brier=briers.get(name) if briers is not None else brier_score(ledger, name),
        ))
    rows.sort(key=lambda r: r.pnl, reverse=True)
    return rows


def format_scoreboard(rows: list[ScoreRow], personas: Optional[dict[str, str]] = None) -> str:
    personas = personas or {}
    header = f"{'employee':<36}{'P&L':>10}{'ROI':>8}{'realized':>10}{'open':>6}{'fills':>7}" \
             f"{'W/L':>9}{'win%':>7}{'fees':>8}{'maxDD':>7}{'brier':>7}"
    lines = [header, "-" * len(header)]
    for r in rows:
        label = personas.get(r.strategy, r.strategy)
        wr = f"{r.win_rate:.0%}" if r.win_rate is not None else "-"
        br = f"{r.brier:.3f}" if r.brier is not None else "-"
        lines.append(
            f"{label:<36}{r.pnl:>+10.2f}{r.roi:>+8.1%}{r.realized_pnl:>+10.2f}{r.open_positions:>6}"
            f"{r.fills:>7}{f'{r.wins}/{r.losses}':>9}{wr:>7}{r.fees:>8.2f}{r.max_drawdown:>7.1%}{br:>7}"
        )
    return "\n".join(lines)
