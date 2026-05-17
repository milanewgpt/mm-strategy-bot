"""Mode A — Squeeze Continuation LONG entry and exit logic."""

from typing import Optional
from dataclasses import dataclass
from classifier.phase import TokenData, Phase
from config import cfg


@dataclass
class ModeASignal:
    valid: bool
    confidence: float  # 0–100
    reasons: list[str]
    failed_conditions: list[str]
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None
    invalidation: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None


def check_mode_a(token: TokenData, phase: Phase) -> ModeASignal:
    """
    Check Mode A (Long) entry conditions.
    All primary conditions must pass.
    """
    reasons = []
    failed = []

    # Phase must be EARLY_SQUEEZE
    if phase not in (Phase.EARLY_SQUEEZE,):
        return ModeASignal(False, 0, [], [f"Phase {phase.value} not suitable for long"])

    float_pct = token.float_pct or 100

    # --- Primary conditions (all required) ---
    p1 = float_pct < cfg.mode_a_max_float_pct
    if p1:
        reasons.append(f"Float {float_pct:.1f}% < {cfg.mode_a_max_float_pct}%")
    else:
        failed.append(f"Float {float_pct:.1f}% ≥ {cfg.mode_a_max_float_pct}%")

    oi_growth = token.oi_growth_7d or 0
    p2 = oi_growth >= cfg.mode_a_min_oi_growth_7d
    if p2:
        reasons.append(f"OI 7d +{oi_growth:.0f}%")
    else:
        failed.append(f"OI 7d +{oi_growth:.0f}% < +{cfg.mode_a_min_oi_growth_7d}%")

    price_growth = token.price_growth_7d or 0
    p3 = price_growth >= cfg.mode_a_min_price_growth_7d
    if p3:
        reasons.append(f"Price 7d +{price_growth:.0f}%")
    else:
        failed.append(f"Price 7d +{price_growth:.0f}% < +{cfg.mode_a_min_price_growth_7d}%")

    funding = token.funding_4h or 0
    p4 = funding <= cfg.mode_a_max_funding_pct
    if p4:
        reasons.append(f"Funding {funding:+.2f}% (neutral/neg)")
    else:
        failed.append(f"Funding {funding:+.2f}% overheated (> {cfg.mode_a_max_funding_pct}%)")

    funding_trend = token.funding_trend or "neutral"
    p5 = funding_trend in ("improving", "neutral")
    if p5:
        reasons.append(f"Funding trend: {funding_trend}")
    else:
        failed.append(f"Funding trend: {funding_trend}")

    conc = token.exchange_concentration or 50
    p6 = conc <= cfg.mode_a_max_exchange_concentration
    if p6:
        reasons.append(f"Exchange concentration {conc:.0f}%")
    else:
        failed.append(f"Exchange concentration {conc:.0f}% > {cfg.mode_a_max_exchange_concentration}%")

    all_pass = p1 and p2 and p3 and p4 and p5 and p6
    if not all_pass:
        return ModeASignal(False, 0, reasons, failed)

    # Confidence score (bonus conditions)
    confidence = 60.0
    if oi_growth > 80:
        confidence += 10
    if price_growth > 40:
        confidence += 10
    if funding < 0:
        confidence += 10  # negative funding = squeeze fuel
    if (token.taker_ratio or 0.5) < 0.45:
        confidence += 5   # sell-side takers still present
    if conc < 40:
        confidence += 5

    confidence = min(confidence, 95)

    # Entry zone: current price ± 2%
    price = token.price
    entry_low = round(price * 0.98, 6)
    entry_high = round(price * 1.02, 6)
    invalidation = round(price * 0.88, 6)   # -12% invalidation
    target_1 = round(price * 1.20, 6)        # +20%
    target_2 = round(price * 1.40, 6)        # +40%

    return ModeASignal(
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


def check_mode_a_exit(token: TokenData, entry_price: float) -> Optional[str]:
    """
    Check exit conditions for an open long position.
    Returns exit reason string or None.
    """
    funding = token.funding_4h or 0

    if funding >= cfg.exit_a_funding_full:
        return f"FULL_EXIT: funding {funding:+.2f}% ≥ {cfg.exit_a_funding_full}%"

    if funding >= cfg.exit_a_funding_partial:
        return f"PARTIAL_EXIT_50: funding {funding:+.2f}% ≥ {cfg.exit_a_funding_partial}%"

    taker = token.taker_ratio or 0.5
    if taker > 0.70:
        return f"PARTIAL_EXIT_50: taker ratio {taker:.2f} > 0.70 (excessive buy pressure)"

    price = token.price
    price_change_from_entry = (price - entry_price) / entry_price * 100
    if price_change_from_entry < -12:
        return f"FULL_EXIT: price hit invalidation ({price_change_from_entry:.1f}% from entry)"

    return None
