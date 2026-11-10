"""Friends' offices (desk/offices.py): their own books, the owner's playbook, and no elbowing the family."""

import base64
import json
import os
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from desk import hr
from desk.config import DeskConfig
from desk.kalshi.models import Side
from desk.offices import open_box, schema_of, sync_playbook
from desk.paper.ledger import Ledger
from desk.runner import Desk
from desk.strategies import LongshotFade
from desk.strategies.base import Leg, TradeIntent
from tests.desk.conftest import make_market


def lock(pem: bytes, public) -> str:
    """What web/lib/vault.ts does in the browser's place: AES-256-GCM, the AES key wrapped with RSA-OAEP-SHA256."""
    aes, iv = os.urandom(32), os.urandom(12)
    wrapped = public.encrypt(aes, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    data = AESGCM(aes).encrypt(iv, pem, None)
    return json.dumps({"v": 1, "key": base64.b64encode(wrapped).decode(), "iv": base64.b64encode(iv).decode(),
                       "data": base64.b64encode(data).decode()})


def test_a_locked_kalshi_key_opens_only_with_the_servers_key():
    server = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    box = lock(b"-----BEGIN PRIVATE KEY-----\nfriend\n-----END PRIVATE KEY-----\n", server.public_key())
    assert open_box(box, server).startswith(b"-----BEGIN PRIVATE KEY-----")
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(ValueError):
        open_box(box, other)


def test_office_names_cant_reach_other_books():
    assert schema_of("sam") == "office_sam"
    for bad in ("real", "x", "Sam", "sam; drop", "a_b", ""):
        if bad == "real":
            assert schema_of(bad) == "office_real"  # never the owner's own schema
            continue
        with pytest.raises(ValueError):
            schema_of(bad)


def test_offices_follow_the_owners_playbook_but_keep_their_own_reviews():
    real, office = Ledger(":memory:"), Ledger(":memory:")
    strategies = {"maker_btc": {}, "maker_eth": {}, "dart_monkey": {"enabled": False}, "hourly_btc": {"enabled": False}}
    policy = hr.load_policy(real)
    policy.update(season=8, last_review="2026-11-05T00:00:00+00:00", hired=["hourly_btc"])
    policy["pool"]["bet_pct"] = 0.04
    hr.save_policy(real, policy)
    for k, status in (("maker_btc", "active"), ("maker_eth", "fired"), ("dart_monkey", "active"), ("hourly_btc", "active")):
        rec = hr.EmployeeRecord(k, status=status, level=3, params={"odds_margin": 0.01} if k == "maker_btc" else {})
        real.upsert_employee(rec.to_row())
    mine = hr.load_policy(office)
    mine.update(season=1, last_review="2026-11-09T00:00:00+00:00")
    hr.save_policy(office, mine)

    assert sync_playbook(real, office, strategies)
    got = hr.load_policy(office)
    assert got["pool"]["bet_pct"] == 0.04 and got["hired"] == ["hourly_btc"]
    assert got["season"] == 1 and got["last_review"].startswith("2026-11-09")  # the office's own
    roster = {r["key"]: hr.EmployeeRecord.from_row(r) for r in office.employee_rows()}
    assert set(roster) == {"maker_btc", "maker_eth", "hourly_btc"}  # not the yardstick left off real money
    assert roster["maker_btc"].params == {"odds_margin": 0.01}
    assert roster["maker_btc"].level != 3  # levels are earned in the office's own reviews
    assert roster["maker_eth"].status == "fired"  # the owner's firing holds everywhere
    assert not sync_playbook(real, office, strategies)  # nothing new

    rec = hr.EmployeeRecord.from_row(next(r for r in real.employee_rows() if r["key"] == "maker_eth"))
    rec.status = "active"
    real.upsert_employee(rec.to_row())
    sync_playbook(real, office, strategies)
    assert next(r for r in office.employee_rows() if r["key"] == "maker_eth")["status"] == "active"


def _desk():
    cfg = DeskConfig(crypto_series=[], broad_scan=False, use_database_url=False)
    return Desk(cfg, None, [LongshotFade()], Ledger(":memory:"))


def _bid(price, count=10.0):
    return TradeIntent("longshot_fade", [Leg("T-1", Side.NO, price, count)], "bid", post_only=True)


def test_a_friend_joins_the_familys_bid_instead_of_topping_it():
    desk = _desk()
    live = make_market("T-1", yes_bid=0.04, yes_ask=0.07)  # NO's best bid 0.93 (the family's), ask 0.96
    assert desk.join_family(_bid(0.94), live).legs[0].limit_price == 0.94  # no family: unchanged (the owner)
    desk.family = {("T-1", "no"): 0.93}
    joined = desk.join_family(_bid(0.94), live)
    assert joined.legs[0].limit_price == 0.93 and joined.legs[0].count == pytest.approx(10.1, abs=0.01)
    desk.family = {("T-1", "no"): 0.92}  # someone outside the family bid over us: compete as usual
    assert desk.join_family(_bid(0.94), live).legs[0].limit_price == 0.94


async def test_a_friends_staff_decide_on_the_owners_clock():
    from desk.strategies.base import Snapshot

    desk = _desk()
    seen = []
    desk.strategies[0].evaluate = lambda snap, view: seen.append(snap.now) or []
    snap = Snapshot.build(desk.started_at, [], [])
    await desk.run_strategies(snap)
    assert seen[-1] == snap.now  # the owner's own books: no lag
    desk.lag = timedelta(seconds=40)
    await desk.run_strategies(snap)
    assert seen[-1] == snap.now - timedelta(seconds=40)
