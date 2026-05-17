"""Market regime filter — determines if shorts/longs are allowed."""

import logging
from dataclasses import dataclass
from typing import Optional

from scanner.binance_api import get_btc_klines_daily, get_all_24h_tickers
from config import cfg

log = logging.getLogger(__name__)


@dataclass
class Regime:
    btc_price: float
    btc_ema20: float
    btc_regime: str        # "bullish" | "bearish" | "neutral"
    shorts_allowed: bool
    longs_allowed: bool
    reason: str


def _ema(values: list[float], period: int) -> float:
    """Calculate EMA for a list of closing prices."""
    if not values:
        return 0.0
    k = 2 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1 - k)
    return ema


async def get_avg_alt_funding() -> float:
    """Average funding rate across top altcoins (USDT futures)."""
    tickers = await get_all_24h_tickers()
    # Take top 20 by volume, excluding BTC/ETH
    sorted_tickers = sorted(tickers, key=lambda t: float(t.get("quoteVolume", 0)), reverse=True)
    alt_symbols = [
        t["symbol"] for t in sorted_tickers
        if t["symbol"] not in ("BTCUSDT", "ETHUSDT")
    ][:20]

    from scanner.binance_api import get_funding_rate
    import asyncio

    rates = await asyncio.gather(*[get_funding_rate(s) for s in alt_symbols], return_exceptions=True)
    valid = [r for r in rates if isinstance(r, float)]
    return sum(valid) / len(valid) if valid else 0.0


async def assess_regime() -> Regime:
    """
    Assess current market regime from BTC price structure + alt funding.

    Blocked conditions for shorts:
    - BTC above 20D EMA AND accelerating (last 5d candles all green/up)
    - Broad alt funding strongly positive

    Blocked conditions for longs:
    - BTC in sharp downtrend (below 20D EMA, accelerating down)
    """
    klines = await get_btc_klines_daily(limit=30)
    closes = [float(k[4]) for k in klines]

    if len(closes) < 25:
        log.warning("Insufficient BTC klines for regime assessment")
        return Regime(
            btc_price=closes[-1] if closes else 0,
            btc_ema20=0,
            btc_regime="unknown",
            shorts_allowed=True,
            longs_allowed=True,
            reason="insufficient data",
        )

    btc_price = closes[-1]
    ema20 = _ema(closes[-20:], 20)

    # BTC momentum: slope of last 5 days
    recent_5 = closes[-5:]
    positive_days = sum(1 for i in range(1, len(recent_5)) if recent_5[i] > recent_5[i - 1])
    accelerating_up = positive_days >= 4
    accelerating_down = positive_days <= 1

    above_ema = btc_price > ema20

    # Alt funding
    avg_alt_funding = await get_avg_alt_funding()
    broad_funding_hot = avg_alt_funding > cfg.regime_alt_funding_threshold

    # Determine regime
    if above_ema and accelerating_up:
        btc_regime = "bullish"
        shorts_blocked = True
        longs_blocked = False
        reason = f"BTC above EMA20 ({ema20:.0f}) + accelerating up"
    elif not above_ema and accelerating_down:
        btc_regime = "bearish"
        shorts_blocked = False
        longs_blocked = True
        reason = f"BTC below EMA20 ({ema20:.0f}) + accelerating down"
    else:
        btc_regime = "neutral"
        shorts_blocked = False
        longs_blocked = False
        reason = f"BTC neutral vs EMA20 ({ema20:.0f})"

    if broad_funding_hot:
        shorts_blocked = True
        reason += f" | broad alt funding hot ({avg_alt_funding:.2f}%)"

    return Regime(
        btc_price=btc_price,
        btc_ema20=ema20,
        btc_regime=btc_regime,
        shorts_allowed=not shorts_blocked,
        longs_allowed=not longs_blocked,
        reason=reason,
    )
