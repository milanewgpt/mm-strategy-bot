"""Paper trading engine — simulates trade execution with slippage + fees."""

import logging
from datetime import datetime, timezone
from typing import Optional

from config import cfg
from db.database import get_conn
from strategy.signals import Signal

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def open_paper_trade(signal: Signal, signal_id: int) -> Optional[int]:
    """
    Open a paper trade from a signal.
    Returns trade_id or None if position limit reached.
    """
    conn = get_conn()
    cur = conn.cursor()

    # Check concurrent position limit
    cur.execute("SELECT COUNT(*) FROM paper_trades WHERE status = 'open'")
    open_count = cur.fetchone()[0]
    if open_count >= cfg.paper_max_concurrent:
        log.info(f"Position limit ({cfg.paper_max_concurrent}) reached, skipping {signal.symbol}")
        conn.close()
        return None

    # Check if already in this symbol
    cur.execute("SELECT id FROM paper_trades WHERE symbol = ? AND status = 'open'", (signal.symbol,))
    if cur.fetchone():
        log.info(f"Already in {signal.symbol}, skipping")
        conn.close()
        return None

    # Calculate position size
    position_usd = cfg.paper_virtual_equity * (cfg.paper_position_size_pct / 100)
    leveraged_usd = position_usd * cfg.paper_max_leverage

    # Entry price with slippage
    slippage = cfg.paper_slippage_pct / 100
    if signal.mode == "LONG":
        entry_price = signal.price * (1 + slippage)
    else:
        entry_price = signal.price * (1 - slippage)

    # Entry fee
    fee_cost = leveraged_usd * (cfg.paper_fee_pct / 100)

    cur.execute("""
        INSERT INTO paper_trades (
            signal_id, symbol, direction, entry_price, size_usd, leverage,
            status, funding_at_entry, oi_percentile, float_pct, listing_age_days,
            market_cap_usd, btc_regime, exchange_concentration, taker_ratio, opened_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        signal_id,
        signal.symbol,
        signal.mode,
        entry_price,
        leveraged_usd,
        cfg.paper_max_leverage,
        signal.funding_4h,
        None,  # oi_percentile — future enrichment
        signal.float_pct,
        signal.listing_age_days,
        signal.market_cap_usd,
        signal.btc_regime,
        signal.exchange_concentration,
        signal.taker_ratio,
        _now(),
    ))

    trade_id = cur.lastrowid
    conn.commit()
    conn.close()

    log.info(
        f"Paper trade opened: {signal.mode} {signal.symbol} @ {entry_price:.6f} "
        f"size=${leveraged_usd:.0f} fee=${fee_cost:.2f}"
    )
    return trade_id


def close_paper_trade(trade_id: int, current_price: float, reason: str) -> Optional[dict]:
    """
    Close an open paper trade at current_price.
    Returns trade summary dict.
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM paper_trades WHERE id = ? AND status = 'open'", (trade_id,))
    trade = cur.fetchone()
    if not trade:
        conn.close()
        return None

    trade = dict(trade)
    entry_price = trade["entry_price"]
    size_usd = trade["size_usd"]
    direction = trade["direction"]

    # Exit price with slippage
    slippage = cfg.paper_slippage_pct / 100
    if direction == "LONG":
        exit_price = current_price * (1 - slippage)
        pnl_pct = (exit_price - entry_price) / entry_price * 100
    else:
        exit_price = current_price * (1 + slippage)
        pnl_pct = (entry_price - exit_price) / entry_price * 100

    pnl_usd = size_usd * (pnl_pct / 100)
    fee_cost = size_usd * (cfg.paper_fee_pct / 100)
    pnl_usd -= fee_cost  # exit fee

    cur.execute("""
        UPDATE paper_trades
        SET status = 'closed', exit_price = ?, exit_reason = ?,
            pnl_usd = ?, pnl_pct = ?, closed_at = ?
        WHERE id = ?
    """, (exit_price, reason, pnl_usd, pnl_pct, _now(), trade_id))
    conn.commit()
    conn.close()

    log.info(
        f"Paper trade closed: {direction} {trade['symbol']} "
        f"@ {exit_price:.6f} PnL={pnl_usd:+.2f}$ ({pnl_pct:+.1f}%) — {reason}"
    )
    return {
        "trade_id": trade_id,
        "symbol": trade["symbol"],
        "direction": direction,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "pnl_usd": pnl_usd,
        "pnl_pct": pnl_pct,
        "reason": reason,
    }


def get_open_trades() -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM paper_trades WHERE status = 'open'")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
