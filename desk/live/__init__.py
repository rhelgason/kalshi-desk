"""
Real money on Kalshi: the live broker, its safety guard, and reconciliation.

Off unless desk.yaml says `trading: live` AND the host sets
KALSHI_LIVE_TRADING=yes AND a Kalshi API key is configured (see guard.py).
"""

from __future__ import annotations

from desk.config import DeskConfig
from desk.kalshi.auth import KalshiSigner
from desk.kalshi.client import KalshiClient
from desk.live.guard import ENV_SWITCH, Guard, env_allows_live


class LiveSetupError(RuntimeError):
    """Live trading was asked for but isn't safely set up: nothing will trade."""


def live_client(cfg: DeskConfig) -> KalshiClient:
    """A Kalshi client allowed to place orders, or LiveSetupError saying what's missing."""
    if not env_allows_live():
        raise LiveSetupError(f"the config says trading: live, but {ENV_SWITCH}=yes isn't set on this machine")
    signer = KalshiSigner.from_env()
    if signer is None:
        raise LiveSetupError("no Kalshi API key: set KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY(_PATH)")
    return KalshiClient(env=cfg.env, signer=signer, allow_trading=True, requests_per_second=cfg.requests_per_second)


def make_live_broker(cfg: DeskConfig, ledger, accounts: dict, client: KalshiClient):
    from desk.live.broker import LiveBroker

    if not env_allows_live():
        raise LiveSetupError(f"{ENV_SWITCH}=yes isn't set on this machine")
    if not (client.signer and client.allow_trading):
        raise LiveSetupError("the Kalshi client has no API key or isn't allowed to trade (use desk.live.live_client)")
    return LiveBroker(ledger, accounts, client, Guard(ledger, cfg.live))


__all__ = ["Guard", "LiveSetupError", "env_allows_live", "live_client", "make_live_broker"]
