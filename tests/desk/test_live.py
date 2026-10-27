"""Real money (desk/live) against a fake Kalshi: orders, fills, the guard, reconciliation, the kill switch."""

from datetime import datetime, timedelta, timezone

import pytest

from desk.config import DeskConfig
from desk.kalshi.client import KalshiAPIError
from desk.kalshi.models import Side
from desk.live import LiveSetupError, live_client, make_live_broker
from desk.live.broker import client_order_id
from desk.live.reconcile import our_books, reconcile
from desk.paper.account import PaperAccount
from desk.paper.ledger import Ledger
from desk.runner import Desk
from desk.strategies import LongshotFade
from desk.strategies.base import Leg, TradeIntent
from tests.desk.conftest import book_for, make_market

NOW = datetime(2026, 10, 22, 19, 0, tzinfo=timezone.utc)
T = "KXBTC15M-26OCT221515-15"


class FakeKalshi:
    """Just enough of Kalshi: IOC orders fill against `asks`, post-only orders rest until traded into."""

    env = "demo"
    signer = object()
    allow_trading = True

    def __init__(self, cash=1000.0):
        self.asks: dict[tuple[str, str], tuple[float, float]] = {}  # (ticker, side) -> (price, size)
        self.orders: dict[str, dict] = {}
        self.fills: list[dict] = []
        self.position: dict[str, float] = {}  # + YES, - NO
        self.cash = cash
        self.cancel_all_calls = 0
        self.sent: list[dict] = []

    def _fill(self, oid, ticker, side, n, price, fee):
        self.fills.append({"fill_id": f"f{len(self.fills) + 1}", "order_id": oid, "ticker": ticker,
                           "outcome_side": side, "count_fp": f"{n:.2f}",
                           f"{side}_price_dollars": f"{price:.4f}",
                           f"{'no' if side == 'yes' else 'yes'}_price_dollars": f"{1 - price:.4f}",
                           "fee_cost": f"{fee:.4f}"})
        self.position[ticker] = self.position.get(ticker, 0.0) + (n if side == "yes" else -n)
        self.cash -= n * price + fee
        o = self.orders[oid]
        o["fill_count_fp"] = f"{float(o['fill_count_fp']) + n:.2f}"

    async def create_order(self, ticker, side, count, limit_price, time_in_force="immediate_or_cancel",
                           post_only=False, client_order_id=None, expiration_ts=None, **kw):
        self.sent.append(dict(ticker=ticker, side=side.value, count=count, price=limit_price, tif=time_in_force,
                              post_only=post_only, coid=client_order_id, expires=expiration_ts))
        oid = f"o{len(self.orders) + 1}"
        self.orders[oid] = {"order_id": oid, "ticker": ticker, "side": side.value, "price": limit_price,
                            "count": count, "fill_count_fp": "0.00", "status": "resting", "maker_fees_dollars": "0"}
        if not post_only:
            price, size = self.asks.get((ticker, side.value), (None, 0.0))
            if price is not None and price <= limit_price + 1e-9:
                n = min(count, size)
                self._fill(oid, ticker, side.value, n, price, round(0.07 * n * price * (1 - price), 4))
            self.orders[oid]["status"] = "executed" if float(self.orders[oid]["fill_count_fp"]) else "canceled"
        filled = float(self.orders[oid]["fill_count_fp"])
        return {"order_id": oid, "fill_count": f"{filled:.2f}", "remaining_count": f"{count - filled:.2f}"}

    def trade_into(self, oid, n):
        """Someone sells into our resting bid (maker fill, no fee on this series)."""
        o = self.orders[oid]
        self._fill(oid, o["ticker"], o["side"], n, o["price"], 0.0)
        if float(o["fill_count_fp"]) >= o["count"] - 1e-9:
            o["status"] = "executed"

    async def get_order(self, oid, ticker=None):
        return dict(self.orders[oid])

    async def get_fills(self, order_id=None, **kw):
        return [f for f in self.fills if f["order_id"] == order_id]

    async def cancel_order(self, oid, ticker):
        if oid not in self.orders or self.orders[oid]["status"] != "resting":
            raise KalshiAPIError(404, "not found")
        self.orders[oid]["status"] = "canceled"
        return {"order_id": oid}

    async def cancel_all_orders(self):
        self.cancel_all_calls += 1
        for o in self.orders.values():
            if o["status"] == "resting":
                o["status"] = "canceled"
        return {}

    async def get_positions(self):
        return [{"ticker": t, "position_fp": f"{n:.2f}"} for t, n in self.position.items() if abs(n) > 0.005]

    async def get_balance(self):
        return self.cash

    async def get_account(self):
        return {"cash": self.cash, "positions": 0.0}


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv("KALSHI_LIVE_TRADING", "yes")
    ledger = Ledger(":memory:")
    accounts = {"e0": PaperAccount("e0", 500), "e1": PaperAccount("e1", 500), "monkey": PaperAccount("monkey", 1000)}
    client = FakeKalshi()
    broker = make_live_broker(DeskConfig(trading="live", live={"max_order_dollars": 30}), ledger, accounts, client)
    broker.pool_members = {"e0", "e1"}
    return broker, client, ledger, accounts


