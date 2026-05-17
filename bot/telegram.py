"""Telegram bot — commands + notification sender."""

import logging
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes

from config import cfg
from bot.formatter import format_metrics
from paper.engine import get_open_trades
from paper.metrics import get_metrics
from db.database import get_conn

log = logging.getLogger(__name__)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "MM Strategy Bot active.\n"
        "Scanning for squeeze/unwind signals on Binance Futures.\n\n"
        "/status — open positions\n"
        "/metrics — paper trading stats\n"
        "/scan — trigger manual scan\n"
        "/help — all commands"
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Available commands:\n\n"
        "/start — bot info\n"
        "/status — open paper positions\n"
        "/metrics — performance statistics\n"
        "/scan — trigger manual scan now\n"
        "/regime — current market regime\n"
        "/help — this message"
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    trades = get_open_trades()
    if not trades:
        await update.message.reply_text("No open paper positions.")
        return

    lines = [f"📋 Open positions ({len(trades)}):"]
    for t in trades:
        lines.append(
            f"\n{t['direction']} {t['symbol']}\n"
            f"  Entry: {t['entry_price']:.6g}\n"
            f"  Size: ${t['size_usd']:.0f} ({t['leverage']}x)\n"
            f"  Opened: {t['opened_at'][:16]}"
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
        await update.message.reply_text("No regime data yet. Wait for first scan.")
        return

    row = dict(row)
    shorts = "✅" if row["shorts_allowed"] else "🚫"
    longs = "✅" if row["longs_allowed"] else "🚫"
    await update.message.reply_text(
        f"🌍 Market Regime\n\n"
        f"BTC: ${row['btc_price']:,.0f}\n"
        f"EMA20: ${row['btc_ema20']:,.0f}\n"
        f"Regime: {row['btc_regime']}\n\n"
        f"Longs allowed: {longs}\n"
        f"Shorts allowed: {shorts}\n\n"
        f"Updated: {row['recorded_at'][:16]}"
    )


async def cmd_scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Manual scan triggered. Results will appear as signals...")
    # The scan loop picks this up via a shared flag
    ctx.bot_data["manual_scan"] = True


def build_app() -> Application:
    app = Application.builder().token(cfg.telegram_token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("metrics", cmd_metrics))
    app.add_handler(CommandHandler("regime", cmd_regime))
    app.add_handler(CommandHandler("scan", cmd_scan))
    return app


async def send_message(text: str, bot: Bot) -> None:
    await bot.send_message(chat_id=cfg.telegram_chat_id, text=text)
