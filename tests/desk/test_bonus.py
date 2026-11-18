from datetime import datetime, timedelta, timezone

from desk import bonus, notify
from desk.kalshi.models import Side
from desk.live.guard import Guard
from desk.paper.broker import RestingOrder
from desk.paper.ledger import Ledger
from desk.strategies.base import Leg, TradeIntent
from tests.desk.conftest import NOW
from tests.desk.test_runner import desk_and_client  # noqa: F401 (fixture)

ON = {"share": 0.10, "min_pool": 0.0}


def test_the_pot_gets_a_tenth_of_a_winning_week_and_goes_to_the_winner():
    led = Ledger(":memory:")
    s = bonus.hand_out(led, ON, office_pnl=200.0, pool=1200, winner="nickel_maker", now=NOW)
    assert (s["winner"], s["given"], s["left"], s["pot"]) == ("nickel_maker", 20.0, 20.0, 0.0)
    # She used $15; the $5 left returns, a losing week adds nothing, and the new winner gets the $5
    bonus.spend(led, s, 15.0)
    s = bonus.hand_out(led, ON, office_pnl=-50.0, pool=1100, winner="nickel_picker", now=NOW)
    assert (s["winner"], s["given"]) == ("nickel_picker", 5.0)


def test_no_pot_until_the_pool_is_big_enough():
    led = Ledger(":memory:")
    s = bonus.hand_out(led, {"share": 0.1, "min_pool": 500}, office_pnl=30.0, pool=130, winner="nickel_maker", now=NOW)
    assert s["winner"] is None and s["pot"] == 0.0


def test_the_winner_bets_bigger_out_of_the_same_pool(desk_and_client):
    desk, _ = desk_and_client
    desk.pool.update(1000, NOW)
    t = "KXBTC15M-26OCT151200-00"
    normal, _ = desk.size(TradeIntent("longshot_fade", [Leg(t, Side.YES, 0.50, 100)], ""))
    desk.bonus = bonus.hand_out(desk.ledger, ON, 200.0, 1000, "longshot_fade", NOW)  # $20 to bet
    bigger, _ = desk.size(TradeIntent("longshot_fade", [Leg(t, Side.YES, 0.50, 100)], ""))
    assert bigger.legs[0].count == 2 * normal.legs[0].count and abs(bigger.bonus - 0.5) < 1e-9
    other, _ = desk.size(TradeIntent("cover_arb", [Leg(t, Side.YES, 0.50, 100)], ""))
    assert other.bonus == 0.0
    # Only what's left: $3 of bonus on a $10 bet
    bonus.spend(desk.ledger, desk.bonus, 17.0)
    capped, _ = desk.size(TradeIntent("longshot_fade", [Leg(t, Side.YES, 0.50, 100)], ""))
    assert capped.legs[0].count == normal.legs[0].count + 6


def test_bonus_bets_move_no_money_between_accounts(desk_and_client):
    desk, _ = desk_and_client
    before = sum(a.cash for a in desk.accounts.values())
    desk.bonus = bonus.hand_out(desk.ledger, ON, 200.0, 1000, "longshot_fade", NOW)
    assert sum(a.cash for a in desk.accounts.values()) == before
    assert desk.ledger._rows("SELECT count(*) AS n FROM transfers")[0]["n"] == 0


def test_an_unfilled_bonus_bid_gives_the_bonus_back(desk_and_client):
    desk, _ = desk_and_client
    desk.bonus = bonus.hand_out(desk.ledger, ON, 200.0, 1000, "longshot_fade", NOW)
    o = RestingOrder("o1", "longshot_fade", "T", "yes", 0.5, 20, NOW.isoformat(), NOW.isoformat(), bonus=0.5)
    bonus.spend(desk.ledger, desk.bonus, 0.5 * 0.5 * 20)  # $5 went out with the bid
    o.filled = 8
    desk._bid_ended(o, "bid expired, part filled")
    assert desk.bonus["left"] == 20 - 5 + 0.5 * 0.5 * 12
    assert bonus.load(desk.ledger)["left"] == desk.bonus["left"]


