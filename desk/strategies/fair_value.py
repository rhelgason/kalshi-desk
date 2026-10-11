"""
Model-based crypto employees: bet when Kalshi's price disagrees with the math.

    fair_value   The Professor      plain volatility model, the baseline
    vol_arb      Vega Vinny         uses the market's own volatility; hunts strikes out of line with their neighbors
    sniper       The Sniper         last few minutes only; near-certain outcomes the market hasn't fully priced
    momentum     Momentum Mo        assumes recent moves keep going
    mean_revert  Rubber Band Randy  assumes recent moves snap back

For "BTC above $K at 10pm?" we know today's price and roughly how much bitcoin
tends to move, so we can estimate the true odds (see pricing.prob_above). If
the YES contract costs 30c but our model says 40%, buying it has positive
expected value. Unlike arbitrage, this can lose on any single bet; it only
wins on average, and only if the model is better than the market.

Known weak spots (why the defaults are cautious):
  - Our spot price approximates the official CF Benchmarks index.
  - Log-normal models underrate big jumps, so far-out strikes look "too
    expensive" to the model when they aren't. We skip prices near 0 or 1.
  - The market often knows things the model doesn't (news, order flow).
  - Volatility is the whole game. Deribit's implied vol is a 30-day forecast
    that includes weekends and big news days; over the next hour bitcoin
    usually moves far less. On the first live test (Oct 2026), implied vol was
    37%, the last 4 hours realized 9%, and Kalshi's prices implied ~12%. So for
    hour-scale contracts we lean on recent realized vol (implied_weight=0.1).
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Optional

from desk.kalshi.models import Side
from desk.strategies.base import AccountView, Leg, Persona, Snapshot, Strategy, TradeIntent
from desk.feeds.crypto import UnderlyingQuote, underlying_for_series
from desk.strategies.pricing import effective_years, kelly_fraction, prob_yes


class CryptoFairValue(Strategy):
    key = "fair_value"
    persona = Persona(
        "The Professor", "Quant", "🎓",
        "Prices every bitcoin contract with a formula and buys whatever looks cheap.",
    )

    def __init__(
        self,
        min_edge: float = 0.04,
        min_price: float = 0.08,
        max_price: float = 0.92,
        min_seconds: float = 180,
        max_seconds: float = 6 * 3600,
        kelly_mult: float = 0.25,
        max_bet: float = 25.0,
        implied_weight: float = 0.1,
        vol_multiplier: float = 1.0,
        momentum_weight: float = 0.0,
        momentum_window: int = 15,
        min_win_prob: float = 0.0,
        max_per_settlement: int = 1,
        market_weight: float = 0.0,
    ):
        self.min_edge = min_edge
        self.min_price = min_price
        self.max_price = max_price
        self.min_seconds = min_seconds
        self.max_seconds = max_seconds
        self.kelly_mult = kelly_mult
        self.max_bet = max_bet
        self.implied_weight = implied_weight
        self.vol_multiplier = vol_multiplier
        # +1 = expect the last `momentum_window` minutes' trend to continue at
        # the same pace; -1 = expect it to fully reverse; 0 = ignore it
        self.momentum_weight = momentum_weight
        self.momentum_window = momentum_window
        self.min_win_prob = min_win_prob
        # Bets on the same coin settling at the same moment all ride on one number,
        # so they win or lose together. One per settlement keeps each result an
        # independent data point (and avoids piling into a single outcome).
        self.max_per_settlement = max_per_settlement
        # Kalshi's prices are well calibrated, so blend toward them:
        # final = market_weight x market mid + (1 - market_weight) x model.
        # 0 trusts the formula completely; 0.8 means "the market is mostly right,
        # but I'll bet when my model disagrees a lot".
        self.market_weight = market_weight

    # Hooks subclasses override ------------------------------------------

    def prepare(self, snap: Snapshot) -> None:
        """Called once per snapshot before any market is priced."""

    def vol_for(self, market, snap: Snapshot, quote: UnderlyingQuote) -> Optional[float]:
        vol = quote.vol(self.implied_weight)
        return vol * self.vol_multiplier if vol else None

    def spot_for(self, quote: UnderlyingQuote, vol: float, secs: float) -> float:
        """Spot price, nudged by recent momentum if this employee believes in it."""
        if not self.momentum_weight:
            return quote.spot
        move = quote.momentum.get(self.momentum_window)
        if move is None:
            return quote.spot
        drift = self.momentum_weight * move * secs / (self.momentum_window * 60)
        # Never let a trend guess move the center more than one standard deviation
        sd = vol * math.sqrt(effective_years(secs))
        return quote.spot * math.exp(max(-sd, min(sd, drift)))

    # --------------------------------------------------------------------

    def model_prob(self, market, snap: Snapshot) -> Optional[float]:
        quote = snap.underlying_for(market)
        secs = market.seconds_to_close(snap.now)
        if not quote or secs is None:
            return None
        vol = self.vol_for(market, snap, quote)
        if not vol:
            return None
        p = prob_yes(market, self.spot_for(quote, vol, secs), vol, effective_years(secs))
        if p is None or not self.market_weight or market.mid is None:
            return p
        return self.market_weight * market.mid + (1 - self.market_weight) * p

    @staticmethod
    def settlement_key(market) -> tuple:
        return (underlying_for_series(market.series_ticker), market.close_time)

    def evaluate(self, snap: Snapshot, account: AccountView) -> list[TradeIntent]:
        self.prepare(snap)
        candidates = []
        held = account.open_tickers
        for m in snap.markets.values():
            if not m.is_tradeable or m.ticker in held:
                continue
            secs = m.seconds_to_close(snap.now)
            if secs is None or not (self.min_seconds <= secs <= self.max_seconds):
                continue
            q_yes = self.model_prob(m, snap)
            if q_yes is None or math.isnan(q_yes):
                continue

            fee = snap.fee_for(m)
            best = None
            for side, q in ((Side.YES, q_yes), (Side.NO, 1 - q_yes)):
                price = m.ask(side)
                if not (self.min_price <= price <= self.max_price) or q < self.min_win_prob:
                    continue
                edge = q - price - fee.taker_per_contract(price)
                if edge >= self.min_edge and (best is None or edge > best[2]):
                    best = (side, price, edge, q)
            if not best:
                continue

            side, price, edge, q = best
            all_in_price = price + fee.taker_per_contract(price)
            stake = min(self.max_bet, account.cash * self.kelly_mult * kelly_fraction(q, all_in_price))
            count = math.floor(stake / price)
            if count < 1:
                continue
            candidates.append((m, TradeIntent(
                strategy=self.key,
                legs=[Leg(m.ticker, side, price, count)],
                reason=f"model {q:.0%} vs price {price:.2f} ({side.value.upper()} {m.yes_sub_title})",
                model_prob=q,
                expected_edge=edge,
            )))

        # Best edge first, at most max_per_settlement per (coin, settle time),
        # counting positions already held
        used: dict[tuple, int] = {}
        for t in held:
            if t in snap.markets:
                k = self.settlement_key(snap.markets[t])
                used[k] = used.get(k, 0) + 1
        intents = []
        for m, intent in sorted(candidates, key=lambda c: c[1].expected_edge, reverse=True):
            k = self.settlement_key(m)
            if used.get(k, 0) >= self.max_per_settlement:
                continue
            used[k] = used.get(k, 0) + 1
            intents.append(intent)
        return intents


def implied_vol(market, spot: float, price: float, years: float,
                lo: float = 0.01, hi: float = 3.0) -> Optional[float]:
    """The volatility at which the model's probability equals `price` (bisection)."""
    f_lo, f_hi = prob_yes(market, spot, lo, years), prob_yes(market, spot, hi, years)
    if f_lo is None or f_hi is None or (f_lo - price) * (f_hi - price) > 0:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        f_mid = prob_yes(market, spot, mid, years)
        if (f_lo - price) * (f_mid - price) <= 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


