"""Second-by-second backtest of Fast Coco against her 2-minute twin (the rules in desk/fast.py).

Inputs: Kalshi's trade tape for the last 6 minutes of each market (tape.py), the minute quotes in the history store,
and Binance 1-second closes. For each market:
  - the book at second s = the last minute-close quote, updated by every trade since (a taker selling YES prints
    the best bid, a taker buying YES prints the best ask)
  - Fast Coco decides every second from 300 to 120 seconds left: bid one tick over the best bid on a 94-99c
    favorite (spread <= 2c), follow the price, and pull on a coin move beyond K sigma over the last L seconds
    (several K/L variants run side by side; "none" never pulls)
  - the twin looks when the 2-minute cron would (unix second % 120 == 5) and bids for 110 seconds
  - fills: the tape rule (through our price = full size, at it = 30%), each bid live 0.15 s after it's posted
    and until 0.15 s after it's cancelled. The coin price known at second s is Binance's close of second s-1.
Every bot bets up to $10 a market (the cap), so results are per $1 and fill rates; compounding comes after.
    python replay_fast.py TAPE_DIR BINANCE_DIR HISTORY_DB OUT.json COIN...
"""
import array, csv, gzip, io, json, math, os, sqlite3, statistics as st, sys, zipfile
from datetime import datetime, timezone

TAPE, BIN, DB, OUT, COINS = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5:]
STAKE, QUEUE, LAT = 10.0, 0.3, 0.15
LO, HI, SPREAD, MINS, MAXS = 0.94, 0.99, 0.02, 120, 300
TWIN_EVERY, TWIN_OFF, TWIN_TTL, COOL = 120, 5, 110, 5
VARIANTS = [("none", None, None)] + [(f"K{k}L{l}", k, l) for l in (2, 5) for k in (2.0, 1.5, 1.0, 0.5)]
# Other ways to use the server: always-on but JOINING the best bid (no improving tick), with and without pulls;
# and the twin's schedule with pulls added
JOIN = [("join", None, None), ("joinK1.0L2", 1.0, 2), ("joinK1.5L5", 1.5, 5)]
TWINPULL = [("twinK1.0L2", 1.0, 2), ("twinK1.5L5", 1.5, 5), ("twinK2.0L2", 2.0, 2)]


def tick(p):
    return 0.001 if p >= 0.9 or p <= 0.1 else 0.01


def load_binance(coin):
    files = sorted(f for f in os.listdir(BIN) if f.startswith(coin + "USDT-1s-"))
    t0 = int(datetime.fromisoformat(files[0][-14:-4] + "T00:00:00+00:00").timestamp())
    px = array.array("d", [0.0]) * (len(files) * 86400 + 86400)
    for f in files:
        with zipfile.ZipFile(os.path.join(BIN, f)) as z:
            for row in csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]))):
                t = int(row[0]); t = t // 1_000_000 if t > 10**14 else t // 1000
                i = t - t0
                if 0 <= i < len(px):
                    px[i] = float(row[4])
    last = 0.0  # carry quiet seconds forward
    for i in range(len(px)):
        if px[i] > 0:
            last = px[i]
        else:
            px[i] = last
    return t0, px


def favorite(bid, ask, improve=1):
    """(side, our bid price) for Coco's band, in the side's own prices; bid/ask are YES prices."""
    for side, b, a in (("yes", bid, ask), ("no", round(1 - ask, 4), round(1 - bid, 4))):
        if LO <= a <= HI and 0 < a - b <= SPREAD + 1e-9 and b > 0:
            price = min(round(b + improve * tick(b), 4), round(a - tick(a), 4))
            return side, round(max(price, b), 4)
    return None


class Bot:
    def __init__(self):
        self.bids = []          # [side, price, count, live_from, live_until, filled, ghost]
        self.invested = 0.0
        self.contracts = 0.0
        self.side = None
        self.ghost_cost = 0.0   # pulled bids the tape would have filled
        self.ghost_contracts = 0.0
        self.ghost_side = None
        self.pulls = 0
        self.cool = 0

    def room(self):
        resting = sum(b[1] * (b[2] - b[5]) for b in self.bids if not b[6] and b[4] == math.inf)
        return STAKE - self.invested - resting

    def post(self, side, price, now, ttl=math.inf):
        count = math.floor(self.room() / price * 100) / 100
        if count >= 0.01 and count * price >= 0.25:
            self.bids.append([side, price, count, now + LAT, now + ttl if ttl != math.inf else math.inf, 0.0, False])

    def live(self):
        return [b for b in self.bids if not b[6] and b[4] == math.inf]

    def fill(self, t, yp, n, taker):
        for b in self.bids:
            side, price = b[0], b[1]
            if not (b[3] < t <= b[4]) or taker == side or b[2] - b[5] < 0.01:
                continue
            p = yp if side == "yes" else round(1 - yp, 4)
            if p < price - 1e-9:
                q = n
            elif abs(p - price) < 1e-9:
                q = n * QUEUE
            else:
                continue
            q = math.floor(min(q, b[2] - b[5]) * 100) / 100
            if q <= 0:
                continue
            b[5] = round(b[5] + q, 2)
            if b[6]:
                self.ghost_cost += q * price; self.ghost_contracts += q; self.ghost_side = side
            else:
                self.invested += q * price; self.contracts += q; self.side = side


