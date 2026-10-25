"""Fast Coco and her 2-minute twin (no network)."""

import math
from datetime import timedelta

from desk import fast
from desk.fast import FAST, TWIN, Bid, CoinTape, FastDesk, Live, favorite, match
from desk.kalshi.models import Level, Orderbook, Side
from desk.paper.ledger import Ledger
from tests.desk.conftest import NOW, make_market

T0 = NOW.timestamp()


def trade(t, yes_price, count, taker, tid):
    return {"created_time": fast._iso(t), "yes_price_dollars": str(yes_price), "no_price_dollars": str(round(1 - yes_price, 4)),
            "count_fp": str(count), "taker_side": taker, "trade_id": tid}


def desk_with(market):
    d = FastDesk(Ledger(":memory:"), client=None)
    d.load()
    live = Live(market)
    d.markets[market.ticker] = live
    return d, live


def calm_coin(d, coin="SOL-USD", end=T0, drift=0.0):
    tape = d.coins[coin]
    for i in range(700):  # ten-plus minutes of small wiggles
        tape.push(end - 700 + i, 100 * (1 + 0.0001 * math.sin(i) + drift * i))
    return tape


def test_coin_tape_measures_moves_in_its_own_sigmas():
    tape = CoinTape()
    for i in range(700):
        tape.push(T0 - 700 + i, 100 * (1 + 0.0001 * math.sin(i)))
    assert abs(tape.move(T0 - 1)) < 3
    tape.push(T0, 99.0)  # a 1% drop in a second is many sigmas
    assert tape.move(T0) < -10
    assert tape.move(T0 + 60) is None  # a stale feed says nothing


def test_tape_fills_through_fully_and_at_price_by_queue_share():
    bid = Bid(FAST, "M", Side.YES, 0.96, 10, live_from=T0)
    assert match(bid, trade(T0 + 1, 0.95, 4, "no", "a")) == 4      # sold YES through our price
    assert match(bid, trade(T0 + 1, 0.96, 10, "no", "b")) == 3     # at our price: 30% of it
    assert match(bid, trade(T0 + 1, 0.95, 4, "yes", "c")) == 0     # a buyer, not a seller
    assert match(bid, trade(T0 - 1, 0.90, 4, "no", "d")) == 0      # before the bid was up
    bid.live_until = T0 + 2
    assert match(bid, trade(T0 + 3, 0.90, 4, "no", "e")) == 0      # after it was cancelled


def test_favorite_is_cocos_band_with_a_tight_spread():
    m = make_market("KXSOL15M-X", yes_bid=0.955, yes_ask=0.96)
    side, price = favorite(m)
    assert side is Side.YES and 0.955 <= price < 0.96
    assert favorite(make_market("KXSOL15M-Y", yes_bid=0.80, yes_ask=0.82)) is None
    assert favorite(make_market("KXSOL15M-Z", yes_bid=0.90, yes_ask=0.96)) is None  # 6c spread


def _book(ticker, yes_bid, no_bid):
    return Orderbook(ticker, [Level(yes_bid, 500)], [Level(no_bid, 500)])


def test_fast_bids_in_the_window_and_pulls_on_a_jump_toward_the_line():
    m = make_market("KXSOL15M-X", series="KXSOL15M", yes_bid=0.95, yes_ask=0.96, close_in=timedelta(minutes=4))
    d, live = desk_with(m)
    calm_coin(d)
    lm = d.live_market(live, _book(m.ticker, 0.95, 0.04))
    d.fast_step(live, lm, T0)
    [bid] = [b for b in d.bids if b.bot == FAST]
    assert bid.side is Side.YES and 2.5 <= bid.price * bid.count <= 2.63  # 3% of $87.63
    d.coins["SOL-USD"].push(T0 + 1, 99.0)  # SOL drops: bad news for a YES favorite
    d.fast_step(live, lm, T0 + 1)
    assert bid.live_until < math.inf and any(b.ghost for b in d.bids)
    d.fast_step(live, lm, T0 + 2)  # cooling down: no new bid yet
    assert not [b for b in d.bids if b.bot == FAST and not b.ghost and b.live_until == math.inf]
    # The tape would have filled the pulled bid; the market then goes NO: pulling saved a loss
    d.apply_trades(live, [trade(T0 + 3, 0.90, 50, "no", "x")])
    assert d.accounts[FAST].trades == 0
    d.settle(live, "no")
    d.writes_drain = [d.writes.get_nowait() for _ in range(d.writes.qsize())]
    outcome = [a for fn, a, kw in d.writes_drain if a and a[0] == "pull_outcome"]
    assert outcome and outcome[0][1]["won"] is False and outcome[0][1]["pnl_if_kept"] < 0


def test_no_fast_bids_while_the_coin_feed_is_cold():
    m = make_market("KXSOL15M-X", series="KXSOL15M", yes_bid=0.95, yes_ask=0.96, close_in=timedelta(minutes=4))
    d, live = desk_with(m)
    d.fast_step(live, d.live_market(live, _book(m.ticker, 0.95, 0.04)), T0)
    assert d.bids == []


def test_twin_bids_once_per_look_for_110_seconds_and_fills_from_the_tape():
    m = make_market("KXSOL15M-X", series="KXSOL15M", yes_bid=0.95, yes_ask=0.96, close_in=timedelta(minutes=4))
    d, live = desk_with(m)
    lm = d.live_market(live, _book(m.ticker, 0.95, 0.04))
    d.twin_step(live, lm, T0)
    d.twin_step(live, lm, T0 + 1)
    [bid] = [b for b in d.bids if b.bot == TWIN]
    assert bid.live_until == T0 + fast.TWIN_TTL
    d.apply_trades(live, [trade(T0 + 5, 0.94, 100, "no", "y"), trade(T0 + 5, 0.94, 100, "no", "y")])
    acct = d.accounts[TWIN]
    assert acct.trades == 1 and m.ticker in acct.positions  # the duplicate trade id is ignored
    d.settle(live, "yes")
    assert acct.cash > fast.START_CASH and not d.bids


def test_report_compares_the_two_and_charges_the_server():
    led = Ledger(":memory:")
    for bot, pnl in ((FAST, 1.5), (TWIN, 0.5)):
        led.set_starting_cash(bot, fast.START_CASH)
        led.record_fill(bot, "M", Side.YES, 10, 0.95, 0.0, ts="2026-11-02T00:00:00+00:00")
        led.record_settlement(bot, "M", 1.0, pnl, ts="2026-11-02T00:15:00+00:00")
    out = fast.fast_report(led)
    assert "2026-11" in out and "+1.00" in out  # fast beat the twin by $1 before the server's cost


def test_a_quiet_coin_still_gets_a_reading():
    tape = CoinTape()
    for i in range(0, 700, 20):  # DOGE: a trade every 20 seconds, heartbeats in between
        tape.push(T0 - 700 + i, 0.2 * (1 + 0.001 * (i % 40 == 0)))
        tape.hold(T0 - 700 + i + 19)
    assert tape.sigma(int(T0)) is not None and tape.move(T0) is not None
