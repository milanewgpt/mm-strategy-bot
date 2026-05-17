"""Phase classification engine — assigns one of 7 states to a token."""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class Phase(str, Enum):
    ACCUMULATION = "ACCUMULATION"
    EARLY_SQUEEZE = "EARLY_SQUEEZE"
    ACTIVE_SQUEEZE = "ACTIVE_SQUEEZE"
    LATE_SQUEEZE = "LATE_SQUEEZE"
    EXHAUSTION = "EXHAUSTION"
    UNWIND = "UNWIND"
    DEAD = "DEAD"


@dataclass
class TokenData:
    symbol: str
    price: float
    price_growth_7d: Optional[float]   # %
    oi_growth_7d: Optional[float]       # %
    funding_4h: Optional[float]         # % per 4h period
    taker_ratio: Optional[float]        # 0–1
    float_pct: Optional[float]          # %
    exchange_concentration: Optional[float]  # % on top exchange
    volume_24h_usd: Optional[float]
    market_cap_usd: Optional[float]

    # Optional enrichment
    funding_trend: Optional[str] = None     # improving | neutral | worsening
    oi_flattening: Optional[bool] = None    # OI growth slowing last 2 periods
    failed_breakout: Optional[bool] = None  # price tried higher high, failed


def classify_phase(token: TokenData) -> Phase:
    """
    Classify token into one of 7 phases based on OI, funding, price structure.

    Decision tree:
    1. Dead: no meaningful activity
    2. Accumulation: low OI growth, low funding, low price movement
    3. Early squeeze: moderate OI growth, funding neutral/neg, price up
    4. Active squeeze: strong OI + price growth, funding heating up
    5. Late squeeze: very high OI growth, funding high, price still up
    6. Exhaustion: OI slowing/flattening while price stalls or reverses
    7. Unwind: OI↑ + Price↓ (trapped longs being liquidated)
    """
    oi = token.oi_growth_7d or 0.0
    price = token.price_growth_7d or 0.0
    funding = token.funding_4h or 0.0
    taker = token.taker_ratio or 0.5

    # --- DEAD ---
    if abs(price) < 5 and abs(oi) < 10:
        return Phase.DEAD

    # --- UNWIND (strongest signal) ---
    # OI rising while price falling = trapped longs being liquidated
    if oi > 20 and price < -5:
        return Phase.UNWIND

    # --- EXHAUSTION ---
    # High OI + high funding + OI starting to flatten + price stalling
    exhaustion_score = 0
    if oi > 80:
        exhaustion_score += 2
    if funding > 0.4:
        exhaustion_score += 2
    if token.oi_flattening:
        exhaustion_score += 2
    if token.failed_breakout:
        exhaustion_score += 2
    if taker > 0.65:
        exhaustion_score += 1
    if price < oi * 0.3 and oi > 60:  # OI outpacing price → late stage
        exhaustion_score += 1
    if exhaustion_score >= 5:
        return Phase.EXHAUSTION

    # --- LATE SQUEEZE ---
    if oi > 80 and price > 40 and funding > 0.3:
        return Phase.LATE_SQUEEZE

    # --- ACTIVE SQUEEZE ---
    if oi > 40 and price > 15 and funding > 0.1:
        return Phase.ACTIVE_SQUEEZE

    # --- EARLY SQUEEZE ---
    if oi > 20 and price > 10 and funding <= 0.15:
        return Phase.EARLY_SQUEEZE

    # --- ACCUMULATION ---
    return Phase.ACCUMULATION
