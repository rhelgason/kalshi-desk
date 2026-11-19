"""
Polymarket US recorder (2026-11-19): a tape of its 15-minute up/down markets, so one day we can replay Sadie's rule on
it the way we did on Kalshi's trades. Polymarket US's public data (gateway.polymarket.us, no key) has order books and
best bid/offer but no trade history, so this keeps its own: every POLL seconds the best bid/ask, the last trade and the
running contracts traded of each open 15-minute window (a jump in `traded` between two looks is a trade of that size
near `last`), every BOOK seconds the top of the book, and each window's settlement once it's in.

Not part of the bot and not in the database (Supabase stays free): files on the server's own disk, one per UTC day
(today's plain, finished days gzipped),
    OUT/YYYY-MM-DD.jsonl[.gz]  {"t": unix seconds, "k": "q" (quote) | "b" (book) | "s" (settlement) | "m" (market), ...}

    python research/polymarket/recorder.py /home/desk/pm_tape         (deploy/pm-recorder.service, always on)

Revisit when the office is big enough that Kalshi's markets fill up (CLAUDE.md, "Other sites").
"""
import gzip, json, os, sys, time
from datetime import datetime, timedelta, timezone

import httpx

GATEWAY = "https://gateway.polymarket.us/v1"
POLL, BOOK, LIST = 2.0, 10.0, 60.0  # seconds; ~5 requests a second against a public limit of 25
DEPTH = 8  # book levels kept per side
FAMILIES = ("-updown-15m-",)  # bitcoin, ether, solana, XRP, gold, silver, oil, natural gas


def px(x):
    return float(x["value"]) if isinstance(x, dict) and x.get("value") is not None else None


class Recorder:
    def __init__(self, out: str):
        self.out = out
        os.makedirs(out, exist_ok=True)
        self.http = httpx.Client(timeout=10, headers={"User-Agent": "market-data-recorder/1.0"})
        self.open: dict[str, dict] = {}  # slug -> {"end": windowEnd, "start": windowStart}
        self.settle: dict[str, float] = {}  # slug -> when to ask for its settlement
        self.day, self.fh = None, None
        self.last_book: dict[str, float] = {}
        self.listed = 0.0

    def compress_old(self, today: str) -> None:
        # Today's file is plain text (a restart or crash never leaves a broken gzip); finished days get compressed
        for name in os.listdir(self.out):
            if name.endswith(".jsonl") and name[:-6] != today:
                src = os.path.join(self.out, name)
                with open(src, "rb") as a, gzip.open(src + ".gz", "ab") as b:
                    b.write(a.read())
                os.remove(src)

    def write(self, rec: dict) -> None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if day != self.day:
            if self.fh:
                self.fh.close()
            self.compress_old(day)
            self.fh = open(os.path.join(self.out, f"{day}.jsonl"), "a")
            self.day = day
        self.fh.write(json.dumps(rec, separators=(",", ":")) + "\n")

    def get(self, path: str, **params):
        for attempt in range(4):
            try:
                r = self.http.get(GATEWAY + path, params=params)
                if r.status_code == 429:
                    time.sleep(1.5 * 2 ** attempt)
                    continue
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.json()
            except httpx.HTTPError:
                time.sleep(1.0 * 2 ** attempt)
        return None

    def list_markets(self) -> None:
        now = datetime.now(timezone.utc)
        found = []
        for off in range(0, 2000, 200):
            d = self.get("/markets", closed="false", limit=200, offset=off,
                         endDateMin=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                         endDateMax=(now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"))
            ms = (d or {}).get("markets") or []
            found += ms
            if len(ms) < 200:
                break
        for m in found:
            slug = m.get("slug") or ""
            terms = m.get("assetPriceTerms") or {}
            if not any(f in slug for f in FAMILIES) or not terms.get("windowEnd") or slug in self.open:
                continue
            end = datetime.fromisoformat(terms["windowEnd"].replace("Z", "+00:00")).timestamp()
            start = datetime.fromisoformat(terms["windowStart"].replace("Z", "+00:00")).timestamp()
            self.open[slug] = {"end": end, "start": start}
            self.write({"t": round(time.time(), 2), "k": "m", "slug": slug, "start": start, "end": end,
                        "asset": (terms.get("asset") or {}).get("symbol"), "index": terms.get("indexSymbol"),
                        "beat": px(terms.get("priceToBeat"))})
        self.listed = time.time()

    def quote(self, slug: str) -> None:
        d = (self.get(f"/markets/{slug}/bbo") or {}).get("marketData")
        if not d:
            return
        s = d.get("lastPriceSample") or {}
        self.write({"t": round(time.time(), 2), "k": "q", "slug": slug, "bid": px(d.get("bestBid")),
                    "ask": px(d.get("bestAsk")), "last": px(d.get("lastTradePx")), "traded": d.get("sharesTraded"),
                    "oi": d.get("openInterest"), "lts": s.get("ts"), "state": d.get("state")})

    def book(self, slug: str) -> None:
        d = (self.get(f"/markets/{slug}/book") or {}).get("marketData")
        if not d:
            return
        side = lambda rows: [[px(r["px"]), float(r["qty"])] for r in (rows or [])[:DEPTH]]
        self.write({"t": round(time.time(), 2), "k": "b", "slug": slug, "bids": side(d.get("bids")),
                    "asks": side(d.get("offers"))})

    def settlement(self, slug: str) -> bool:
        d = self.get(f"/markets/{slug}/settlement")
        if not d:
            return False
        self.write({"t": round(time.time(), 2), "k": "s", "slug": slug, "data": d})
        return True

    def run(self) -> None:
        while True:
            t0 = time.time()
            if t0 - self.listed > LIST:
                self.list_markets()
            for slug, w in list(self.open.items()):
                if t0 >= w["end"] + 5:
                    self.open.pop(slug)
                    self.settle[slug] = w["end"] + 180  # results come in within minutes
                    continue
                if t0 < w["start"] - 60:
                    continue
                self.quote(slug)
                if t0 - self.last_book.get(slug, 0) >= BOOK:
                    self.book(slug)
                    self.last_book[slug] = t0
            for slug, when in list(self.settle.items()):
                if t0 >= when and (self.settlement(slug) or t0 > when + 3600):
                    self.settle.pop(slug)
                    self.last_book.pop(slug, None)
            if self.fh:
                self.fh.flush()
            time.sleep(max(0.0, POLL - (time.time() - t0)))


if __name__ == "__main__":
    Recorder(sys.argv[1] if len(sys.argv) > 1 else "data/pm_tape").run()
