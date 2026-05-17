"""Mode B — Exhaustion / Unwind SHORT entry and exit logic."""

from typing import Optional
from dataclasses import dataclass
from classifier.phase import TokenData, Phase
from config import cfg


@dataclass
class ModeBSignal:
    valid: bool
    confidence: float  # 0–100
    reasons: list[str]
    failed_conditions: list[str]
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None
    invalidation: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None


def check_mode_b(token: TokenData, phase: Phase) -> ModeBSignal:
    """
    Check Mode B (Short) entry conditions.

    CRITICAL: SHORT is FORBIDDEN if price still making higher highs
    and OI still accelerating. Need exhaustion confirmation.
    """
    reasons = []
    failed = []

    # Phase must be EXHAUSTION or UNWIND
    if phase not in (Phase.EXHAUSTION, Phase.UNWIND):
        return ModeBSignal(False, 0, [], [f"Phase {phase.value} — not exhaustion yet, no short"])

    float_pct = token.float_pct or 100

    # --- Primary conditions (all required) ---
    p1 = float_pct < cfg.mode_b_max_float_pct
    if p1:
        reasons.append(f"Float {float_pct:.1f}%")
    else:
        failed.append(f"Float {float_pct:.1f}% ≥ {cfg.mode_b_max_float_pct}% (not low-float)")

    oi_growth = token.oi_growth_7d or 0
    p2 = oi_growth >= cfg.mode_b_min_oi_growth_7d
    if p2:
        reasons.append(f"OI 7d +{oi_growth:.0f}%")
    else:
        failed.append(f"OI 7d +{oi_growth:.0f}% < +{cfg.mode_b_min_oi_growth_7d}% required")

    price_growth = token.price_growth_7d or 0
    p3 = price_growth >= cfg.mode_b_min_price_growth_7d
    if p3:
        reasons.append(f"Price 7d +{price_growth:.0f}%")
    else:
        failed.append(f"Price 7d +{price_growth:.0f}% < +{cfg.mode_b_min_price_growth_7d}%")

    funding = token.funding_4h or 0
    p4 = funding >= cfg.mode_b_min_funding_pct
    if p4:
        reasons.append(f"Funding {funding:+.2f}% (overheated)")
    else:
        failed.append(f"Funding {funding:+.2f}% < {cfg.mode_b_min_funding_pct}% (not hot enough)")

    taker = token.taker_ratio or 0
    p5 = taker >= cfg.mode_b_min_taker_ratio
    if p5:
        reasons.append(f"Taker ratio {taker:.2f} (elevated)")
    else:
        failed.append(f"Taker ratio {taker:.2f} < {cfg.mode_b_min_taker_ratio}")

    # OI must be slowing or flattening (not accelerating)
    oi_flat = token.oi_flattening
    p6 = oi_flat is True or oi_flat is None  # None = unknown, allow with penalty
    if oi_flat:
        reasons.append("OI flattening (distribution)")
    elif oi_flat is None:
        reasons.append("OI trend unknown")
    else:
        failed.append("OI still accelerating — no short yet")

    # Failed breakout is strongest confirmation
    has_failed_breakout = token.failed_breakout or False
    if has_failed_breakout:
        reasons.append("Failed breakout detected")

    # CRITICAL block: if price still making strong higher highs, no short
    price_growth_strong = price_growth > 80 and not (token.oi_flattening)
    if price_growth_strong:
        failed.append("Price still in strong uptrend — no short")
        return ModeBSignal(False, 0, reasons, failed)

    all_pass = p1 and p2 and p3 and p4 and p5 and p6
    if not all_pass:
        return ModeBSignal(False, 0, reasons, failed)

    # Confidence calculation
    confidence = 55.0

    # Strongest signal: OI↑ + Price↓
    if phase == Phase.UNWIND:
        confidence += 20
        reasons.append("OI↑ + Price↓ = trapped longs (strongest signal)")

    if has_failed_breakout:
        confidence += 10

    if oi_flat:
        confidence += 5

    if funding > 0.8:
        confidence += 5

    conc = token.exchange_concentration or 50
    if conc <= cfg.mode_b_max_exchange_concentration:
        confidence += 3

    confidence = min(confidence, 95)

    # Entry zone
    price = token.price
    entry_low = round(price * 0.98, 6)
    entry_high = round(price * 1.02, 6)
    invalidation = round(price * 1.15, 6)    # +15% invalidation (short)
    target_1 = round(price * 0.83, 6)        # -17%
    target_2 = round(price * 0.67, 6)        # -33%

    return ModeBSignal(
        valid=True,
        confidence=round(confidence, 1),
        reasons=reasons,
        failed_conditions=[],
        entry_low=entry_low,
        entry_high=entry_high,
        invalidation=invalidation,
        target_1=target_1,
        target_2=target_2,
    )


def check_mode_b_exit(token: TokenData, entry_price: float) -> Optional[str]:
    """Exit conditions for an open short."""
    funding = token.funding_4h or 0
    price = token.price
    price_change_from_entry = (entry_price - price) / entry_price * 100  # positive = profitable short

    # Exit if price moved against us significantly
    if price_change_from_entry < -15:
        return f"FULL_EXIT: price hit invalidation ({-price_change_from_entry:.1f}% against short)"

    # Funding normalizing = squeeze might restart
    if funding < 0.1:
        return f"FULL_EXIT: funding normalized ({funding:+.2f}%), unwind may be over"

    # Profit target
    if price_change_from_entry >= 17:
        return f"PARTIAL_EXIT_50: target 1 reached (+{price_change_from_entry:.1f}%)"

    if price_change_from_entry >= 33:
        return f"FULL_EXIT: target 2 reached (+{price_change_from_entry:.1f}%)"

    return None
