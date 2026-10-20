"""
Phone notifications through Pushover (https://pushover.net), for the real-money book only:

  * the moment Live trading pauses, and why
  * a 9 PM summary of real profit or loss since the last one

Needs PUSHOVER_TOKEN (the "Kalshi Desk" application's API token) and PUSHOVER_USER
(your user key) where the bot runs; without them nothing is sent. Messages use
Pushover's small HTML subset, in the iPhone widget's terminal-green style.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

API = "https://api.pushover.net/1/messages.json"
DASHBOARD = "https://kalshi-desk-nu.vercel.app"
GREEN, RED, AMBER = "#3dff8a", "#ff4d5e", "#ffb000"  # the widget's colors


def configured() -> bool:
    return bool(os.getenv("PUSHOVER_TOKEN", "").strip() and os.getenv("PUSHOVER_USER", "").strip())


def send(title: str, message: str, priority: int = 0, sound: Optional[str] = None) -> bool:
    """One notification; never raises (a phone ping must not stop trading)."""
    if not configured():
        return False
    data = {"token": os.environ["PUSHOVER_TOKEN"].strip(), "user": os.environ["PUSHOVER_USER"].strip(),
            "title": title, "message": message, "html": 1, "priority": priority,
            "url": DASHBOARD, "url_title": "Open Kalshi Desk"}
    if sound:
        data["sound"] = sound
    try:
        r = httpx.post(API, data=data, timeout=8)
        if r.status_code != 200:
            logger.warning("Pushover said %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except httpx.HTTPError as e:
        logger.warning("Couldn't reach Pushover: %s", e)
        return False


def money(v: float) -> str:
    return f"${abs(v):,.2f}"


def paused(reason: str, by: str) -> bool:
    who = "the bot's safety check" if by == "bot" else by
    until = ("it restarts by itself at midnight" if "daily stop" in by
             else "you resume it on the dashboard")
    return send("⏸ Live trading paused",
                f'<font color="{AMBER}"><b>{reason}</b></font>\n'
                f"Paused by {who}. No new real bets until {until}; bets already placed still settle.",
                priority=1, sound="falling")


def daily(pnl: float, settled: int, won: int, leader: Optional[tuple[str, float]], pool: float,
          riding: float, open_bets: int, halted: Optional[str] = None) -> bool:
    if settled:
        title = f"{'▲ Up' if pnl >= 0 else '▼ Down'} {money(pnl)} today"
    else:
        title = "Quiet day: no bets settled"
    color = GREEN if pnl >= 0 else RED
    lines = [f'<font color="{color}"><b>{"+" if pnl >= 0 else "−"}{money(pnl)}</b></font> since 9 PM yesterday']
    if settled:
        s = f"{won} of {settled} bet{'' if settled == 1 else 's'} won"
        if leader and leader[1] > 0:
            s += f" · {leader[0]} led (+{money(leader[1])})"
        lines.append(s)
    s = f"Pool {money(pool)}"
    if open_bets:
        s += f" · {money(riding)} riding on {open_bets} bet{'' if open_bets == 1 else 's'}"
    lines.append(s)
    if halted:
        lines.append(f'<font color="{AMBER}">⏸ Live is paused: {halted}</font>')
    return send(title, "\n".join(lines), sound="cashregister" if settled and pnl > 0 else "pushover")
