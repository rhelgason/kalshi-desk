"""
A paper-money account for one strategy.

Mirrors how Kalshi treats positions: you hold YES or NO contracts in each
market. If you hold both sides of the same market, Kalshi nets them: one YES
plus one NO always pays exactly $1, so each pair turns back into $1 cash.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from desk.kalshi.models import Side


@dataclass
class Position:
    ticker: str
    yes: float = 0.0
    no: float = 0.0
    yes_cost: float = 0.0  # dollars paid for the YES contracts still held (incl. fees)
    no_cost: float = 0.0
    yes_fees: float = 0.0  # the fee part of yes_cost (already spent, never coming back)
    no_fees: float = 0.0

    @property
    def is_flat(self) -> bool:
        return self.yes < 0.005 and self.no < 0.005

    def contracts(self, side: Side) -> float:
        return self.yes if side is Side.YES else self.no


@dataclass
class PaperAccount:
    strategy: str
    starting_cash: float
    cash: float = 0.0
    positions: dict[str, Position] = field(default_factory=dict)
    fees_paid: float = 0.0
    realized_pnl: float = 0.0
    trades: int = 0
    settled_wins: int = 0
    settled_losses: int = 0

    def __post_init__(self):
        if not self.cash:
            self.cash = self.starting_cash

    # AccountView interface ---------------------------------------------

    def position(self, ticker: str) -> tuple[float, float]:
        p = self.positions.get(ticker)
        return (p.yes, p.no) if p else (0.0, 0.0)

    @property
    def open_tickers(self) -> set[str]:
        return {t for t, p in self.positions.items() if not p.is_flat}

    # Mutations ---------------------------------------------------------

    def apply_fill(self, ticker: str, side: Side, count: float, price: float, fee: float) -> None:
        cost = count * price + fee
        self.cash -= cost
        self.fees_paid += fee
        self.trades += 1
        pos = self.positions.setdefault(ticker, Position(ticker))
        if side is Side.YES:
            pos.yes += count
            pos.yes_cost += cost
            pos.yes_fees += fee
        else:
            pos.no += count
            pos.no_cost += cost
            pos.no_fees += fee
        self._net(pos)

    def _net(self, pos: Position) -> None:
        pairs = min(pos.yes, pos.no)
        if pairs <= 0:
            return
        yes_frac, no_frac = pairs / pos.yes, pairs / pos.no
        yes_basis = pos.yes_cost * yes_frac
        no_basis = pos.no_cost * no_frac
        pos.yes_fees -= pos.yes_fees * yes_frac
        pos.no_fees -= pos.no_fees * no_frac
        self.cash += pairs
        self.realized_pnl += pairs - yes_basis - no_basis
        pos.yes -= pairs
        pos.no -= pairs
        pos.yes_cost -= yes_basis
        pos.no_cost -= no_basis
        if pos.is_flat:
            self.positions.pop(pos.ticker, None)

    def settle(self, ticker: str, yes_value: float) -> float:
        """
        Pay out a settled market. yes_value is 1.0 if YES won, 0.0 if NO won
        (or something in between for rare scalar/void settlements).
        Returns the P&L realized.
        """
        pos = self.positions.pop(ticker, None)
        if not pos:
            return 0.0
        payout = pos.yes * yes_value + pos.no * (1 - yes_value)
        pnl = payout - pos.yes_cost - pos.no_cost
        self.cash += payout
        self.realized_pnl += pnl
        if pnl > 0:
            self.settled_wins += 1
        elif pnl < 0:
            self.settled_losses += 1
        return pnl

    # Reporting ---------------------------------------------------------

    def cost_basis(self) -> float:
        return sum(p.yes_cost + p.no_cost for p in self.positions.values())

    def equity(self, marks: dict[str, float]) -> float:
        """
        Cash plus open positions valued at `marks` (ticker -> YES value).
        Positions without a mark are valued at the price paid, so fees already
        spent show up as a loss right away.
        """
        value = self.cash
        for t, p in self.positions.items():
            if t in marks:
                y = marks[t]
                value += p.yes * y + p.no * (1 - y)
            else:
                value += p.yes_cost + p.no_cost - p.yes_fees - p.no_fees
        return value
