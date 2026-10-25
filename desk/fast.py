"""
Fast Coco: the always-on Closing Time Coco, for the DigitalOcean server (deploy/server/README.md).

The hosted bot wakes every 2 minutes and its bids live 110 seconds. Here one process runs all day:

  - Kalshi's order books twice a second and the trade tape every second (public data, no API key)
  - Coinbase's live price stream for each coin
  - Fast Coco (`fast_maker`): Coco's rules (94-99c favorites, 2-5 minutes left, a bid one tick over
    the best bid), but her bid stays up the whole window, follows the price, and is PULLED when the
    coin jumps toward the line (the 2-second move beyond PULL_SIGMA). Kalshi's tape, Oct 18-25: fills
    right after such a jump lost 2c per $1; avoiding them lifted the rest by ~0.2c.
  - The twin (`late_maker_twin`): today's Coco exactly, looking only when the 2-minute cron would.
    Same tape, same fill rules, same money: the difference between the two is what the server is worth.

Both bet pretend money (3% of their own pot, at most $10, one market's worth at a time) in the database's
"fast" schema. Fills come from the real tape like Training's (desk.paper.broker.PaperBroker.match): a trade
through our price fills us, a trade at it fills a 30% queue share. Every pulled bid is kept as a "ghost"
until its market settles, so `desk fast-report` can say what pulling saved and what it cost.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import statistics
import time
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Optional

from desk.kalshi.client import KalshiClient
from desk.kalshi.models import Market, Side
from desk.paper.account import PaperAccount
from desk.paper.ledger import Ledger
from desk.strategies.bitcoin import contracts, patient_price

logger = logging.getLogger(__name__)

SCHEMA = "fast"
COINS = {"KXETH15M": "ETH-USD", "KXSOL15M": "SOL-USD", "KXXRP15M": "XRP-USD", "KXDOGE15M": "DOGE-USD"}
FAST, TWIN = "fast_maker", "late_maker_twin"
START_CASH = 87.63           # the real book's pool when the trial began (2026-10-25)
BET_PCT, MAX_BET = 0.03, 10.0
MIN_PRICE, MAX_PRICE, MAX_SPREAD = 0.94, 0.99, 0.02
MIN_SECONDS, MAX_SECONDS = 120, 300
PULL_SIGMA, PULL_WINDOW, PULL_COOLDOWN = 1.0, 2, 5.0
QUEUE_SHARE = 0.3
ORDER_LATENCY = 0.15         # seconds before a posted/cancelled bid takes effect at Kalshi
TAPE_GRACE = 5.0             # a cancelled bid still counts against the stake until the tape has caught up with it
TWIN_EVERY, TWIN_OFFSET, TWIN_TTL = 120, 5, 110   # pg_cron's */2 schedule, the run's ~5s, Coco's bid life
SERVER_COST = float(os.environ.get("FAST_SERVER_COST", "6"))  # dollars a month (DigitalOcean)


def _ts(s: str) -> float:
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


# ----------------------------------------------------------------------
# Coin prices
# ----------------------------------------------------------------------

class CoinTape:
    """Last price each second for one coin, and how far it moved in units of its own jitter."""

    def __init__(self, keep: int = 900):
        self.px: dict[int, float] = {}
        self.order: deque[int] = deque()
        self.keep = keep
        self.last_at = 0.0
        self._sigma: Optional[float] = None
        self._sigma_at = 0

    def push(self, t: float, price: float) -> None:
        self.hold(t - 1)
        sec = int(t)
        if not self.order or sec > self.order[-1]:
            self.order.append(sec)
        self.px[sec] = price
        self._trim()
        self.last_at = t

    def hold(self, t: float) -> None:
        """Carry the last price through every second up to `t`: a second without a trade (DOGE often goes 10+)
        is a second the price stood still, and it counts toward the coin's jitter."""
        if not self.order:
            return
        last = self.order[-1]
        for sec in range(last + 1, int(t) + 1):
            self.order.append(sec)
            self.px[sec] = self.px[last]
        self._trim()
        self.last_at = max(self.last_at, t)

    def _trim(self) -> None:
        while len(self.order) > self.keep:
            self.px.pop(self.order.popleft(), None)

    def at(self, s: int) -> Optional[float]:
        for k in range(10):  # quiet seconds carry the last price forward
            if s - k in self.px:
                return self.px[s - k]
        return None

    def sigma(self, now: int) -> Optional[float]:
        """Stdev of 1-second log moves over the last 10 minutes (recomputed every 10 seconds)."""
        if self._sigma is None or now - self._sigma_at >= 10:
            r = []
            for s in range(now - 600, now):
                a, b = self.at(s - 1), self.at(s)
                if a and b:
                    r.append(math.log(b / a))
            self._sigma = statistics.pstdev(r) if len(r) > 300 else None
            self._sigma_at = now
        return self._sigma

    def move(self, now: float, seconds: int = PULL_WINDOW) -> Optional[float]:
        """The last `seconds` of movement in sigmas (positive = up); None while the feed is cold or stale."""
        s = int(now)
        if now - self.last_at > 5:
            return None
        sig, a, b = self.sigma(s), self.at(s - seconds), self.at(s)
        if not (sig and a and b):
            return None
        return math.log(b / a) / (sig * math.sqrt(seconds))


