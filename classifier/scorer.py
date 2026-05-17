"""Structural score calculator — 0 to 100 composite score."""

from typing import Optional
from classifier.phase import TokenData


def compute_structural_score(token: TokenData) -> float:
    """
    Weighted composite score 0–100.

    Components:
    - OI growth (25%)
    - Funding extremity (20%)
    - Float tightness (20%)
    - Vol/OI abnormality (10%)
    - Exchange dispersion (10%)
    - Wallet activity proxy (15%) — approximated from taker ratio
    """
    score = 0.0

    # 1. OI growth (25pts) — higher = more interesting
    oi = token.oi_growth_7d or 0.0
    oi_score = min(oi / 150.0, 1.0) * 25  # 150%+ OI = max score
    score += oi_score

    # 2. Funding extremity (20pts) — extreme in either direction is interesting
    funding = abs(token.funding_4h or 0.0)
    funding_score = min(funding / 1.0, 1.0) * 20  # 1%+ = max score
    score += funding_score

    # 3. Float tightness (20pts) — lower float = higher score
    float_pct = token.float_pct
    if float_pct is not None:
        float_score = max(0, (25 - float_pct) / 25) * 20  # <25% float → score
    else:
        float_score = 10  # unknown → neutral
    score += float_score

    # 4. Vol/OI abnormality (10pts) — high volume relative to market cap
    vol = token.volume_24h_usd or 0
    mc = token.market_cap_usd or 1
    vol_ratio = vol / mc if mc > 0 else 0
    vol_score = min(vol_ratio / 0.5, 1.0) * 10  # vol > 50% of MC = max
    score += vol_score

    # 5. Exchange dispersion (10pts) — lower concentration = better (less manipulation)
    conc = token.exchange_concentration
    if conc is not None:
        disp_score = max(0, (65 - conc) / 65) * 10  # <65% = some score
    else:
        disp_score = 5  # unknown → neutral
    score += disp_score

    # 6. Taker/wallet activity proxy (15pts)
    taker = token.taker_ratio or 0.5
    # Both extreme buy (>0.65) and extreme sell (<0.35) taker ratio is interesting
    taker_extremity = abs(taker - 0.5) * 2  # normalize 0→0, 0.5→1
    taker_score = taker_extremity * 15
    score += taker_score

    return round(score, 1)
