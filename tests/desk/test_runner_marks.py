from types import SimpleNamespace

from desk.runner import _mark


def test_open_bets_are_worth_the_last_trade_like_kalshi_says():
    # A market closed but not yet paid: the book is 0-100c (middle 50c), Kalshi values it at the last trade
    assert _mark(SimpleNamespace(last_price=0.98, mid=0.5)) == 0.98
    assert _mark(SimpleNamespace(last_price=None, mid=0.6)) == 0.6  # never traded: the middle of the book
    assert _mark(SimpleNamespace(last_price=0.0, mid=None)) is None
