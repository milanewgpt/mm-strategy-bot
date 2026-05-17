"""Signal and metrics formatting for Telegram messages."""

from strategy.signals import Signal
from classifier.phase import Phase
from paper.metrics import get_metrics


MODE_EMOJI = {"LONG": "🟢", "SHORT": "🔴"}
PHASE_EMOJI = {
    Phase.EARLY_SQUEEZE: "⚡",
    Phase.ACTIVE_SQUEEZE: "🔥",
    Phase.LATE_SQUEEZE: "⚠️",
    Phase.EXHAUSTION: "💥",
    Phase.UNWIND: "📉",
    Phase.ACCUMULATION: "💤",
    Phase.DEAD: "🪦",
}


def format_signal(signal: Signal) -> str:
    mode_emoji = MODE_EMOJI.get(signal.mode, "❓")
    phase_emoji = PHASE_EMOJI.get(signal.phase, "")

    float_str = f"{signal.float_pct:.0f}%" if signal.float_pct else "unknown"
    conc_str = f"{signal.exchange_concentration:.0f}%" if signal.exchange_concentration else "unknown"
    mc_str = f"${signal.market_cap_usd / 1_000_000:.0f}M" if signal.market_cap_usd else "unknown"

    reasons_str = "\n".join(f"  • {r}" for r in signal.reasons)

    lines = [
        f"{'🚨 EXHAUSTION' if signal.phase == Phase.EXHAUSTION else '⚡ SQUEEZE'} SIGNAL",
        "",
        f"Token: {signal.symbol}",
        f"Mode: {mode_emoji} {signal.mode}",
        f"Phase: {phase_emoji} {signal.phase.value}",
        f"Confidence: {signal.confidence:.0f}%",
        f"Structural Score: {signal.structural_score:.0f}/100",
        "",
        f"Price: ${signal.price:.6g}",
        f"Funding: {signal.funding_4h:+.2f}% / 4h",
        f"OI 7D: {signal.oi_growth_7d:+.0f}%",
        f"Price 7D: {signal.price_growth_7d:+.0f}%",
        f"Taker ratio: {signal.taker_ratio:.2f}",
        f"Float: {float_str}",
        f"Exchange conc: {conc_str}",
        f"Market cap: {mc_str}",
        "",
        "Detected:",
        reasons_str,
        "",
        f"Entry: {signal.entry_low:.6g} — {signal.entry_high:.6g}",
        f"Invalidation: {signal.invalidation:.6g}",
        f"Targets: {signal.target_1:.6g} / {signal.target_2:.6g}",
        "",
        f"Market Regime: {signal.btc_regime.capitalize()}",
    ]
    return "\n".join(lines)


def format_trade_closed(result: dict) -> str:
    pnl = result["pnl_usd"]
    pnl_pct = result["pnl_pct"]
    emoji = "✅" if pnl > 0 else "❌"
    direction = result["direction"]
    return (
        f"{emoji} Paper trade closed\n"
        f"{direction} {result['symbol']}\n"
        f"Entry: {result['entry_price']:.6g} → Exit: {result['exit_price']:.6g}\n"
        f"PnL: {pnl:+.2f}$ ({pnl_pct:+.1f}%)\n"
        f"Reason: {result['reason']}"
    )


def format_metrics() -> str:
    m = get_metrics()
    if m.get("total_trades", 0) == 0:
        return "📊 No closed trades yet."

    return (
        f"📊 Paper Trading Metrics\n\n"
        f"Total trades: {m['total_trades']}\n"
        f"Win rate: {m['win_rate_pct']}%\n"
        f"Profit factor: {m['profit_factor']}\n"
        f"Total PnL: {m['total_pnl_usd']:+.2f}$\n\n"
        f"Longs: {m['long_trades']} trades, WR {m['long_win_rate_pct']}%\n"
        f"Shorts: {m['short_trades']} trades, WR {m['short_win_rate_pct']}%\n\n"
        f"Avg win: {m['avg_win_usd']:+.2f}$\n"
        f"Avg loss: {m['avg_loss_usd']:+.2f}$\n"
        f"Avg hold: {m['avg_hold_hours']:.1f}h"
    )