def bet(who="e0", side=Side.YES, price=0.50, count=10, **kw):
    return TradeIntent(who, [Leg(T, side, price, count)], "test bet", intent_id="abc123", **kw)


async def test_a_real_bet_is_booked_at_kalshis_price_and_fee(live):
    broker, client, ledger, accounts = live
    client.asks[(T, "yes")] = (0.48, 6)  # better than our limit, but only 6 there
    r = await broker.execute(bet(), {}, {})
    assert r.filled and r.fills[0].count == 6 and r.fills[0].avg_price == pytest.approx(0.48)
    fee = round(0.07 * 6 * 0.48 * 0.52, 4)
    assert accounts["e0"].cash == pytest.approx(500 - 6 * 0.48 - fee)
    assert client.sent[0] == dict(ticker=T, side="yes", count=10, price=0.50, tif="immediate_or_cancel",
                                  post_only=False, coid=client_order_id("abc123", T), expires=None)
    fill = ledger.fills()[0]
    assert (fill["price"], fill["fee"]) == (pytest.approx(0.48), pytest.approx(fee))
    order = ledger._rows("SELECT * FROM orders")[0]
    assert (order["status"], order["filled"], order["kind"]) == ("executed", 6, "taker")


async def test_nothing_on_offer_means_no_bet(live):
    broker, client, ledger, accounts = live
    r = await broker.execute(bet(), {}, {})
    assert not r.filled and r.reason == "no liquidity at limit price"
    assert accounts["e0"].cash == 500 and ledger._rows("SELECT status FROM orders")[0]["status"] == "canceled"


async def test_the_guard_says_no_before_kalshi_hears_anything(live):
    broker, client, ledger, _ = live
    r = await broker.execute(bet(count=100), {}, {})  # $50 > the $30 limit
    assert not r.filled and "limit" in r.reason
    broker.guard.halt("testing")
    r = await broker.execute(bet(), {}, {})
    assert not r.filled and r.reason == "trading halted: testing"
    assert client.sent == []


async def test_the_control_group_stays_on_paper(live):
    broker, client, ledger, accounts = live
    m = make_market(T, yes_bid=0.49, yes_ask=0.50)
    r = await broker.execute(bet("monkey"), {T: book_for(m)}, {})
    assert r.filled and client.sent == [] and accounts["monkey"].cash < 1000


async def test_a_real_bid_fills_once_and_is_cancelled_when_it_expires(live):
    broker, client, ledger, accounts = live
    [o] = await broker.place(bet(price=0.40, post_only=True, ttl_seconds=110), NOW)
    assert client.sent[0]["post_only"] and client.sent[0]["expires"] == int(NOW.timestamp()) + 110
    client.trade_into(o.order_id, 3)
    assert [f.count for f in await broker.poll(NOW + timedelta(seconds=30))] == [3]
    assert await broker.poll(NOW + timedelta(seconds=60)) == []  # the same fill isn't booked twice
    assert accounts["e0"].position(T) == (3, 0)
    gone = await broker.expire(NOW + timedelta(seconds=120))
    assert [x.order_id for x in gone] == [o.order_id] and client.orders[o.order_id]["status"] == "canceled"
    row = ledger._rows("SELECT status, filled, kind FROM orders")[0]
    assert (row["status"], row["filled"], row["kind"]) == ("canceled", 3, "maker")


async def test_our_books_match_kalshi_after_real_bets(live):
    broker, client, ledger, accounts = live
    client.asks[(T, "yes")] = (0.48, 100)
    client.asks[(T, "no")] = (0.50, 100)
    await broker.execute(bet("e0", Side.YES, 0.50, 10), {}, {})
    await broker.execute(TradeIntent("e1", [Leg(T, Side.NO, 0.52, 4)], "", intent_id="def"), {}, {})
    first = await reconcile(client, accounts, broker.pool_members, broker.resting)
    assert first.ok and first.positions[T] == (6.0, 6.0)
    # Kalshi pairs e0's YES with e1's NO into $1 each; our expected balance counts those pairs
    second = await reconcile(client, accounts, broker.pool_members, broker.resting, baseline=first.baseline)
    assert abs(second.drift) < 1e-6
    net, expected = our_books(accounts, {"e0", "e1"}, [])
    assert net == {T: 6.0}


def _desk(live, monkeypatch):
    broker, client, ledger, accounts = live
    cfg = DeskConfig(trading="live", live={"max_order_dollars": 30}, crypto_series=[], broad_scan=False)
    desk = Desk(cfg, client, [LongshotFade()], ledger, accounts=accounts)
    desk.pool.members = desk.broker.pool_members = {"e0", "e1"}
    return desk


