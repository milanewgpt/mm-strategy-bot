"""
MM Squeeze & Unwind Detection Strategy — main entry point.

Architecture:
- Telegram bot (PTB 20.x) runs polling in background
- APScheduler drives all scan/monitor jobs
- Initial jobs fire 10s after start so bot is ready to receive commands first
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
load_dotenv()

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from config import cfg
from db.database import init_db, get_conn
from scanner.universe import build_universe
from classifier.phase import TokenData
from classifier.regime import assess_regime
from scanner.binance_api import get_funding_trend, get_oi_history, get_klines
from strategy.signals import generate_signals
from strategy.mode_a import check_mode_a_exit
from strategy.mode_b import check_mode_b_exit
from paper.engine import open_paper_trade, close_paper_trade, get_open_trades
from bot.telegram import build_app, send_message, set_scan_callback
from bot.formatter import format_signal, format_trade_closed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("main")

_current_regime = None
_app: Application = None


async def run_regime_check() -> None:
    global _current_regime
    log.info("Regime check...")
    try:
        regime = await assess_regime()
        _current_regime = regime

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO regime_log (btc_price, btc_ema20, btc_regime, shorts_allowed, longs_allowed)
            VALUES (?, ?, ?, ?, ?)
        """, (regime.btc_price, regime.btc_ema20, regime.btc_regime,
              int(regime.shorts_allowed), int(regime.longs_allowed)))
        conn.commit()
        conn.close()

        log.info(
            f"Regime: {regime.btc_regime} | longs={'on' if regime.longs_allowed else 'OFF'} "
            f"shorts={'on' if regime.shorts_allowed else 'OFF'} | {regime.reason}"
        )
    except Exception as e:
        log.error(f"Regime check failed: {e}")


async def _enrich_token_data(raw: dict) -> TokenData:
    sym = raw["symbol"]

    funding_trend = None
    try:
        funding_trend = await get_funding_trend(sym)
    except Exception:
        pass

    oi_flattening = None
    try:
        oi_hist = await get_oi_history(sym, period="4h", limit=6)
        if len(oi_hist) >= 4:
            recent_avg = sum(float(h["sumOpenInterest"]) for h in oi_hist[-2:]) / 2
            prev_avg = sum(float(h["sumOpenInterest"]) for h in oi_hist[-4:-2]) / 2
            if prev_avg > 0:
                oi_flattening = (recent_avg - prev_avg) / prev_avg < 0.02
    except Exception:
        pass

    failed_breakout = None
    try:
        klines = await get_klines(sym, interval="4h", limit=42)
        if klines:
            highs = [float(k[2]) for k in klines]
            recent_peak = max(highs[-14:]) if len(highs) >= 14 else max(highs)
            current = float(klines[-1][4])
            if recent_peak > 0:
                failed_breakout = (recent_peak - current) / recent_peak > 0.05
    except Exception:
        pass

    return TokenData(
        symbol=sym,
        price=raw.get("price", 0),
        price_growth_7d=raw.get("price_growth_7d"),
        oi_growth_7d=raw.get("oi_growth_7d"),
        funding_4h=raw.get("funding_4h"),
        taker_ratio=raw.get("taker_ratio"),
        float_pct=raw.get("float_pct"),
        exchange_concentration=raw.get("exchange_concentration"),
        volume_24h_usd=raw.get("volume_24h_usd"),
        market_cap_usd=raw.get("market_cap_usd"),
        funding_trend=funding_trend,
        oi_flattening=oi_flattening,
        failed_breakout=failed_breakout,
    )


