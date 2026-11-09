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
from desk.runner import MISMATCH_CHECKS
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
        self.weather_cash = 0.0  # on shard 0; the rest of `cash` is on the coins' shard 2
        self.transfers: list[tuple[float, int, int]] = []

    async def transfer_between_shards(self, dollars, source, destination):
        self.transfers.append((dollars, source, destination))
        self.weather_cash += dollars if destination == 0 else -dollars

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

    async def get_balance_breakdown(self):
        return [{"exchange_index": 0, "balance": f"{self.weather_cash:.4f}"},
                {"exchange_index": 2, "balance": f"{self.cash - self.weather_cash:.4f}"}]


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


async def test_a_fill_kalshi_hasnt_listed_yet_is_still_booked(live):
    """2026-11-08: the order said filled and finished, the fills list was still empty, and the bet never reached
    our books (Kalshi paid it; the books were $0.84 off for days)."""
    broker, client, ledger, accounts = live
    [o] = await broker.place(bet(price=0.40, post_only=True, ttl_seconds=110), NOW)
    client.trade_into(o.order_id, 5)
    client.orders[o.order_id]["status"] = "executed"  # finished (the rest expired)
    client.fills.clear()  # Kalshi's fills list lags behind the order
    [f] = await broker.poll(NOW + timedelta(seconds=30))
    assert (f.count, f.avg_price) == (5, 0.40) and accounts["e0"].position(T) == (5, 0)
    assert broker.resting == [] and await broker.poll(NOW + timedelta(seconds=60)) == []
    assert ledger._rows("SELECT filled FROM orders")[0]["filled"] == 5


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
    for _ in range(MISMATCH_CHECKS - 1):
        await desk.reconcile_live()
        assert not desk.guard.halted  # odd readings for a while can be a fill or a payout in flight
    await desk.reconcile_live()
    assert desk.guard.halted and "positions differ" in desk.guard.state["reason"]
    assert client.cancel_all_calls == 1 and desk.broker.resting == []
    desk.guard.resume()
    assert not desk.guard.halted and desk.guard.books() == {}


async def test_the_safety_check_resumes_on_its_own_once_the_books_agree(live, monkeypatch):
    """11-04: the owner shouldn't have to press Resume for a difference that sorted itself out."""
    broker, client, ledger, accounts = live
    desk = _desk(live, monkeypatch)
    desk.pool.update(1000, NOW)
    await desk.reconcile_live()  # baseline
    client.position[T] = 5.0
    for _ in range(MISMATCH_CHECKS):
        await desk.reconcile_live()
    assert desk.guard.halted
    del client.position[T]  # Kalshi and our books agree again
    await desk.reconcile_live()
    assert not desk.guard.halted and "safety check" in desk.guard.state["resumed_by"]
    # A pause the manager (or the daily-loss stop) chose stays until the manager lifts it
    desk.guard.halt("manager pressed stop", by="website")
    await desk.reconcile_live()
    assert desk.guard.halted


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


def test_the_order_limit_can_be_a_share_of_the_pool(live):
    broker, client, ledger, accounts = live
    g = broker.guard
    g.limits["max_order_pct"] = 0.25
    g.equity = 300.0
    assert g.refuse(70.0) is None and "$75.00 limit" in g.refuse(80.0)
    g.equity = 0.0  # pool not known yet: the dollar cap
    assert "limit" in g.refuse(31.0)


async def test_the_loss_limit_can_be_a_share_of_the_pool(live, monkeypatch):
    desk = _desk(live, monkeypatch)
    desk.guard.limits["max_daily_loss_pct"] = 0.20
    desk.pool.update(300, NOW)
    desk.pool.update(250, NOW + timedelta(hours=1))  # $50 down: past $40 but under 20% ($60)
    await desk.reconcile_live()
    assert not desk.guard.halted
    desk.pool.update(235, NOW + timedelta(hours=2))  # $65 down
    await desk.reconcile_live()
    assert desk.guard.halted and "20% of the pool, $60.00" in desk.guard.state["reason"]


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


async def test_a_market_kalshi_hasnt_paid_out_yet_doesnt_halt_trading(live, monkeypatch):
    """2026-11-02: we settled a ZEC win, but Kalshi still held it (and its money) for 6+ minutes: trading halted.
    A recently settled market that Kalshi still holds as we held it is on its way, not a mismatch."""
    broker, client, ledger, accounts = live
    desk = _desk(live, monkeypatch)
    desk.pool.update(1000, NOW)
    client.asks[(T, "no")] = (0.95, 100)
    await desk.broker.execute(TradeIntent("e0", [Leg(T, Side.NO, 0.95, 4)], "", intent_id="z"), {}, {})
    await desk.reconcile_live()  # baseline, the bet open on both sides
    desk.broker.settle(T, 0.0)   # we see the result: NO won, our books are paid
    for _ in range(3):           # Kalshi hasn't paid yet: the position and its $4 are still "out"
        await desk.reconcile_live()
        assert not desk.guard.halted
    assert desk.guard.books()["strikes"] == 0
    del client.position[T]; client.cash += 4.0   # now Kalshi pays
    await desk.reconcile_live()
    assert not desk.guard.halted and desk.guard.books()["strikes"] == 0
    # A settlement older than the allowance that Kalshi still holds is a real problem
    client.position[T] = -4.0
    monkeypatch.setattr(desk, "recently_settled", lambda minutes=720: {})
    for _ in range(MISMATCH_CHECKS):
        await desk.reconcile_live()
    assert desk.guard.halted


async def test_differences_that_fix_themselves_on_different_markets_dont_halt(live, monkeypatch):
    """2026-11-03: a payout Kalshi made before we saw the result (BNB), then two fills Kalshi showed seconds
    before our books (BNB, then SOL), on back-to-back checks: three markets, each right by the next check."""
    broker, client, ledger, accounts = live
    desk = _desk(live, monkeypatch)
    desk.pool.update(1000, NOW)
    await desk.reconcile_live()  # baseline
    for t in ("KXBNB-A", "KXBNB-B", "KXSOL-C"):
        client.position[t] = -2.5   # Kalshi has it this check...
        await desk.reconcile_live()
        assert not desk.guard.halted
        del client.position[t]      # ...and the next check agrees again
    await desk.reconcile_live()
    assert not desk.guard.halted and desk.guard.books()["strikes"] == 0


async def test_the_bot_keeps_cash_on_the_weather_shard_too(live, monkeypatch):
    """2026-11-03: Kalshi refused every weather bid for "insufficient balance": all the cash was on the coins' shard,
    and on 11-04 still was, though Kalshi had been asked to keep the split. The bot moves it itself, once."""
    broker, client, ledger, accounts = live
    desk = _desk(live, monkeypatch)
    desk.config.shards = {2: 80, 0: 20}
    desk.pool.update(1000, NOW)
    await desk.reconcile_live(); await desk.reconcile_live()
    assert client.transfers == [(200.0, 2, 0)] and desk.journal.info["shards"] == {0: 200.0, 2: 800.0}
    # Weather spends most of its share: no new transfer within 10 minutes, then a top-up
    client.weather_cash = 50.0
    await desk.reconcile_live()
    assert len(client.transfers) == 1
    ledger.set_status("_shard_move", {"at": (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()})
    await desk.reconcile_live()
    assert client.transfers[-1] == (150.0, 2, 0)
