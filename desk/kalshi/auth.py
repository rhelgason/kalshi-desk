"""
Kalshi API key request signing.

Every authenticated request carries three headers:
    KALSHI-ACCESS-KEY        your key ID
    KALSHI-ACCESS-TIMESTAMP  current time in milliseconds
    KALSHI-ACCESS-SIGNATURE  base64(sign(timestamp + METHOD + path))

The signed path is the full path from the API root (e.g.
"/trade-api/v2/portfolio/balance") without the query string. Kalshi accepts
RSA keys (signed with RSA-PSS / SHA-256) and Ed25519 keys.

Docs: https://docs.kalshi.com/getting_started/api_keys
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Optional, Union

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa

PrivateKey = Union[rsa.RSAPrivateKey, ed25519.Ed25519PrivateKey]


def load_private_key(pem: Union[str, bytes]) -> PrivateKey:
    data = pem.encode() if isinstance(pem, str) else pem
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, (rsa.RSAPrivateKey, ed25519.Ed25519PrivateKey)):
        raise ValueError("Kalshi keys must be RSA or Ed25519")
    return key


def sign_message(key: PrivateKey, message: str) -> str:
    raw = message.encode()
    if isinstance(key, ed25519.Ed25519PrivateKey):
        sig = key.sign(raw)
    else:
        sig = key.sign(
            raw,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
    return base64.b64encode(sig).decode()


class KalshiSigner:
    def __init__(self, key_id: str, private_key: PrivateKey):
        self.key_id = key_id
        self.private_key = private_key

    def headers(self, method: str, path: str, timestamp_ms: Optional[int] = None) -> dict[str, str]:
        ts = str(timestamp_ms if timestamp_ms is not None else int(time.time() * 1000))
        path_only = path.split("?", 1)[0]
        signature = sign_message(self.private_key, ts + method.upper() + path_only)
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": signature,
        }

    @classmethod
    def from_env(cls) -> Optional["KalshiSigner"]:
        """
        Build a signer from environment variables, or return None.

            KALSHI_API_KEY_ID        the key ID shown in Kalshi's API settings
            KALSHI_PRIVATE_KEY_PATH  path to the downloaded .pem / .key file
            (or KALSHI_PRIVATE_KEY   the PEM contents directly)
        """
        key_id = os.getenv("KALSHI_API_KEY_ID")
        if not key_id:
            return None
        pem: Optional[bytes] = None
        path = os.getenv("KALSHI_PRIVATE_KEY_PATH")
        if path:
            pem = Path(path).expanduser().read_bytes()
        elif os.getenv("KALSHI_PRIVATE_KEY"):
            pem = os.environ["KALSHI_PRIVATE_KEY"].encode()
        if pem is None:
            return None
        return cls(key_id, load_private_key(pem))
