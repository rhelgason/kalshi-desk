from dataclasses import replace
from datetime import datetime, timedelta, timezone

from desk.config import DeskConfig
from desk.kalshi.models import Side
from desk.runner import Desk
from desk.strategies import FinalWhistleFiona, HourlyHazel, SteadySadie, WeatherWendy
from desk.strategies.base import Snapshot
from tests.desk.conftest import NOW, make_market

# 2026-10-28 13:00 UTC = 9 am in New York, 6 am in Los Angeles
MORNING = datetime(2026, 10, 28, 13, 0, tzinfo=timezone.utc)


def weather(yes_bid, yes_ask, series="KXHIGHNY", day="26OCT28", strike="B67.5"):
    return make_market(f"{series}-{day}-{strike}", yes_bid=yes_bid, yes_ask=yes_ask, series=series,
                       event=f"{series}-{day}", close_in=timedelta(hours=12))


def game(yes_bid, yes_ask, ends_in, event="KXNBAGAME-26OCT28LALDEN", team="LAL"):
    m = make_market(f"{event}-{team}", yes_bid=yes_bid, yes_ask=yes_ask, series=event.split("-")[0], event=event,
                    close_in=timedelta(days=2))
    return replace(m, expected_expiration_time=MORNING + ends_in)


def snap(*markets, now=MORNING):
    return Snapshot.build(now, [], list(markets))


class TestWeatherWendy:
    def test_bids_on_a_morning_favorite_a_tick_over_the_best_bid(self, account):
        [bid] = WeatherWendy().evaluate(snap(weather(0.94, 0.97)), account)
        assert bid.post_only and bid.legs[0].side is Side.YES and bid.legs[0].limit_price == 0.95

    def test_the_no_side_of_a_long_shot_bracket_counts(self, account):
        [bid] = WeatherWendy().evaluate(snap(weather(0.03, 0.06)), account)
        assert bid.legs[0].side is Side.NO and bid.legs[0].limit_price == 0.95

    def test_only_mornings_of_the_day_itself_in_the_citys_time(self, account):
        w = WeatherWendy()
        assert w.evaluate(snap(weather(0.94, 0.97), now=MORNING + timedelta(hours=3)), account) == []  # noon in NY
        assert w.evaluate(snap(weather(0.94, 0.97, day="26OCT29")), account) == []  # tomorrow's market
        assert len(w.evaluate(snap(weather(0.94, 0.97, series="KXHIGHLAX"), now=MORNING + timedelta(hours=4)), account)) == 1

    def test_skips_toss_ups_and_other_series(self, account):
        w = WeatherWendy()
        assert w.evaluate(snap(weather(0.60, 0.64)), account) == []
        coin = make_market("KXBTC15M-X", yes_bid=0.94, yes_ask=0.97, series="KXBTC15M", event="KXBTC15M-X")
        assert w.evaluate(snap(coin), account) == []

    def test_a_reprice_below_her_band_is_dropped(self):
        m = weather(0.94, 0.97)
        [bid] = WeatherWendy().evaluate(snap(m), _empty())
        assert WeatherWendy().reprice(bid, m, replace(m, yes_bid=0.85, yes_ask=0.88)) is None


def hourly(yes_bid, yes_ask, close_in, strike="T86999.99"):
    return make_market(f"KXBTCD-26OCT2810-{strike}", yes_bid=yes_bid, yes_ask=yes_ask, series="KXBTCD",
                       event="KXBTCD-26OCT2810", close_in=close_in)


class TestHourlyHazel:
    def test_bids_on_an_hourly_favorite_5_to_21_minutes_out(self, account):
        h = HourlyHazel()
        [bid] = h.evaluate(snap(hourly(0.95, 0.97, timedelta(minutes=12)), now=NOW), account)
        assert bid.post_only and bid.legs[0].side is Side.YES and bid.legs[0].limit_price == 0.96
        assert h.evaluate(snap(hourly(0.95, 0.97, timedelta(minutes=4)), now=NOW), account) == []
        assert h.evaluate(snap(hourly(0.95, 0.97, timedelta(minutes=25)), now=NOW), account) == []

    def test_several_strikes_in_one_hour_and_no_15_minute_coins(self, account):
        h = HourlyHazel()
        two = snap(hourly(0.95, 0.97, timedelta(minutes=12)), hourly(0.02, 0.04, timedelta(minutes=12), "T88999.99"),
                   now=NOW)
        assert len(h.evaluate(two, account)) == 2
        coin = make_market("KXBTC15M-X", yes_bid=0.95, yes_ask=0.97, series="KXBTC15M", event="KXBTC15M-X",
                           close_in=timedelta(minutes=8))
        assert h.evaluate(snap(coin, now=NOW), account) == []


class TestFinalWhistleFiona:
    def test_bids_on_the_winner_late_in_the_game(self, account):
        [bid] = FinalWhistleFiona().evaluate(snap(game(0.97, 0.99, timedelta(hours=1))), account)
        assert bid.legs[0].side is Side.YES and bid.legs[0].limit_price == 0.98

    def test_not_before_the_last_three_hours_or_long_after(self, account):
        f = FinalWhistleFiona()
        assert f.evaluate(snap(game(0.97, 0.99, timedelta(hours=4))), account) == []
        assert f.evaluate(snap(game(0.97, 0.99, -timedelta(hours=3))), account) == []

    def test_baseball_and_hockey_only_in_the_last_hour_and_no_football(self, account):
        f = FinalWhistleFiona()
        for event in ("KXMLBGAME-26OCT28NYYLAD", "KXNHLGAME-26OCT28TORBOS"):
            assert f.evaluate(snap(game(0.97, 0.99, timedelta(hours=2), event=event, team="X")), account) == []
            assert len(f.evaluate(snap(game(0.97, 0.99, timedelta(minutes=40), event=event, team="X")), account)) == 1
        assert f.evaluate(snap(game(0.97, 0.99, timedelta(minutes=40), event="KXNFLGAME-26OCT28KCDET", team="KC")),
                          account) == []

    def test_one_bid_per_game(self, account):
        both = snap(game(0.97, 0.99, timedelta(hours=1)), game(0.01, 0.03, timedelta(hours=1), team="DEN"))
        assert len(FinalWhistleFiona().evaluate(both, account)) == 1

    def test_skips_a_game_still_in_doubt(self, account):
        assert FinalWhistleFiona().evaluate(snap(game(0.80, 0.82, timedelta(hours=1))), account) == []


def _empty():
    from desk.paper.account import PaperAccount
    return PaperAccount("t", 1000.0)


def test_coin_staff_never_see_weather_and_wendy_never_sees_coins(tmp_path):
    from desk.paper.ledger import Ledger

    cfg = DeskConfig(db_path=str(tmp_path / "d.db"), use_database_url=False,
                     other_series=["KXHIGHNY"], strategies={})
    desk = Desk(cfg, client=None, strategies=[SteadySadie(), WeatherWendy()], ledger=Ledger(cfg.db_path))
    s = snap(weather(0.94, 0.97), make_market("KXBTC15M-X", series="KXBTC15M", event="KXBTC15M-X"))
    assert set(desk.scoped(s, "coins").markets) == {"KXBTC15M-X"}
    assert set(desk.scoped(s, "other").markets) == {"KXHIGHNY-26OCT28-B67.5"}
    desk.config.other_series = []
    assert desk.scoped(s, "coins") is s
