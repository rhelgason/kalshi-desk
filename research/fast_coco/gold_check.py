"""Does a gold price check help Goldie the way the coin check helped the coins? (2026-11-09)

Kalshi's 15-minute gold markets on Sadie's rules (hourly_check.sadie, 5-9 minutes left), with and without the check:
skip a bid when gold's own price gives our side worse odds than the bid. Gold's second-by-second price is Binance's
PAXG (a token backed by one ounce of gold; data/binance1s PAXGUSDT-1s-*.zip). PAXG trades at a small premium to spot
gold, so the strike is moved by the PAXG/strike ratio at the window's open (the market asks "up or down from the
open"), not compared in dollars.
    python research/fast_coco/gold_check.py data/tape_cmdty/KXGOLD15M.jsonl.gz
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from cmdty_check import show  # noqa: E402
from hourly_check import Binance, markets, sadie, side_odds  # noqa: E402


def main():
    path = sys.argv[1]
    v = Binance("PAXG")
    rows = []
    for m in markets(path):
        if not m["t"] or m.get("result") not in ("yes", "no") or not m.get("strike"):
            continue
        r = sadie(m, 300, 540)
        if not r:
            continue
        side, spent, got, at, price = r
        opened = v.get(m["close"] - 900)
        if not opened:
            continue
        odds = side_odds(v, m["close"], opened, int(at), side)  # PAXG's own open stands in for the strike
        if odds is None:
            continue
        rows.append({"close": m["close"], "price": price, "spent": spent, "odds": odds,
                     "pnl": (got if side == m["result"] else 0) - spent})
    print(f"Gold, 5-9 minutes left, $10 a market ({len(rows)} bets with a PAXG price):")
    show("every bid", rows)
    show("gold check (odds >= bid)", [r for r in rows if r["odds"] >= r["price"]])
    show("check skipped these", [r for r in rows if r["odds"] < r["price"]])
    show("97c+ only", [r for r in rows if r["price"] >= 0.97])
    show("97c+ with the check", [r for r in rows if r["price"] >= 0.97 and r["odds"] >= r["price"]])
    show("92c+ with check, 1c margin", [r for r in rows if r["odds"] >= r["price"] + 0.01])


if __name__ == "__main__":
    main()