def run_market(m, quotes, t0, px):
    close, trades = m["close"], m["t"]
    # sigma of 1-second moves over the 10 minutes before the window
    s0 = close - MAXS
    r = []
    for s in range(s0 - 600, s0):
        a, b = px[s - 1 - t0], px[s - t0]
        if a > 0 and b > 0:
            r.append(math.log(b / a))
    sig = st.pstdev(r) if len(r) > 300 else None
    fast = {name: Bot() for name, _, _ in VARIANTS + JOIN}
    twin = Bot()
    twins = {name: Bot() for name, _, _ in TWINPULL}
    qi = sorted(quotes)
    ti = 0
    bid = ask = None
    # book at the start: last minute quote at or before the window start, then trades since
    for s in range(close - MAXS - 60, close - MINS + 1):
        # 1) trades in (s-1, s]: fill bids posted before them, then update the book estimate
        while ti < len(trades) and trades[ti][0] <= s:
            t, yp, n, taker = trades[ti]
            if t > s - 1 and s > close - MAXS:
                for bot in list(fast.values()) + [twin] + list(twins.values()):
                    bot.fill(t, yp, n, taker)
            if taker == "no":   # sold YES into the best bid
                bid = yp
                if ask is not None and ask <= bid:
                    ask = round(bid + tick(bid), 4)
            else:               # bought YES at the best ask
                ask = yp
                if bid is not None and bid >= ask:
                    bid = round(ask - tick(ask), 4)
            ti += 1
        if s in quotes:          # a minute closed: Kalshi's own quote replaces the estimate
            bid, ask = quotes[s]
        left = close - s
        if left > MAXS or bid is None or ask is None:
            continue
        pick = pick_imp = favorite(bid, ask) if MINS <= left <= MAXS else None
        # coin move known at s: Binance closes of seconds up to s-1
        def move(L):
            a, b = px[s - 1 - L - t0], px[s - 1 - t0]
            return math.log(b / a) / (sig * math.sqrt(L)) if (sig and a > 0 and b > 0) else None
        pick_join = favorite(bid, ask, 0) if MINS <= left <= MAXS else None
        for name, K, L in VARIANTS + JOIN:
            bot = fast[name]
            pick = pick_join if name.startswith("join") else pick_imp
            mv = move(L) if K is not None else None
            for b in bot.live():
                against = None if mv is None else (mv if b[0] == "yes" else -mv)
                if against is not None and against < -K:
                    b[4] = s + LAT
                    bot.bids.append([b[0], b[1], round(b[2] - b[5], 2), s + LAT, math.inf, 0.0, True])
                    bot.pulls += 1; bot.cool = s + COOL
                elif not pick or (b[0], b[1]) != pick:
                    b[4] = s + LAT
            if pick and s >= bot.cool and not bot.live() and (sig or K is None):
                bot.post(pick[0], pick[1], s)
        pick = pick_imp
        if s % TWIN_EVERY == TWIN_OFF and pick and not any(b[4] > s for b in twin.bids):
            twin.post(pick[0], pick[1], s, ttl=TWIN_TTL)
        for name, K, L in TWINPULL:
            bot = twins[name]
            mv = move(L)
            for b in bot.bids:
                if not b[6] and b[3] <= s < b[4]:
                    against = None if mv is None else (mv if b[0] == "yes" else -mv)
                    if against is not None and against < -K:
                        bot.bids.append([b[0], b[1], round(b[2] - b[5], 2), s + LAT, b[4], 0.0, True])
                        b[4] = s + LAT
                        bot.pulls += 1
            if s % TWIN_EVERY == TWIN_OFF and pick and not any(b[4] > s for b in bot.bids if not b[6]):
                bot.post(pick[0], pick[1], s, ttl=TWIN_TTL)
    # trades after the window still fill bids that were live (cancels take 0.15 s; the twin's last bid lives 110 s)
    while ti < len(trades):
        t, yp, n, taker = trades[ti]
        for bot in list(fast.values()) + [twin] + list(twins.values()):
            bot.fill(t, yp, n, taker)
        ti += 1
    res = lambda bot: {"inv": round(bot.invested, 4), "ct": round(bot.contracts, 2), "side": bot.side,
                       "gcost": round(bot.ghost_cost, 4), "gct": round(bot.ghost_contracts, 2), "gside": bot.ghost_side,
                       "pulls": bot.pulls}
    return {"close": close, "result": m["result"], "twin": res(twin), **{k: res(v) for k, v in fast.items()},
            **{k: res(v) for k, v in twins.items()}}


db = sqlite3.connect(DB)
out = []
for coin in COINS:
    t0, px = load_binance(coin)
    hi = t0 + len(px) - 86400
    quotes_all = {}
    for tk, data in db.execute("select ticker, data from market_history where series=? and close_ts>=?",
                               (f"KX{coin}15M", t0 + 1200)):
        c = json.loads(data)["c"]
        quotes_all[tk] = {row[0]: (row[1], row[2]) for row in c if row[1] and row[2]}
    n = 0
    with gzip.open(os.path.join(TAPE, f"KX{coin}15M.jsonl.gz"), "rt") as fh:
        for line in fh:
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            if m["ticker"] not in quotes_all or not (t0 + 1200 < m["close"] < hi):
                continue
            r = run_market(m, quotes_all[m["ticker"]], t0, px)
            r["coin"], r["ticker"] = coin, m["ticker"]
            out.append(r); n += 1
    print(coin, n, "markets replayed", file=sys.stderr, flush=True)
json.dump(out, open(OUT, "w"))
