import pytest

from desk.kalshi.fees import FeeSchedule
from desk.kalshi.models import Level, Orderbook, Side
from desk.paper.account import PaperAccount
from desk.paper.broker import PaperBroker
from desk.paper.ledger import Ledger
from desk.paper.scoreboard import max_drawdown, scoreboard_rows
from desk.strategies.base import Leg, TradeIntent


class TestAccount:
    def test_buy_and_win(self):
        a = PaperAccount("s", 100)
        a.apply_fill("T", Side.YES, 10, 0.40, 0.17)
        assert a.cash == pytest.approx(100 - 4.17)
        pnl = a.settle("T", 1.0)
        assert pnl == pytest.approx(10 - 4.17)
        assert a.cash == pytest.approx(105.83)
        assert a.settled_wins == 1 and not a.positions

    def test_buy_and_lose(self):
        a = PaperAccount("s", 100)
        a.apply_fill("T", Side.NO, 10, 0.40, 0.17)
        assert a.settle("T", 1.0) == pytest.approx(-4.17)
        assert a.settled_losses == 1

    def test_yes_and_no_net_to_cash(self):
        a = PaperAccount("s", 100)
        a.apply_fill("T", Side.YES, 10, 0.40, 0)
        a.apply_fill("T", Side.NO, 4, 0.55, 0)
        # 4 pairs turn into $4; 6 YES remain
        assert a.position("T") == (6, 0)
        assert a.realized_pnl == pytest.approx(4 - 4 * 0.40 - 4 * 0.55)
        assert a.cash == pytest.approx(100 - 4.0 - 2.2 + 4)

    def test_equity_marks(self):
        a = PaperAccount("s", 100)
        a.apply_fill("T", Side.YES, 10, 0.40, 0)
        assert a.equity({}) == pytest.approx(100)  # unmarked = at cost
        assert a.equity({"T": 0.50}) == pytest.approx(101)

    def test_unmarked_equity_counts_fees_as_spent(self):
        a = PaperAccount("s", 100)
        a.apply_fill("T", Side.YES, 10, 0.40, 0.17)
        assert a.equity({}) == pytest.approx(100 - 0.17)
        # Netting half the position releases half the remaining fee
        a.apply_fill("T", Side.NO, 5, 0.60, 0)
        assert a.positions["T"].yes_fees == pytest.approx(0.085)


def _book(ticker, yes_ask, size, no_ask=None):
    """Book offering YES at `yes_ask` and NO at `no_ask` (default: 2c spread)."""
    no_ask = no_ask if no_ask is not None else round(1 - yes_ask + 0.02, 2)
    return Orderbook(ticker, yes_bids=[Level(round(1 - no_ask, 2), size)],
                     no_bids=[Level(round(1 - yes_ask, 2), size)])