async def test_a_lasting_mismatch_halts_trading_and_pulls_bids(live, monkeypatch):
    broker, client, ledger, accounts = live
    desk = _desk(live, monkeypatch)
    desk.pool.update(1000, NOW)
    await desk.reconcile_live()  # baseline
    assert not desk.guard.halted
    client.position[T] = 5.0  # Kalshi holds something our books don't know about
    await desk.broker.place(bet(price=0.40, post_only=True, ttl_seconds=600), NOW)
    await desk.reconcile_live()
    assert not desk.guard.halted  # one odd reading can be a settlement in flight
    await desk.reconcile_live()
    assert desk.guard.halted and "positions differ" in desk.guard.state["reason"]
    assert client.cancel_all_calls == 1 and desk.broker.resting == []
    desk.guard.resume()
    assert not desk.guard.halted and desk.guard.books() == {}


async def test_a_bid_taken_the_second_it_went_up_is_booked_before_the_check(live, monkeypatch):
    # 2026-10-27: two bids in a row filled within the run that posted them; Kalshi showed the position
    # before our books did, two "mismatches" halted trading, and the kill switch dropped the second fill
    broker, client, ledger, accounts = live
    desk = _desk(live, monkeypatch)
    desk.pool.update(1000, NOW)
    await desk.reconcile_live()  # baseline
    for _ in range(3):
        [o] = await desk.broker.place(bet(price=0.40, post_only=True, ttl_seconds=110), NOW)
        client.trade_into(o.order_id, 2)
        await desk.reconcile_live()
        assert not desk.guard.halted
    assert accounts["e0"].position(T) == (6, 0) and client.position[T] == 6


async def test_a_bid_that_filled_before_the_kill_switch_pulled_it_is_still_booked(live):
    broker, client, ledger, accounts = live
    [o] = await broker.place(bet(price=0.40, post_only=True, ttl_seconds=600), NOW)
    client.trade_into(o.order_id, 3)
    await broker.cancel_everything()
    assert accounts["e0"].position(T) == (3, 0) and broker.resting == []
    row = ledger._rows("SELECT status, filled FROM orders")[0]
    assert (row["status"], row["filled"]) == ("canceled", 3)


async def test_the_kill_switch_from_the_website_pulls_real_bids(live, monkeypatch):
    broker, client, ledger, accounts = live
    desk = _desk(live, monkeypatch)
    await desk.broker.place(bet(price=0.40, post_only=True, ttl_seconds=600), NOW)
    ledger.set_setting("trading", {"halted": True, "reason": "manager pressed stop", "by": "website"})
    await desk.check_guard()
    assert desk.broker.resting == [] and client.cancel_all_calls == 1
    assert desk.trading_status()["halted"] and desk.trading_status()["mode"] == "live"


async def test_a_big_loss_day_halts_until_resumed(live, monkeypatch):
    desk = _desk(live, monkeypatch)
    desk.pool.update(1000, NOW)
    desk.pool.update(840, NOW + timedelta(hours=1))  # $160 down: past the $150 hard limit
    await desk.reconcile_live()
    assert desk.guard.halted and "lost $160.00 today" in desk.guard.state["reason"]


def test_live_trading_needs_both_switches_and_a_key(monkeypatch, tmp_path):
    cfg = DeskConfig(trading="live")
    monkeypatch.delenv("KALSHI_LIVE_TRADING", raising=False)
    with pytest.raises(LiveSetupError, match="KALSHI_LIVE_TRADING=yes"):
        live_client(cfg)
    monkeypatch.setenv("KALSHI_LIVE_TRADING", "yes")
    monkeypatch.delenv("KALSHI_API_KEY_ID", raising=False)
    with pytest.raises(LiveSetupError, match="API key"):
        live_client(cfg)

    class NoKey(FakeKalshi):
        signer = None

    with pytest.raises(LiveSetupError):
        Desk(cfg, NoKey(), [LongshotFade()], Ledger(":memory:"))
    bad = tmp_path / "desk.yaml"
    bad.write_text("trading: real\n")
    with pytest.raises(ValueError, match="paper or live"):
        DeskConfig.load(bad)


async def test_waiting_bids_dont_count_as_missing_cash(live):
    """Real Kalshi leaves a waiting bid's money in the balance (the 2026-10-19 false halt)."""
    broker, client, ledger, accounts = live
    first = await reconcile(client, accounts, broker.pool_members, broker.resting)
    [o] = await broker.place(bet(price=0.92, count=1.65, post_only=True, ttl_seconds=110), NOW)
    waiting = await reconcile(client, accounts, broker.pool_members, broker.resting, baseline=first.baseline)
    assert abs(waiting.drift) < 1e-6
    client.trade_into(o.order_id, 1.65)
    await broker.poll(NOW + timedelta(seconds=30))
    filled = await reconcile(client, accounts, broker.pool_members, broker.resting, baseline=first.baseline)
    assert abs(filled.drift) < 1e-6 and filled.ok