# ----------------------------------------------------------------------
# Paper bids filled from the real tape
# ----------------------------------------------------------------------

@dataclass
class Bid:
    bot: str
    ticker: str
    side: Side
    price: float
    count: float
    live_from: float
    live_until: float = math.inf
    filled: float = 0.0
    ghost: bool = False          # pulled: still matched against the tape, never charged
    pulled_move: float = 0.0
    reason: str = ""

    @property
    def remaining(self) -> float:
        return round(self.count - self.filled, 2)


def match(bid: Bid, trade: dict) -> float:
    """Contracts this trade gives `bid` (the rule PaperBroker.match uses for Training's bids)."""
    t = _ts(trade["created_time"])
    taker = trade.get("taker_outcome_side") or trade.get("taker_side")
    if not (bid.live_from < t <= bid.live_until) or taker == bid.side.value or bid.remaining < 0.01:
        return 0.0
    price = float(trade.get(f"{bid.side.value}_price_dollars") or 1)
    size = float(trade.get("count_fp") or 0)
    if price < bid.price - 1e-9:
        qty = size
    elif abs(price - bid.price) < 1e-9:
        qty = size * QUEUE_SHARE
    else:
        return 0.0
    return math.floor(min(qty, bid.remaining) * 100) / 100


def favorite(m: Market) -> Optional[tuple[Side, float]]:
    """Coco's pick: the side priced 94-99c with a tight spread, and the bid she'd post for it."""
    for side in (Side.YES, Side.NO):
        bid, ask = m.bid(side), m.ask(side)
        if MIN_PRICE <= ask <= MAX_PRICE and 0 < ask - bid <= MAX_SPREAD + 1e-9:
            price = patient_price(m, side, 1)
            if price:
                return side, price
    return None


def stake(acct: PaperAccount) -> float:
    return min(max(acct.equity({}), 0.0) * BET_PCT, MAX_BET)


# ----------------------------------------------------------------------
# The desk
# ----------------------------------------------------------------------

@dataclass
class Live:
    market: Market
    strike_side_up: bool = True      # "price up in next 15 mins?": YES pays when the coin finishes higher
    trades_seen: set = field(default_factory=set)
    trades_from: float = 0.0
    settled: bool = False