async def run_full_scan() -> None:
    global _current_regime
    if _current_regime is None:
        await run_regime_check()

    log.info("Starting full universe scan...")
    try:
        raw_universe = await build_universe()
    except Exception as e:
        log.error(f"Universe build failed: {e}")
        return

    log.info(f"Enriching {len(raw_universe)} tokens...")
    tokens = []
    for raw in raw_universe:
        try:
            td = await _enrich_token_data(raw)
            tokens.append(td)
        except Exception as e:
            log.warning(f"{raw.get('symbol')}: enrichment error — {e}")

    signals = generate_signals(tokens, _current_regime)
    log.info(f"Generated {len(signals)} signals")

    conn = get_conn()
    cur = conn.cursor()

    for signal in signals:
        cur.execute("""
            INSERT INTO signals (
                symbol, mode, confidence, phase, price, funding_4h,
                oi_growth_7d, price_growth_7d, taker_ratio, exchange_concentration,
                float_pct, market_cap_usd, listing_age_days, btc_regime,
                entry_low, entry_high, invalidation, target_1, target_2
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal.symbol, signal.mode, signal.confidence, signal.phase.value,
            signal.price, signal.funding_4h, signal.oi_growth_7d, signal.price_growth_7d,
            signal.taker_ratio, signal.exchange_concentration, signal.float_pct,
            signal.market_cap_usd, signal.listing_age_days, signal.btc_regime,
            signal.entry_low, signal.entry_high, signal.invalidation,
            signal.target_1, signal.target_2,
        ))
        signal_id = cur.lastrowid
        conn.commit()

        if signal.confidence >= 65:
            try:
                await send_message(format_signal(signal), _app.bot)
            except Exception as e:
                log.error(f"Failed to send signal for {signal.symbol}: {e}")

            trade_id = open_paper_trade(signal, signal_id)
            if trade_id:
                log.info(f"Paper trade opened: {signal.mode} {signal.symbol} id={trade_id}")

    conn.close()
    log.info("Scan complete.")


async def run_monitor() -> None:
    if _current_regime is None:
        return
    open_trades = get_open_trades()
    if not open_trades:
        return

    log.info(f"Monitoring {len(open_trades)} open positions...")

    for trade in open_trades:
        sym = trade["symbol"]
        try:
            from scanner.binance_api import get_funding_rate, get_taker_ratio, get_24h_ticker
            funding = await get_funding_rate(sym)
            taker = await get_taker_ratio(sym)
            ticker = await get_24h_ticker(sym)
            current_price = float(ticker["lastPrice"])
        except Exception as e:
            log.warning(f"{sym}: monitor fetch failed — {e}")
            continue

        token = TokenData(
            symbol=sym, price=current_price,
            price_growth_7d=None, oi_growth_7d=None,
            funding_4h=funding, taker_ratio=taker,
            float_pct=trade.get("float_pct"),
            exchange_concentration=trade.get("exchange_concentration"),
            volume_24h_usd=None, market_cap_usd=trade.get("market_cap_usd"),
        )

        exit_reason = (
            check_mode_a_exit(token, trade["entry_price"])
            if trade["direction"] == "LONG"
            else check_mode_b_exit(token, trade["entry_price"])
        )

        if exit_reason:
            result = close_paper_trade(trade["id"], current_price, exit_reason)
            if result:
                try:
                    await send_message(format_trade_closed(result), _app.bot)
                except Exception as e:
                    log.error(f"Failed to send close notification: {e}")


async def main() -> None:
    global _app

    init_db()
    log.info("Database initialized")

    _app = build_app()
    set_scan_callback(run_full_scan)

    await _app.bot.set_my_commands([
        ("start", "Bot overview"),
        ("status", "Open paper positions"),
        ("metrics", "Win rate, PnL stats"),
        ("regime", "BTC regime, longs/shorts status"),
        ("scan", "Trigger manual scan now"),
        ("help", "All commands"),
    ])

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(run_regime_check, "interval", seconds=cfg.regime_interval, id="regime")
    scheduler.add_job(run_full_scan, "interval", seconds=cfg.scan_interval, id="scan")
    scheduler.add_job(run_monitor, "interval", seconds=cfg.monitor_interval, id="monitor")

    # Initial jobs: fire 10s after start so bot polling is ready first
    now = datetime.now(timezone.utc)
    scheduler.add_job(run_regime_check, "date", run_date=now + timedelta(seconds=10), id="regime_init")
    scheduler.add_job(run_full_scan, "date", run_date=now + timedelta(seconds=15), id="scan_init")

    scheduler.start()

    async with _app:
        await _app.start()
        log.info("Bot started — polling...")
        await _app.updater.start_polling(drop_pending_updates=True)

        # Keep alive until SIGTERM
        try:
            while True:
                await asyncio.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            log.info("Shutting down...")
            scheduler.shutdown(wait=False)
            await _app.updater.stop()
            await _app.stop()


if __name__ == "__main__":
    asyncio.run(main())
