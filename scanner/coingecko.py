"""CoinGecko free tier — market cap, exchange concentration, float proxy."""

import httpx
import asyncio
from typing import Optional

BASE = "https://api.coingecko.com/api/v3"

# CoinGecko symbol → id mapping cache
_symbol_cache: dict[str, str] = {}


async def _coin_id_by_symbol(symbol: str) -> Optional[str]:
    """Resolve USDT futures symbol (e.g. MYXUSDT) to CoinGecko coin id."""
    base = symbol.replace("USDT", "").lower()
    if base in _symbol_cache:
        return _symbol_cache[base]
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{BASE}/search", params={"query": base})
        r.raise_for_status()
        data = r.json()
    coins = data.get("coins", [])
    for coin in coins:
        if coin["symbol"].lower() == base:
            _symbol_cache[base] = coin["id"]
            return coin["id"]
    return None


async def get_market_data(symbol: str) -> dict:
    """Returns market_cap, total_volume, circulating_supply, total_supply, float_pct."""
    coin_id = await _coin_id_by_symbol(symbol)
    if not coin_id:
        return {}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE}/coins/{coin_id}",
            params={"localization": "false", "tickers": "false", "community_data": "false", "developer_data": "false"},
        )
        r.raise_for_status()
        data = r.json()

    market = data.get("market_data", {})
    circulating = market.get("circulating_supply") or 0
    total = market.get("total_supply") or 0
    float_pct = (circulating / total * 100) if total > 0 else None

    return {
        "market_cap_usd": market.get("market_cap", {}).get("usd"),
        "daily_volume_usd": market.get("total_volume", {}).get("usd"),
        "circulating_supply": circulating,
        "total_supply": total,
        "float_pct": float_pct,
        "coin_id": coin_id,
    }


async def get_exchange_concentration(symbol: str, top_n: int = 1) -> Optional[float]:
    """
    Returns % of 24h volume on the single largest exchange.
    High concentration = one exchange dominates = squeeze risk.
    """
    coin_id = await _coin_id_by_symbol(symbol)
    if not coin_id:
        return None
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{BASE}/coins/{coin_id}/tickers", params={"include_exchange_logo": "false"})
        r.raise_for_status()
        data = r.json()

    tickers = data.get("tickers", [])
    if not tickers:
        return None

    # only USD/USDT/USDC pairs
    usdt_tickers = [
        t for t in tickers
        if t.get("target") in ("USDT", "USDC", "USD")
    ]
    if not usdt_tickers:
        usdt_tickers = tickers

    total_vol = sum(float(t.get("converted_volume", {}).get("usd", 0) or 0) for t in usdt_tickers)
    if total_vol == 0:
        return None

    # volume by exchange
    exchange_vols: dict[str, float] = {}
    for t in usdt_tickers:
        exch = t.get("market", {}).get("name", "unknown")
        vol = float(t.get("converted_volume", {}).get("usd", 0) or 0)
        exchange_vols[exch] = exchange_vols.get(exch, 0) + vol

    top_vols = sorted(exchange_vols.values(), reverse=True)[:top_n]
    concentration = sum(top_vols) / total_vol * 100
    return concentration