class FastDesk:
    def __init__(self, ledger: Ledger, client: KalshiClient):
        self.ledger, self.client = ledger, client
        self.coins = {c: CoinTape() for c in COINS.values()}
        self.markets: dict[str, Live] = {}
        self.bids: list[Bid] = []
        self.cooldown: dict[str, float] = {}
        self.writes: asyncio.Queue = asyncio.Queue()
        self.stats = {"started_at": _iso(time.time()), "book_reads": 0, "trade_reads": 0, "errors": 0,
                      "pulls": 0, "fills": {FAST: 0, TWIN: 0}, "coinbase_msgs": 0, "last_error": None}
        self.accounts: dict[str, PaperAccount] = {}
        self.last_twin_look = int(time.time() - TWIN_OFFSET) // TWIN_EVERY
        self.last_equity_hour = None

    # --- bookkeeping -------------------------------------------------

    def load(self) -> None:
        have = {r["strategy"] for r in self.ledger._rows("SELECT strategy FROM accounts")}
        for k in (FAST, TWIN):
            if k not in have:
                self.ledger.set_starting_cash(k, START_CASH)
                self.ledger.record_event("fast", {"action": "opened", "cash": START_CASH}, strategy=k)
        self.accounts = self.ledger.load_accounts(START_CASH, [FAST, TWIN])

    def write(self, fn, *a, **kw) -> None:
        """Database writes go through one background task, so the price loop never waits on them."""
        self.writes.put_nowait((fn, a, kw))

    async def writer(self) -> None:
        while True:
            fn, a, kw = await self.writes.get()
            try:
                await asyncio.to_thread(fn, *a, **kw)
            except Exception as e:  # keep trading; the next restart rebuilds from what was saved
                logger.exception("database write failed")
                self.stats["errors"] += 1
                self.stats["last_error"] = f"db: {e}"[:200]

    def committed(self, bot: str, ticker: str) -> float:
        """Dollars this bot has in a market: what filled plus what's still bid (pulled ghosts don't count)."""
        acct = self.accounts[bot]
        pos = acct.positions.get(ticker)
        held = (pos.yes_cost + pos.no_cost) if pos else 0.0
        cutoff = time.time() - TAPE_GRACE  # fills for a just-cancelled bid can still arrive from the tape
        return held + sum(b.price * b.remaining for b in self.bids
                          if b.bot == bot and b.ticker == ticker and not b.ghost and b.live_until > cutoff)

    def free_cash(self, bot: str) -> float:
        cutoff = time.time() - TAPE_GRACE
        return self.accounts[bot].cash - sum(b.price * b.remaining for b in self.bids
                                             if b.bot == bot and not b.ghost and b.live_until > cutoff)

    def post(self, bot: str, live: Live, side: Side, price: float, now: float, ttl: float = math.inf,
             reason: str = "") -> Optional[Bid]:
        room = min(stake(self.accounts[bot]) - self.committed(bot, live.market.ticker), self.free_cash(bot))
        count = contracts(room / price) if price > 0 else 0
        if count < 0.01 or count * price < 0.25:  # Kalshi's smallest order
            return None
        bid = Bid(bot, live.market.ticker, side, price, count, live_from=now + ORDER_LATENCY,
                  live_until=now + ttl if ttl != math.inf else math.inf, reason=reason)
        self.bids.append(bid)
        return bid

    def cancel(self, bid: Bid, now: float, ghost: bool = False, move: float = 0.0) -> None:
        bid.live_until = now + ORDER_LATENCY
        if ghost:  # keep it, uncharged, to see what the tape would have done to it
            ghost_bid = replace(bid, live_from=bid.live_until, live_until=math.inf, ghost=True, pulled_move=move,
                                count=bid.remaining, filled=0.0)
            self.bids.append(ghost_bid)

    # --- decisions ---------------------------------------------------

    def live_market(self, live: Live, book) -> Market:
        yb, nb = book.best_bid(Side.YES), book.best_bid(Side.NO)
        return replace(live.market, yes_bid=yb, no_bid=nb, yes_ask=round(1 - nb, 4) if nb else 0.0,
                       no_ask=round(1 - yb, 4) if yb else 0.0)

    def fast_step(self, live: Live, m: Market, now: float) -> None:
        t = live.market.ticker
        left = live.market.seconds_to_close(datetime.fromtimestamp(now, timezone.utc)) or 0
        mine = [b for b in self.bids if b.bot == FAST and b.ticker == t and not b.ghost and b.live_until == math.inf]
        pick = favorite(m) if MIN_SECONDS <= left <= MAX_SECONDS else None
        coin = self.coins[COINS[live.market.series_ticker or t.split("-")[0]]]
        move = coin.move(now)
        for b in mine:
            against = None if move is None else (move if b.side is Side.YES else -move)
            if against is not None and against < -PULL_SIGMA:
                self.cancel(b, now, ghost=True, move=round(against, 2))
                self.cooldown[t] = now + PULL_COOLDOWN
                self.stats["pulls"] += 1
                self.write(self.ledger.record_event, "pull", {
                    "ticker": t, "side": b.side.value, "price": b.price, "count": b.remaining,
                    "move_sigma": round(against, 2), "seconds_left": round(left)}, strategy=FAST)
            elif not pick or pick != (b.side, b.price):
                self.cancel(b, now)   # out of the window or band, or the price moved: re-bid below
        if not pick or now < self.cooldown.get(t, 0) or move is None:
            return  # no bids while the coin feed is cold: pulling is the point of this bot
        if not any(b.live_until == math.inf for b in self.bids
                   if b.bot == FAST and b.ticker == t and not b.ghost):
            self.post(FAST, live, pick[0], pick[1], now, reason=f"fast: {pick[0].value} {pick[1]:.3f}, {left:.0f}s left")

    def twin_step(self, live: Live, m: Market, now: float) -> None:
        """Today's Coco: one look per cron run, a bid that lives 110 seconds, no coin feed."""
        left = live.market.seconds_to_close(datetime.fromtimestamp(now, timezone.utc)) or 0
        if not (MIN_SECONDS <= left <= MAX_SECONDS):
            return
        t = live.market.ticker
        if any(b.bot == TWIN and b.ticker == t and b.live_until > now for b in self.bids):
            return
        pick = favorite(m)
        if pick:
            self.post(TWIN, live, pick[0], pick[1], now, ttl=TWIN_TTL,
                      reason=f"twin: {pick[0].value} {pick[1]:.3f}, {left:.0f}s left")

    def apply_trades(self, live: Live, trades: list[dict]) -> None:
        for tr in sorted(trades, key=lambda x: x["created_time"]):
            if tr.get("trade_id") in live.trades_seen:
                continue
            live.trades_seen.add(tr.get("trade_id"))
            live.trades_from = max(live.trades_from, _ts(tr["created_time"]))
            for b in self.bids:
                if b.ticker != live.market.ticker:
                    continue
                qty = match(b, tr)
                if qty <= 0:
                    continue
                b.filled = round(b.filled + qty, 2)
                if b.ghost:
                    continue
                self.accounts[b.bot].apply_fill(b.ticker, b.side, qty, b.price, 0.0)
                self.stats["fills"][b.bot] += 1
                t = _ts(tr["created_time"])
                self.write(self.ledger.record_fill, b.bot, b.ticker, b.side, qty, b.price, 0.0,
                           reason=f"maker fill: {b.reason}", ts=_iso(t), seen_price=b.price,
                           book_depth=float(tr.get("count_fp") or 0), latency_ms=int((t - b.live_from) * 1000))

    def summarize(self, ticker: str) -> None:
        """One decisions row per bot per market: how many bids it posted, the last price, what filled."""
        for bot in (FAST, TWIN):
            mine = [b for b in self.bids if b.ticker == ticker and b.bot == bot and not b.ghost]
            if not mine:
                continue
            last, filled = mine[-1], round(sum(b.filled for b in mine), 2)
            pulls = sum(1 for b in self.bids if b.ticker == ticker and b.bot == bot and b.ghost)
            self.write(self.ledger.record_decision, bot, ticker, last.side.value, last.price,
                       round(sum(b.count for b in mine), 2), filled,
                       "filled" if filled > 0 else "no fill", f"{len(mine)} bids, {pulls} pulled: {last.reason}",
                       {"bids": len(mine), "pulls": pulls})

    def settle(self, live: Live, result: str) -> None:
        t, yes_value = live.market.ticker, 1.0 if result == "yes" else 0.0
        for bot, acct in self.accounts.items():
            if t in acct.positions:
                pnl = acct.settle(t, yes_value)
                self.write(self.ledger.record_settlement, bot, t, yes_value, pnl)
        self.summarize(t)
        for g in [b for b in self.bids if b.ticker == t and b.ghost]:
            won = (result == g.side.value)
            pnl = round(g.filled * ((1.0 if won else 0.0) - g.price), 4)
            self.write(self.ledger.record_event, "pull_outcome", {
                "ticker": t, "side": g.side.value, "price": g.price, "would_have_filled": g.filled,
                "won": won, "pnl_if_kept": pnl, "move_sigma": g.pulled_move}, strategy=FAST)
        self.bids = [b for b in self.bids if b.ticker != t]
        live.settled = True

    # --- loops -------------------------------------------------------

    async def coinbase(self) -> None:
        import websockets  # server-only dependency (requirements-server.txt)

        while True:
            try:
                async with websockets.connect("wss://ws-feed.exchange.coinbase.com", ping_interval=20) as ws:
                    await ws.send(json.dumps({"type": "subscribe", "product_ids": list(COINS.values()),
                                              "channels": ["ticker", "heartbeat"]}))
                    async for raw in ws:
                        msg = json.loads(raw)
                        coin = self.coins.get(msg.get("product_id"))
                        if coin is None:
                            continue
                        if msg.get("type") == "ticker":
                            coin.push(time.time(), float(msg["price"]))
                            self.stats["coinbase_msgs"] += 1
                        elif msg.get("type") == "heartbeat":
                            coin.hold(time.time())  # a quiet coin (DOGE) is still live: its price just held
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = f"coinbase: {e}"[:200]
                logger.warning("Coinbase feed dropped (%s); reconnecting", e)
                await asyncio.sleep(3)

    async def discover(self) -> None:
        while True:
            try:
                now = time.time()
                for series in COINS:
                    for m in await self.client.get_markets(series_ticker=series, status="open"):
                        if m.ticker not in self.markets and m.close_time:
                            self.markets[m.ticker] = Live(replace(m, series_ticker=series), trades_from=now)
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = f"discover: {e}"[:200]
            await asyncio.sleep(20)

    def active(self, now: float) -> list[Live]:
        out = []
        for live in self.markets.values():
            left = live.market.close_time.timestamp() - now
            if 0 < left <= MAX_SECONDS + 15 and not live.settled:
                out.append(live)
        return out

    async def books(self) -> None:
        while True:
            now = time.time()
            act = self.active(now)
            if act:
                try:
                    books = await self.client.get_orderbooks([lv.market.ticker for lv in act])
                    self.stats["book_reads"] += 1
                    now = time.time()
                    # once per 2-minute slot, as soon as the cron run would have looked (slow loops can't skip it)
                    slot = int(now - TWIN_OFFSET) // TWIN_EVERY
                    twin_look = slot != self.last_twin_look
                    for live in act:
                        book = books.get(live.market.ticker)
                        if book is None:
                            continue
                        m = self.live_market(live, book)
                        self.fast_step(live, m, now)
                        if twin_look:
                            self.twin_step(live, m, now)
                    if twin_look:
                        self.last_twin_look = slot
                except Exception as e:
                    self.stats["errors"] += 1
                    self.stats["last_error"] = f"books: {e}"[:200]
            await asyncio.sleep(max(0.05, 0.5 - (time.time() - now)))

    async def tape(self) -> None:
        while True:
            started = time.time()
            for live in [lv for lv in self.markets.values() if not lv.settled]:
                close = live.market.close_time.timestamp()
                if not any(b.ticker == live.market.ticker for b in self.bids) and started < close - MAX_SECONDS - 15:
                    continue
                if started > close + 30:
                    continue  # trading is over; settlement picks it up
                try:
                    trades = await self.client.get_trades(live.market.ticker, limit=1000, max_items=5000,
                                                          min_ts=int(live.trades_from) - 2)
                    self.stats["trade_reads"] += 1
                    self.apply_trades(live, trades)
                except Exception as e:
                    self.stats["errors"] += 1
                    self.stats["last_error"] = f"tape: {e}"[:200]
            await asyncio.sleep(max(0.1, 1.0 - (time.time() - started)))

    async def settlements(self) -> None:
        while True:
            now = time.time()
            for live in list(self.markets.values()):
                close = live.market.close_time.timestamp()
                if live.settled or now < close + 20:
                    continue
                held = any(live.market.ticker in a.positions for a in self.accounts.values())
                ghosts = any(b.ticker == live.market.ticker and b.ghost for b in self.bids)
                if not (held or ghosts):
                    if now > close + 45:  # the tape has stopped looking: nothing more can fill
                        self.summarize(live.market.ticker)
                        self.bids = [b for b in self.bids if b.ticker != live.market.ticker]
                        live.settled = True
                    continue
                try:
                    m = await self.client.get_market(live.market.ticker)
                    if m.result in ("yes", "no"):
                        # last look at the tape so no fill near the close is missed
                        self.apply_trades(live, await self.client.get_trades(
                            live.market.ticker, limit=1000, max_items=5000, min_ts=int(close) - 120))
                        self.settle(live, m.result)
                except Exception as e:
                    self.stats["errors"] += 1
                    self.stats["last_error"] = f"settle: {e}"[:200]
            # forget long-finished markets
            self.markets = {k: v for k, v in self.markets.items()
                            if not (v.settled and now > v.market.close_time.timestamp() + 3600)}
            await asyncio.sleep(10)

    async def health(self) -> None:
        while True:
            now = time.time()
            hour = int(now // 3600)
            if hour != self.last_equity_hour:
                for bot, acct in self.accounts.items():
                    self.write(self.ledger.record_equity, bot, acct.cash, acct.equity({}))
                self.last_equity_hour = hour
            feed_age = {c: round(now - tape.last_at, 1) for c, tape in self.coins.items()}
            self.write(self.ledger.set_status, "fast:health", {
                **self.stats, "at": _iso(now), "coin_feed_age_s": feed_age,
                "bids_up": sum(1 for b in self.bids if not b.ghost and b.live_until > now),
                "ghosts": sum(1 for b in self.bids if b.ghost),
                "accounts": {k: {"cash": round(a.cash, 2), "equity": round(a.equity({}), 2),
                                 "trades": a.trades, "open": sorted(a.positions)} for k, a in self.accounts.items()},
                "server_cost_per_month": SERVER_COST,
            })
            await asyncio.sleep(30)

    async def run(self) -> None:
        self.load()
        logger.info("Fast desk up: %s", {k: round(a.equity({}), 2) for k, a in self.accounts.items()})
        await asyncio.gather(self.writer(), self.coinbase(), self.discover(), self.books(), self.tape(),
                             self.settlements(), self.health())


async def run_fast(db_url: str) -> None:
    ledger = Ledger(db_url, SCHEMA)
    async with KalshiClient(env="prod", requests_per_second=12) as client:
        await FastDesk(ledger, client).run()


# ----------------------------------------------------------------------
# Is the server worth it?
# ----------------------------------------------------------------------

def fast_report(ledger: Ledger, server_since: Optional[str] = None) -> str:
    """Month by month: Fast Coco against her 2-minute twin, what pulling did, and the server's cost."""
    rows = ledger._rows("SELECT strategy, ts, pnl FROM settlements ORDER BY ts")
    fills = ledger._rows("SELECT strategy, ts, count, price FROM fills ORDER BY ts")
    events = ledger._rows("SELECT ts, kind, detail FROM events WHERE kind = 'pull_outcome' ORDER BY ts")
    months: dict[str, dict] = {}

    def month(ts: str) -> dict:
        return months.setdefault(ts[:7], {"pnl": {FAST: 0.0, TWIN: 0.0}, "bets": {FAST: 0, TWIN: 0},
                                          "bet_dollars": {FAST: 0.0, TWIN: 0.0}, "pulls": 0, "pull_saved": 0.0})
    for r in rows:
        if r["strategy"] in (FAST, TWIN):
            mo = month(r["ts"]); mo["pnl"][r["strategy"]] += float(r["pnl"]); mo["bets"][r["strategy"]] += 1
    for f in fills:
        if f["strategy"] in (FAST, TWIN):
            month(f["ts"])["bet_dollars"][f["strategy"]] += float(f["count"]) * float(f["price"])
    for e in events:
        d = json.loads(e["detail"]) if isinstance(e["detail"], str) else e["detail"]
        mo = month(e["ts"]); mo["pulls"] += 1; mo["pull_saved"] -= float(d.get("pnl_if_kept") or 0)
    accts = ledger.load_accounts(START_CASH, [FAST, TWIN])
    lines = ["Fast Coco (always-on server) vs her twin (today's 2-minute Coco), pretend money, same tape",
             f"{'month':8} {'fast P&L':>9} {'twin P&L':>9} {'server':>8} {'cost':>6} {'net':>8} "
             f"{'fast c/$':>9} {'twin c/$':>9} {'pulls':>6} {'pulls saved':>12}"]
    tot = {"fast": 0.0, "twin": 0.0, "cost": 0.0}
    for k in sorted(months):
        mo = months[k]
        f, tw = mo["pnl"][FAST], mo["pnl"][TWIN]
        cost = SERVER_COST
        tot["fast"] += f; tot["twin"] += tw; tot["cost"] += cost
        cpd = lambda b: (mo["pnl"][b] / mo["bet_dollars"][b] * 100) if mo["bet_dollars"][b] else 0.0
        lines.append(f"{k:8} {f:+9.2f} {tw:+9.2f} {f - tw:+8.2f} {cost:6.2f} {f - tw - cost:+8.2f} "
                     f"{cpd(FAST):+8.2f}c {cpd(TWIN):+8.2f}c {mo['pulls']:6d} {mo['pull_saved']:+12.2f}")
    lines.append(f"{'total':8} {tot['fast']:+9.2f} {tot['twin']:+9.2f} {tot['fast'] - tot['twin']:+8.2f} "
                 f"{tot['cost']:6.2f} {tot['fast'] - tot['twin'] - tot['cost']:+8.2f}")
    lines.append(f"Pots now: Fast Coco ${accts[FAST].equity({}):,.2f}, twin ${accts[TWIN].equity({}):,.2f} "
                 f"(both started at ${START_CASH})")
    lines.append("'server' = what the always-on version made beyond the twin; 'net' subtracts the server's cost "
                 "(a whole month is charged even for a partial one). 'pulls saved' = losses avoided minus "
                 "wins missed by pulling bids.")
    return "\n".join(lines)
