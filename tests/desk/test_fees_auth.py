import base64

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa

from desk.kalshi.auth import KalshiSigner, load_private_key
from desk.kalshi.fees import FeeSchedule, maker_fee, taker_fee


class TestFees:
    def test_published_example_100_contracts_at_50c(self):
        # Kalshi fee schedule example: 100 contracts at 50c -> $1.75 taker
        assert taker_fee(0.50, 100) == pytest.approx(1.75)
        assert maker_fee(0.50, 100) == pytest.approx(0.44)  # 0.4375 rounded up

    def test_rounds_up_to_the_cent(self):
        # 1 contract at 50c: 0.07 * 0.25 = 0.0175 -> 0.02
        assert taker_fee(0.50, 1) == pytest.approx(0.02)

    def test_fee_smallest_near_extremes(self):
        assert taker_fee(0.05, 100) < taker_fee(0.50, 100)
        assert taker_fee(0.95, 100) == taker_fee(0.05, 100)

    def test_no_fee_for_invalid(self):
        assert taker_fee(0, 10) == 0
        assert taker_fee(1, 10) == 0
        assert taker_fee(0.5, 0) == 0

    def test_series_schedule(self):
        plain = FeeSchedule.from_series({"fee_type": "quadratic", "fee_multiplier": 1})
        assert plain.maker(0.5, 100) == 0
        with_maker = FeeSchedule.from_series({"fee_type": "quadratic_with_maker_fees", "fee_multiplier": 0.5})
        assert with_maker.maker(0.5, 100) == pytest.approx(0.22)
        assert with_maker.taker(0.5, 100) == pytest.approx(0.88)  # 0.875 -> 0.88


class TestAuth:
    def test_rsa_pss_signature_verifies_and_ignores_query(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        signer = KalshiSigner("key-123", load_private_key(pem))
        h = signer.headers("get", "/trade-api/v2/portfolio/balance?x=1", timestamp_ms=1700000000000)
        assert h["KALSHI-ACCESS-KEY"] == "key-123"
        assert h["KALSHI-ACCESS-TIMESTAMP"] == "1700000000000"
        key.public_key().verify(
            base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"]),
            b"1700000000000GET/trade-api/v2/portfolio/balance",
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )

    def test_ed25519_signature_verifies(self):
        key = ed25519.Ed25519PrivateKey.generate()
        signer = KalshiSigner("k", key)
        h = signer.headers("POST", "/trade-api/v2/portfolio/events/orders", timestamp_ms=1)
        key.public_key().verify(base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"]),
                                b"1POST/trade-api/v2/portfolio/events/orders")

    def test_from_env_missing_returns_none(self, monkeypatch):
        monkeypatch.delenv("KALSHI_API_KEY_ID", raising=False)
        assert KalshiSigner.from_env() is None


def test_postgres_translation_escapes_percent():
    from desk.paper.ledger import _Postgres
    sql = _Postgres.translate("SELECT 1 FROM fills WHERE reason LIKE 'maker fill%' AND season = ?")
    assert sql == "SELECT 1 FROM fills WHERE reason LIKE 'maker fill%%' AND season = %s"