class VegaVinny(CryptoFairValue):
    """
    Instead of guessing volatility, read it from the market itself: back out
    the volatility implied by each liquid "above $K" strike, take the median,
    and price every strike (and range bucket) at that settle time with it.
    Anything far off the market's own consensus is a candidate.
    """

    key = "vol_arb"
    persona = Persona(
        "Vega Vinny", "Volatility Trader", "📐",
        "Lets the market tell him how jumpy bitcoin is, then bets on the odd strike out.",
    )

    def __init__(self, min_edge: float = 0.04, min_price: float = 0.10, max_price: float = 0.90,
                 min_strikes: int = 2, max_spread: float = 0.03, calib_band: tuple = (0.07, 0.93), **kw):
        super().__init__(min_edge=min_edge, min_price=min_price, max_price=max_price, **kw)
        self.min_strikes = min_strikes
        self.max_spread = max_spread
        # Hourly ladders use $100 strikes, so only a few sit away from 0 and 1;
        # we read vol from anything in this band with a tight spread.
        self.calib_band = calib_band
        self.market_vols: dict[tuple, float] = {}

    @staticmethod
    def _key(m) -> tuple:
        return (underlying_for_series(m.series_ticker), m.close_time)

    def prepare(self, snap: Snapshot) -> None:
        samples: dict[tuple, list[float]] = defaultdict(list)
        for m in snap.markets.values():
            if m.strike_type not in ("greater", "greater_or_equal") or m.mid is None:
                continue
            if not (self.calib_band[0] <= m.mid <= self.calib_band[1]) or m.yes_ask - m.yes_bid > self.max_spread:
                continue
            quote, secs = snap.underlying_for(m), m.seconds_to_close(snap.now)
            if not quote or not secs or secs <= 0 or not m.floor_strike:
                continue
            if abs(math.log(quote.spot / m.floor_strike)) < 1e-4:
                continue  # right at the money, price says nothing about vol
            iv = implied_vol(m, quote.spot, m.mid, effective_years(secs))
            if iv:
                samples[self._key(m)].append(iv)
        self.market_vols = {k: statistics.median(v) for k, v in samples.items() if len(v) >= self.min_strikes}

    def vol_for(self, market, snap, quote):
        return self.market_vols.get(self._key(market))