class TestBroker:
    def setup_method(self):
        self.ledger = Ledger(":memory:")
        self.accounts = self.ledger.load_accounts(1000, ["s"])
        self.broker = PaperBroker(self.ledger, self.accounts, liquidity_share=1.0)

    def test_single_leg_fill_charges_fee_and_logs(self):
        intent = TradeIntent("s", [Leg("T", Side.YES, 0.50, 10)], "test", model_prob=0.6)
        r = self.broker.execute(intent, {"T": _book("T", 0.50, 100)}, {"T": FeeSchedule()})
        assert r.filled and r.fills[0].count == 10
        assert r.fills[0].fee == pytest.approx(0.18)
        assert self.accounts["s"].cash == pytest.approx(1000 - 5 - 0.18)
        assert len(self.ledger.fills("s")) == 1

    def test_liquidity_share_limits_fill(self):
        broker = PaperBroker(self.ledger, self.accounts, liquidity_share=0.5)
        intent = TradeIntent("s", [Leg("T", Side.YES, 0.50, 100)], "test")
        r = broker.execute(intent, {"T": _book("T", 0.50, 40)}, {})
        assert r.fills[0].count == 20

    def test_limit_price_respected(self):
        intent = TradeIntent("s", [Leg("T", Side.YES, 0.45, 10)], "test")
        r = self.broker.execute(intent, {"T": _book("T", 0.50, 100)}, {})
        assert not r.filled

    def test_all_or_none_scales_to_thinnest_leg(self):
        intent = TradeIntent("s", [Leg("A", Side.YES, 0.50, 20), Leg("B", Side.NO, 0.40, 20)], "arb",
                             all_or_none=True, guaranteed_payout=1.0, expected_edge=0.05)
        books = {"A": _book("A", 0.50, 100), "B": _book("B", 0.62, 7, no_ask=0.40)}
        r = self.broker.execute(intent, books, {})
        assert r.filled
        assert [f.count for f in r.fills] == [7, 7]

    def test_all_or_none_rejects_when_edge_gone(self):
        intent = TradeIntent("s", [Leg("A", Side.YES, 0.55, 10), Leg("B", Side.NO, 0.45, 10)], "arb",
                             all_or_none=True, guaranteed_payout=1.0)
        books = {"A": _book("A", 0.55, 100), "B": _book("B", 0.57, 100, no_ask=0.45)}
        r = self.broker.execute(intent, books, {"A": FeeSchedule(), "B": FeeSchedule()})
        assert not r.filled and "edge" in r.reason

    def test_insufficient_cash(self):
        self.accounts["s"].cash = 1.0
        intent = TradeIntent("s", [Leg("T", Side.YES, 0.50, 10)], "test")
        assert not self.broker.execute(intent, {"T": _book("T", 0.50, 100)}, {}).filled

    def test_settle_across_accounts_and_reload_from_ledger(self, tmp_path):
        ledger = Ledger(tmp_path / "x.db")
        accounts = ledger.load_accounts(100, ["a", "b"])
        broker = PaperBroker(ledger, accounts, liquidity_share=1.0)
        broker.execute(TradeIntent("a", [Leg("T", Side.YES, 0.5, 10)], ""), {"T": _book("T", 0.5, 100)}, {})
        broker.execute(TradeIntent("b", [Leg("T", Side.NO, 0.52, 10)], ""), {"T": _book("T", 0.5, 100)}, {})
        pnl = broker.settle("T", 1.0)
        assert pnl["a"] > 0 > pnl["b"]
        ledger.close()

        reloaded = Ledger(tmp_path / "x.db").load_accounts(100, ["a", "b"])
        assert reloaded["a"].cash == pytest.approx(accounts["a"].cash)
        assert reloaded["b"].cash == pytest.approx(accounts["b"].cash)
        assert reloaded["a"].settled_wins == 1


def test_scoreboard_and_brier():
    ledger = Ledger(":memory:")
    accounts = ledger.load_accounts(100, ["q"])
    broker = PaperBroker(ledger, accounts, liquidity_share=1.0)
    broker.execute(TradeIntent("q", [Leg("T", Side.YES, 0.5, 10)], "", model_prob=0.8),
                   {"T": _book("T", 0.5, 100)}, {})
    broker.settle("T", 1.0)
    row = scoreboard_rows(accounts, ledger)[0]
    assert row.brier == pytest.approx(0.04)  # (0.8 - 1)^2
    assert row.win_rate == 1.0
    assert row.pnl == pytest.approx(10 - 5.0 - 0.18)  # payout - cost - taker fee


def test_max_drawdown():
    assert max_drawdown([100, 120, 90, 130]) == pytest.approx(0.25)
    assert max_drawdown([100, 101, 102]) == 0


def test_accuracy_report_skill_and_calibration():
    from desk.paper.accuracy import accuracy_report, calibration

    ledger = Ledger(":memory:")
    accounts = ledger.load_accounts(1000, ["good", "bad"])
    broker = PaperBroker(ledger, accounts, liquidity_share=1.0)
    # Both pay 0.50 for YES on 4 markets; 3 resolve YES. "good" said 75%, "bad" said 25%.
    for i, result in enumerate([1.0, 1.0, 1.0, 0.0]):
        t = f"M{i}"
        for name, prob in (("good", 0.75), ("bad", 0.25)):
            broker.execute(TradeIntent(name, [Leg(t, Side.YES, 0.5, 10)], "", model_prob=prob),
                           {t: _book(t, 0.5, 100)}, {})
        broker.settle(t, result)
    good, bad = accuracy_report(ledger, ["good", "bad"])
    assert good.n == 4 and good.hit_rate == 0.75
    assert good.skill > 0 > bad.skill
    assert good.realized_edge == pytest.approx(0.75 - 0.5 - 0.018)  # fee 0.18 on 10 contracts
    assert good.model_bins[0].hit_rate == 0.75

    bins = calibration([(0.05, 0), (0.07, 1), (0.95, 1)])
    assert [(b.n, b.hit_rate) for b in bins] == [(2, 0.5), (1, 1.0)]
