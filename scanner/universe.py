"""Universe builder — finds qualifying tokens for MM strategy scanning."""

import asyncio
import logging
from typing import Optional

from scanner.binance_api import (
    get_futures_symbols,
    get_all_24h_tickers,
    get_oi_history,
    get_price_change_7d,
    get_funding_rate,
    get_taker_ratio,
)
from scanner.coingecko import get_market_data, get_exchange_concentration
from config import cfg

log = logging.getLogger(__name__)

# Max symbols to scan per cycle — keeps CoinGecko calls manageable
MAX_CANDIDATES = 80


async def _binance_enrich(sym: str, volume_24h: float) -> Optional[dict]:
    """Binance-only enrichment — fast, no rate limits."""
    try:
        oi_hist, price_7d, funding, taker = await asyncio.gather(
            get_oi_history(sym, period="4h", limit=42),
            get_price_change_7d(sym),
            get_funding_rate(sym),
            get_taker_ratio(sym),
            return_exceptions=True,
        )
    except Exception as e:
        log.warning(f"{sym}: Binance enrichment failed — {e}")
        return None

    oi_growth_7d: Optional[float] = None
    if isinstance(oi_hist, list) and len(oi_hist) >= 2:
        oi_start = float(oi_hist[0]["sumOpenInterest"])
        oi_end = float(oi_hist[-1]["sumOpenInterest"])
        if oi_start > 0:
            oi_growth_7d = (oi_end - oi_start) / oi_start * 100

    return {
        "oi_growth_7d": oi_growth_7d,
        "price_growth_7d": price_7d if not isinstance(price_7d, Exception) else None,
        "funding_4h": funding if not isinstance(funding, Exception) else None,
        "taker_ratio": taker if not isinstance(taker, Exception) else None,
        "volume_24h_usd": volume_24h,
    }


def _is_interesting(d: dict) -> bool:
    """Quick filter: only pass tokens with abnormal OI or funding — reduces CoinGecko calls."""
    oi = d.get("oi_growth_7d") or 0
    funding = abs(d.get("funding_4h") or 0)
    price = d.get("price_growth_7d") or 0
    # Must have at least one interesting signal
    return oi > 30 or funding > 0.3 or price > 15


async def build_universe() -> list[dict]:
    """
    Two-stage pipeline:
    1. Binance scan (fast, all symbols) — filter by volume + interesting signals
    2. CoinGecko enrich (slow) — only for interesting candidates (max 40)
    """
    log.info("Building universe...")

    symbols_info = await get_futures_symbols()
    all_tickers = await get_all_24h_tickers()
    ticker_map = {t["symbol"]: t for t in all_tickers}

    # Stage 1: volume pre-filter, keep only USDT perpetuals
    volume_candidates = []
    for s in symbols_info:
        sym = s["symbol"]
        if not sym.endswith("USDT"):
            continue
        ticker = ticker_map.get(sym)
        if not ticker:
            continue
        vol = float(ticker.get("quoteVolume", 0))
        if vol >= cfg.min_daily_volume_usd:
            volume_candidates.append((sym, ticker, vol))

    # Sort by volume descending, cap at MAX_CANDIDATES
    volume_candidates.sort(key=lambda x: x[2], reverse=True)
    volume_candidates = volume_candidates[:MAX_CANDIDATES]
    log.info(f"Volume filter: {len(volume_candidates)} candidates")

    # Stage 1b: Binance enrich in parallel batches (no rate limit concern)
    binance_results: list[dict] = []
    batch_size = 10
    for i in range(0, len(volume_candidates), batch_size):
        batch = volume_candidates[i:i + batch_size]
        tasks = [_binance_enrich(sym, vol) for sym, _, vol in batch]
        batch_data = await asyncio.gather(*tasks, return_exceptions=True)
        for j, data in enumerate(batch_data):
            if isinstance(data, dict):
                sym, ticker, vol = batch[j]
                data["symbol"] = sym
                data["price"] = float(ticker.get("lastPrice", 0))
                data["price_change_24h_pct"] = float(ticker.get("priceChangePercent", 0))
                binance_results.append(data)

    # Stage 2: filter interesting tokens before CoinGecko
    interesting = [d for d in binance_results if _is_interesting(d)]
    interesting = interesting[:40]  # hard cap: 40 × ~4 CoinGecko req = 160 req ≈ 5-6 min
    log.info(f"Interesting tokens (pre-CoinGecko): {len(interesting)}")

    # Stage 2b: CoinGecko enrich — sequential to respect rate limit
    results = []
    for d in interesting:
        sym = d["symbol"]
        try:
            market = await get_market_data(sym)
            d["market_cap_usd"] = market.get("market_cap_usd")
            d["float_pct"] = market.get("float_pct")

            await asyncio.sleep(4.0)  # CoinGecko free: ~15 req/min safe
            exchange_conc = await get_exchange_concentration(sym)
            d["exchange_concentration"] = exchange_conc
            await asyncio.sleep(4.0)
        except Exception as e:
            log.warning(f"{sym}: CoinGecko failed — {e}")
            d["market_cap_usd"] = None
            d["float_pct"] = None
            d["exchange_concentration"] = None

        mc = d.get("market_cap_usd")
        if mc is not None and mc < cfg.min_market_cap_usd:
            continue
        results.append(d)

    log.info(f"Universe built: {len(results)} tokens")
    return results
