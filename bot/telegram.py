"""Telegram bot — commands + notification sender."""

import asyncio
import logging
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes

from config import cfg
from bot.formatter import format_metrics
from paper.engine import get_open_trades
from paper.metrics import get_metrics
from db.database import get_conn

log = logging.getLogger(__name__)

# Injected from main.py to avoid circular imports
_scan_fn = None


def set_scan_callback(fn) -> None:
    global _scan_fn
    _scan_fn = fn


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 MM Strategy Bot\n\n"
        "Scans Binance Futures perpetuals for squeeze and unwind signals on low-float tokens.\n\n"
        "Commands:\n"
        "/status — open paper positions\n"
        "/metrics — performance stats\n"
        "/regime — current market regime\n"
        "/scan — trigger manual scan\n"
        "/help — all commands"
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📋 Available commands:\n\n"
        "/start — bot overview\n"
        "/status — open paper positions with entry prices\n"
        "/metrics — win rate, profit factor, PnL breakdown\n"
        "/regime — BTC EMA20 regime, longs/shorts status\n"
        "/scan — trigger a manual scan immediately\n"
        "/help — this message\n\n"
        "Scans run automatically every 60 min.\n"
        "Signals are sent when confidence ≥ 65%."
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    trades = get_open_trades()
    if not trades:
        await update.message.reply_text("No open paper positions.")
        return

    lines = [f"📋 Open positions: {len(trades)}"]
    for t in trades:
        pnl_str = ""
        lines.append(
            f"\n{'🟢' if t['direction'] == 'LONG' else '🔴'} {t['direction']} {t['symbol']}\n"
            f"  Entry: {t['entry_price']:.6g}\n"
            f"  Size: ${t['size_usd']:.0f}  Leverage: {t['leverage']}x\n"
            f"  Opened: {t['opened_at'][:16]} UTC"
        )
    await update.message.reply_text("\n".join(lines))


async def cmd_metrics(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(format_metrics())


async def cmd_regime(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM regime_log ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("No regime data yet. Wait for the first scan.")
        return

    row = dict(row)
    shorts = "✅ allowed" if row["shorts_allowed"] else "🚫 blocked"
    longs  = "✅ allowed" if row["longs_allowed"]  else "🚫 blocked"
    above  = "above" if row["btc_price"] > row["btc_ema20"] else "below"

    await update.message.reply_text(
        f"🌍 Market Regime\n\n"
        f"BTC price:  ${row['btc_price']:,.0f}\n"
        f"EMA20:      ${row['btc_ema20']:,.0f}  ({above} EMA)\n"
        f"Regime:     {row['btc_regime'].upper()}\n\n"
        f"Longs:   {longs}\n"
        f"Shorts:  {shorts}\n\n"
        f"Updated: {row['recorded_at'][:16]} UTC"
    )


async def cmd_scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if _scan_fn is None:
        await update.message.reply_text("Scan function not available.")
        return
    await update.message.reply_text("🔍 Manual scan started. Signals will appear if conditions are met...")
    asyncio.create_task(_scan_fn())


def build_app() -> Application:
    app = Application.builder().token(cfg.telegram_token).build()
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CommandHandler("status",  cmd_status))
    app.add_handler(CommandHandler("metrics", cmd_metrics))
    app.add_handler(CommandHandler("regime",  cmd_regime))
    app.add_handler(CommandHandler("scan",    cmd_scan))
    return app


async def send_message(text: str, bot: Bot) -> None:
    await bot.send_message(chat_id=cfg.telegram_chat_id, text=text)