def test_a_pause_pings_the_phone_once(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send", lambda *a, **k: sent.append(a) or True)
    g = Guard(Ledger(":memory:"))
    g.halt("our books don't match Kalshi: cash is off by $+16.67")
    g.halt("something else")  # already paused: no second ping
    assert len(sent) == 1 and "16.67" in sent[0][1]


def test_daily_summary_goes_out_once_after_9pm(desk_and_client, monkeypatch):
    desk, _ = desk_and_client
    desk.guard = Guard(desk.ledger)
    sent = []
    monkeypatch.setattr(notify, "configured", lambda: True)
    monkeypatch.setattr(notify, "send", lambda title, msg, **k: sent.append((title, msg)) or True)
    pacific = timezone(timedelta(hours=-7))
    nine = datetime(2026, 10, 20, 21, 1, tzinfo=pacific)
    noon = (nine - timedelta(hours=9)).astimezone(timezone.utc).isoformat()
    desk.ledger.record_settlement("longshot_fade", "LS-1", 1.0, 2.5, ts=noon)
    desk.daily_summary(nine - timedelta(hours=1))  # 8 PM: not yet
    assert not sent
    desk.daily_summary(nine.astimezone(timezone.utc))
    desk.daily_summary((nine + timedelta(minutes=2)).astimezone(timezone.utc))
    assert len(sent) == 1 and sent[0][0] == "▲ Up $2.50 today"
    assert "1 of 1 bet won · " in sent[0][1]


def test_daily_message_reads_like_the_widget():
    msgs = []
    import desk.notify as n
    orig = n.send
    n.send = lambda title, message, **k: msgs.append((title, message)) or True
    try:
        n.daily(1.42, 6, 5, ("Nickel Nora", 0.88), 103.21, 2.10, 3)
        n.daily(0.0, 0, 0, None, 100.0, 0.0, 0)
    finally:
        n.send = orig
    assert msgs[0][0] == "▲ Up $1.42 today"
    assert "5 of 6 bets won · Nickel Nora led (+$0.88)" in msgs[0][1]
    assert "Pool $103.21 · $2.10 riding on 3 bets" in msgs[0][1]
    assert msgs[1][0] == "Quiet day: no bets settled"


def test_nothing_is_sent_without_pushover_keys(monkeypatch):
    monkeypatch.delenv("PUSHOVER_TOKEN", raising=False)
    monkeypatch.delenv("PUSHOVER_USER", raising=False)
    assert notify.send("t", "m") is False


def test_the_daily_stop_on_real_money_pings_the_phone_once(desk_and_client, monkeypatch):
    import asyncio
    desk, _ = desk_and_client
    desk.guard = Guard(desk.ledger)
    desk.strategies = []
    monkeypatch.setattr("desk.runner._now", lambda: NOW)
    sent = []
    monkeypatch.setattr(notify, "send", lambda title, msg, **k: sent.append(msg) or True)
    desk.pool.update(200, NOW)
    for k in desk.pool.members:
        desk.accounts[k].cash *= 0.8  # the pool loses 20% today
    asyncio.run(desk.run_strategies(None))
    asyncio.run(desk.run_strategies(None))
    assert len(sent) == 1 and "daily stop" in sent[0] and "midnight" in sent[0]


def test_the_models_bet_cap_trims_a_bet_and_never_grows_one(desk_and_client):
    desk, _ = desk_and_client
    desk.pool.update(1000, NOW)
    t = "KXBTC15M-26OCT151200-00"
    normal, _ = desk.size(TradeIntent("longshot_fade", [Leg(t, Side.YES, 0.50, 100)], ""))
    desk.bet_caps = {"longshot_fade": 4.0}  # the nightly model: past $4 the extra dollars lose
    capped, _ = desk.size(TradeIntent("longshot_fade", [Leg(t, Side.YES, 0.50, 100)], ""))
    assert capped.legs[0].count == 8 and normal.legs[0].count > 8
    desk.bet_caps = {"longshot_fade": 1000.0}
    same, _ = desk.size(TradeIntent("longshot_fade", [Leg(t, Side.YES, 0.50, 100)], ""))
    assert same.legs[0].count == normal.legs[0].count
