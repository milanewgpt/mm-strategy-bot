"""Signal generation — combines classifier + mode checks into final signals."""

import logging
from dataclasses import dataclass
from typing import Optional

from classifier.phase import TokenData, Phase, classify_phase
from classifier.scorer import compute_structural_score
from classifier.regime import Regime
from strategy.mode_a import check_mode_a, ModeASignal
from strategy.mode_b import check_mode_b, ModeBSignal

log = logging.getLogger(__name__)


@dataclass
class Signal:
    symbol: str
    mode: str                  # LONG | SHORT
    confidence: float
    phase: Phase
    structural_score: float
    price: float
    funding_4h: float
    oi_growth_7d: float
    price_growth_7d: float
    taker_ratio: float
    exchange_concentration: Optional[float]
    float_pct: Optional[float]
    market_cap_usd: Optional[float]
    listing_age_days: Optional[int]
    btc_regime: str
    reasons: list[str]
    entry_low: float
    entry_high: float
    invalidation: float
    target_1: float
    target_2: float


def generate_signals(tokens: list[TokenData], regime: Regime) -> list[Signal]:
    """
    Run classifier + mode checks on all tokens.
    Returns signals that pass all conditions, sorted by confidence.
    """
    signals: list[Signal] = []

    for token in tokens:
        try:
            phase = classify_phase(token)
            score = compute_structural_score(token)

            # Skip uninteresting phases
            if phase in (Phase.ACCUMULATION, Phase.DEAD):
                continue

            # Try Mode A (Long)
            if regime.longs_allowed:
                sig_a = check_mode_a(token, phase)
                if sig_a.valid:
                    signals.append(Signal(
                        symbol=token.symbol,
                        mode="LONG",
                        confidence=sig_a.confidence,
                        phase=phase,
                        structural_score=score,
                        price=token.price,
                        funding_4h=token.funding_4h or 0,
                        oi_growth_7d=token.oi_growth_7d or 0,
                        price_growth_7d=token.price_growth_7d or 0,
                        taker_ratio=token.taker_ratio or 0.5,
                        exchange_concentration=token.exchange_concentration,
                        float_pct=token.float_pct,
                        market_cap_usd=token.market_cap_usd,
                        listing_age_days=None,
                        btc_regime=regime.btc_regime,
                        reasons=sig_a.reasons,
                        entry_low=sig_a.entry_low,
                        entry_high=sig_a.entry_high,
                        invalidation=sig_a.invalidation,
                        target_1=sig_a.target_1,
                        target_2=sig_a.target_2,
                    ))

            # Try Mode B (Short)
            if regime.shorts_allowed:
                sig_b = check_mode_b(token, phase)
                if sig_b.valid:
                    signals.append(Signal(
                        symbol=token.symbol,
                        mode="SHORT",
                        confidence=sig_b.confidence,
                        phase=phase,
                        structural_score=score,
                        price=token.price,
                        funding_4h=token.funding_4h or 0,
                        oi_growth_7d=token.oi_growth_7d or 0,
                        price_growth_7d=token.price_growth_7d or 0,
                        taker_ratio=token.taker_ratio or 0.5,
                        exchange_concentration=token.exchange_concentration,
                        float_pct=token.float_pct,
                        market_cap_usd=token.market_cap_usd,
                        listing_age_days=None,
                        btc_regime=regime.btc_regime,
                        reasons=sig_b.reasons,
                        entry_low=sig_b.entry_low,
                        entry_high=sig_b.entry_high,
                        invalidation=sig_b.invalidation,
                        target_1=sig_b.target_1,
                        target_2=sig_b.target_2,
                    ))

        except Exception as e:
            log.error(f"{token.symbol}: signal generation error — {e}")

    signals.sort(key=lambda s: s.confidence, reverse=True)
    return signals