class Sniper(CryptoFairValue):
    """
    Only shoots in the final minutes before settlement, when bitcoin is far
    enough from a strike that the outcome is nearly decided, but the contract
    still trades a few cents below $1. Assumes extra volatility to stay humble.
    """

    key = "sniper"
    persona = Persona(
        "The Sniper", "Closer", "🎯",
        "Waits all hour, then takes one shot in the last few minutes.",
    )

    def __init__(self, min_edge: float = 0.015, min_price: float = 0.80, max_price: float = 0.97,
                 min_seconds: float = 45, max_seconds: float = 600, min_win_prob: float = 0.95,
                 vol_multiplier: float = 1.5, max_bet: float = 50.0, **kw):
        super().__init__(min_edge=min_edge, min_price=min_price, max_price=max_price,
                         min_seconds=min_seconds, max_seconds=max_seconds, min_win_prob=min_win_prob,
                         vol_multiplier=vol_multiplier, max_bet=max_bet, **kw)


class MomentumMo(CryptoFairValue):
    key = "momentum"
    persona = Persona(
        "Momentum Mo", "Trend Surfer", "🏄",
        "If bitcoin's been climbing for 15 minutes, Mo bets it keeps climbing.",
    )

    def __init__(self, momentum_weight: float = 1.0, momentum_window: int = 15, **kw):
        super().__init__(momentum_weight=momentum_weight, momentum_window=momentum_window, **kw)


class RubberBandRandy(CryptoFairValue):
    key = "mean_revert"
    persona = Persona(
        "Rubber Band Randy", "Contrarian Quant", "🪀",
        "Every sudden move snaps back. Usually. Hopefully.",
    )

    def __init__(self, momentum_weight: float = -0.5, momentum_window: int = 5, **kw):
        super().__init__(momentum_weight=momentum_weight, momentum_window=momentum_window, **kw)
