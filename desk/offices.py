"""
Friends' offices (2026-11-09): a friend's own Kalshi account, run by the same staff as the owner's real book.

Each office stands alone: its own Kalshi key and money, its own schema (office_<slug>: pool, levels, reviews,
Employee of the Week), its own pause button. What it shares with the owner is the playbook, copied from the
real book every few minutes: who is on staff (hires and firings), their settings, bet size and the review rules.
Friends never hire or fire; levels and strikes come from each office's own weekly reviews.

All offices run on the always-on server (`python -m desk offices`, deploy/offices.service), one after another
in one process, every 2 minutes, half a minute after the owner's run. Each office stays in memory between runs,
so the database is only written to (Supabase's free plan meters what is read back out).

Sharing Kalshi's order books with the owner:
  * a friend's staff decide on the clock of the owner's last run (Desk.lag), so they never find a market
    before the owner has had the chance to bid on it;
  * a bid that would top a family bid by a tick joins it instead (Desk.family): the owner's earlier bid
    keeps its place in the queue, and nobody in the family pays a tick more because of another.

Friends' Kalshi keys are stored encrypted (web/lib/vault.ts) to a key pair whose private half is only on the
server (OFFICE_KEY_PATH); the website can lock a key in but never read one back.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from desk import hr
from desk.cloud import CLOUD_OVERRIDES, LEASE, LEASE_SECONDS, STATE_KEY, restore_desk, saved_state
from desk.config import DeskConfig
from desk.feeds.crypto import CryptoFeed
from desk.kalshi.auth import KalshiSigner, load_private_key
from desk.kalshi.client import KalshiClient
from desk.paper.ledger import Ledger
from desk.runner import Desk
from desk.strategies import REGISTRY

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
EVERY = 120.0  # seconds between rounds, like the owner's pg_cron
OFFSET = 30.0  # seconds after the owner's run starts (pg_cron fires on even minutes)
SYNC_EVERY = 600.0  # the playbook from the owner's real book
# Kept per office: the owner's levels, strikes, awards and season belong to the owner
OWN_POLICY = ("season", "last_review", "realism", "autotune", "award_bonus", "reserve")
OFFICES_SQL = """
CREATE TABLE IF NOT EXISTS public.offices (
    slug TEXT PRIMARY KEY,
    user_id BIGINT,
    name TEXT NOT NULL,
    env TEXT NOT NULL DEFAULT 'prod',
    key_id TEXT,
    key_box TEXT,
    status TEXT NOT NULL DEFAULT 'setup',
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)"""


def schema_of(slug: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9]{1,23}", slug):
        raise ValueError(f"bad office name {slug!r}")
    return f"office_{slug}"


def office_config(slug: str, env: str = "prod") -> DeskConfig:
    """The real book's config (same staff, markets and limits) with the office's own tables."""
    cfg = DeskConfig.load(ROOT / "desk.real.yaml")
    for k, v in CLOUD_OVERRIDES.items():
        setattr(cfg, k, v)
    cfg.schema, cfg.env = schema_of(slug), env
    if cfg.trading != "live" or cfg.book != "real":
        raise ValueError("desk.real.yaml must be a live real-money book")
    return cfg


def open_box(box: str, private_key) -> bytes:
    """A Kalshi key the website locked (web/lib/vault.ts): AES-256-GCM, its key wrapped with RSA-OAEP-SHA256."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    d = json.loads(box)
    if d.get("v") != 1:
        raise ValueError("unknown key box version")
    aes = private_key.decrypt(base64.b64decode(d["key"]), padding.OAEP(
        mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    return AESGCM(aes).decrypt(base64.b64decode(d["iv"]), base64.b64decode(d["data"]), None)


def sync_playbook(real: Ledger, office: Ledger, strategies: dict) -> bool:
    """Copy the owner's playbook into an office: policy (minus its own season and reviews), hires, firings and
    settings. `strategies` is the office's config (desk.real.yaml's). Returns True if anything changed."""
    theirs, mine = hr.load_policy(real), hr.load_policy(office)
    new = {**{k: v for k, v in theirs.items() if k not in OWN_POLICY}, **{k: mine[k] for k in OWN_POLICY if k in mine}}
    changed = new != mine
    if changed:
        hr.save_policy(office, new)
    # The owner's staff on real money (load_roster adds a row, and a "hired" note, for anyone new to the office)
    hired = set(new.get("hired") or [])
    owner = {r["key"]: r for r in real.employee_rows()
             if r["key"] in REGISTRY and ((strategies.get(r["key"]) or {}).get("enabled", True) or r["key"] in hired)}
    roster = hr.load_roster(office, list(owner))
    for k, rec in roster.items():
        o = hr.EmployeeRecord.from_row(owner[k])
        before = rec.to_row()
        rec.params = o.params
        if o.status == "fired" and rec.status != "fired":
            rec.status = "fired"
            office.record_event("hr", {"action": "fired", "why": "the owner let them go"}, strategy=k)
        elif o.status != "fired" and rec.status == "fired":  # friends can't fire: only the owner's firing undone
            rec.status, rec.strikes = "active", 0
            office.record_event("hr", {"action": "rehired", "why": "back on the owner's staff"}, strategy=k)
        if rec.to_row() != before:
            office.upsert_employee(rec.to_row())
            changed = True
    return changed


def family_bids(ledger: Ledger, schemas: list[str], minutes: float = 30) -> dict[tuple[str, str], float]:
    """The family's best resting bid by (ticker, side), across the owner's real book and the offices."""
    since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    out: dict[tuple[str, str], float] = {}
    for s in schemas:
        rows = ledger.db.execute(
            f"SELECT ticker, side, max(price) AS price FROM {s}.orders WHERE status = 'resting' AND kind = 'maker'"
            " AND ts > ? GROUP BY ticker, side", (since,)).fetchall()
        for r in rows:
            k = (r["ticker"], r["side"])
            out[k] = max(out.get(k, 0.0), float(r["price"]))
    return out


def owner_last_run(ledger: Ledger) -> Optional[datetime]:
    """When the owner's last real-book run started (read in the database, so only the time comes back)."""
    row = ledger.db.execute(
        "SELECT (data::jsonb)->'last_run'->>'at' AS at FROM real.status WHERE key = '_state'").fetchone()
    return datetime.fromisoformat(row["at"]) if row and row["at"] else None


@dataclass
class Office:
    slug: str
    name: str
    env: str
    signer: KalshiSigner
    cfg: DeskConfig
    ledger: Ledger
    client: KalshiClient
    desk: Optional[Desk] = None
    state: dict = field(default_factory=dict)
    errors: int = 0


class Offices:
    def __init__(self, url: str, private_key, feed: Optional[CryptoFeed] = None):
        self.url = url
        self.private_key = private_key
        self.home = Ledger(url, None, shared=True)  # public: the offices list and the owner's tables by name
        self.home.db.execute(OFFICES_SQL)
        self.home.db.execute("ALTER TABLE public.offices ENABLE ROW LEVEL SECURITY")
        self.real = Ledger(url, "real", shared=True)
        self.offices: dict[str, Office] = {}
        self.feed = feed
        self._synced = 0.0

    def note(self, slug: str, status: Optional[str], note: Optional[str]) -> None:
        if status:
            self.home.db.execute("UPDATE public.offices SET status = ?, note = ?, updated_at = now() WHERE slug = ?",
                                 (status, note, slug))
        else:
            self.home.db.execute("UPDATE public.offices SET note = ?, updated_at = now() WHERE slug = ?", (note, slug))

    def refresh(self) -> None:
        """Pick up new offices and drop closed ones."""
        rows = self.home.db.execute(
            "SELECT slug, name, env, key_id, key_box, status FROM public.offices"
            " WHERE status IN ('ready', 'active') AND key_box IS NOT NULL").fetchall()
        wanted = {r["slug"]: r for r in rows}
        for slug in [s for s in self.offices if s not in wanted]:
            logger.warning("Office %s closed: no longer running it", slug)
            del self.offices[slug]
        for slug, r in wanted.items():
            if slug in self.offices and self.offices[slug].signer.key_id == r["key_id"]:
                continue
            try:
                signer = KalshiSigner(r["key_id"], load_private_key(open_box(r["key_box"], self.private_key)))
                cfg = office_config(slug, r["env"])
                ledger = Ledger(self.url, cfg.schema, shared=True)
                client = KalshiClient(env=cfg.env, signer=signer, allow_trading=True,
                                      requests_per_second=cfg.requests_per_second)
                self.offices[slug] = Office(slug, r["name"], r["env"], signer, cfg, ledger, client)
                logger.info("Office %s (%s) loaded: key %s", slug, r["name"], signer.fingerprint())
            except Exception as e:
                logger.exception("Office %s couldn't be loaded", slug)
                self.note(slug, None, f"couldn't load: {type(e).__name__}: {e}")

    async def open(self, o: Office) -> None:
        """A new office's first season: everyone on the owner's staff, sharing whatever Kalshi holds (often $0;
        a deposit later joins the pool on its own, runner.money_in_or_out)."""
        sync_playbook(self.real, o.ledger, o.cfg.strategies)
        open_bets = [p for p in await o.client.get_positions() if abs(float(p.get("position_fp") or 0)) > 0.005]
        if open_bets or await o.client.get_orders(status="resting"):
            raise RuntimeError("the Kalshi account already has open bets or orders: the office needs an empty "
                               "account to start from")
        cash = (await o.client.get_account())["cash"]
        roster = hr.load_roster(o.ledger, [r["key"] for r in o.ledger.employee_rows()])
        config = hr.effective_strategy_config(o.cfg.strategies, roster, hr.load_policy(o.ledger).get("hired") or ())
        staff = [k for k in roster if (config.get(k) or {}).get("enabled", True) and roster[k].status != "fired"]
        policy = hr.load_policy(o.ledger)
        policy["season"] = 0  # start_season counts up: the office's first season is season 1
        hr.save_policy(o.ledger, policy)
        detail = hr.start_season(o.ledger, staff, cash, o.cfg.starting_cash, {}, "the office opened")
        o.ledger.set_status(STATE_KEY, {})
        self.note(o.slug, "active", None)
        logger.warning("Office %s opened with $%.2f shared by %d employees", o.slug, cash, len(detail["members"]))

    async def run(self, o: Office, lag: timedelta, family: dict) -> None:
        if not o.ledger.try_lease(LEASE, LEASE_SECONDS):
            return
        try:
            if not o.ledger._rows("SELECT 1 FROM accounts LIMIT 1"):
                await self.open(o)
            season = o.ledger.refresh_season()
            if o.desk is None or o.desk.season != season:
                o.state = o.ledger.get_status(STATE_KEY) or {}  # read once, then kept in memory
                if o.state.get("season", season) != season:
                    o.state = {}
                o.desk = restore_desk(o.cfg, o.ledger, o.client, self.feed, o.state)
            o.desk.lag, o.desk.family = lag, family
            started = time.time()
            await o.desk.tick()
            o.state = saved_state(o.desk, self.feed, o.state)
            o.state["last_run"] = {"at": datetime.fromtimestamp(started, timezone.utc).isoformat(),
                                   "seconds": round(time.time() - started, 1)}
            o.ledger.set_status(STATE_KEY, o.state)
            if o.errors:
                self.note(o.slug, None, None)
            o.errors = 0
        except Exception as e:
            o.errors += 1
            o.desk = None  # start over from the saved state next time
            logger.exception("Office %s run failed", o.slug)
            self.note(o.slug, None, f"{datetime.now(timezone.utc):%b %d %H:%M} UTC: {type(e).__name__}: {e}"[:500])
        finally:
            o.ledger.release_lease(LEASE)

    async def round(self) -> None:
        self.refresh()
        if not self.offices:
            return
        if time.time() - self._synced > SYNC_EVERY:
            for o in self.offices.values():
                try:
                    if sync_playbook(self.real, o.ledger, o.cfg.strategies) and o.desk:
                        o.desk.sync_hr()
                except Exception:
                    logger.exception("Office %s: playbook sync failed", o.slug)
            self._synced = time.time()
        for o in list(self.offices.values()):
            # Each office sees everyone else's bids (the owner's and other friends'), not its own
            schemas = ["real"] + [x.cfg.schema for x in self.offices.values() if x is not o]
            family = family_bids(self.home, schemas)
            last = owner_last_run(self.home)
            behind = datetime.now(timezone.utc) - last if last else None
            # The owner's clock only while the owner is running normally (a stalled owner can't hold friends back)
            lag = behind if behind and behind < timedelta(seconds=EVERY * 1.25) else timedelta(0)
            await self.run(o, lag, family)


async def run_offices(once: bool = False) -> None:
    """The server's loop: every office, every 2 minutes, half a minute after the owner's run."""
    for k in ("PUSHOVER_TOKEN", "PUSHOVER_USER"):  # friends get no phone pings, and the owner none about them
        os.environ.pop(k, None)
    for k in ("KALSHI_API_KEY_ID", "KALSHI_PRIVATE_KEY", "KALSHI_PRIVATE_KEY_PATH"):
        os.environ.pop(k, None)  # never the server's own key: each office signs with its friend's
    url = os.environ["DATABASE_URL"]
    from cryptography.hazmat.primitives import serialization

    private_key = serialization.load_pem_private_key(Path(os.environ["OFFICE_KEY_PATH"]).read_bytes(), password=None)
    feed = CryptoFeed(tuple(DeskConfig.load(ROOT / "desk.real.yaml").crypto_symbols))
    offices = Offices(url, private_key, feed)
    try:
        while True:
            now = time.time()
            # Next even minute + OFFSET, like pg_cron's schedule for the owner
            wait = (OFFSET - now % EVERY) % EVERY
            if not once:
                await asyncio.sleep(wait)
            try:
                await offices.round()
            except Exception:
                logger.exception("Offices round failed")
            if once:
                return
    finally:
        await feed.close()
