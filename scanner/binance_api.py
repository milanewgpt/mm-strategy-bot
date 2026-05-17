"""Binance Futures public API — no API key required for market data."""

import httpx
import asyncio
from datetime import datetime, timezone
from typing import Optional

BASE = "https://fapi.binance.com"
SPOT_BASE = "https://api.binance.com"


async def get_futures_symbols() -> list[dict]:
    """All active USDT-margined futures symbols with basic info."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{BASE}/fapi/v1/exchangeInfo")
        r.raise_for_status()
        data = r.json()
    return [
        s for s in data["symbols"]
        if s["quoteAsset"] == "USDT" and s["status"] == "TRADING" and s["contractType"] == "PERPETUAL"
    ]


async def get_funding_rate(symbol: str) -> Optional[float]:
    """Current funding rate for a symbol (percentage, 4h period)."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{BASE}/fapi/v1/premiumIndex", params={"symbol": symbol})
        r.raise_for_status()
        data = r.json()
    return float(data["lastFundingRate"]) * 100  # convert to %


async def get_funding_history(symbol: str, limit: int = 50) -> list[dict]:
    """Historical funding rates. Returns list of {fundingTime, fundingRate}."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{BASE}/fapi/v1/fundingRate",
            params={"symbol": symbol, "limit": limit},
        )
        r.raise_for_status()
    return r.json()


async def get_open_interest(symbol: str) -> Optional[float]:
    """Current open interest in base asset."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{BASE}/fapi/v1/openInterest", params={"symbol": symbol})
        r.raise_for_status()
        data = r.json()
    return float(data["openInterest"])


async def get_oi_history(symbol: str, period: str = "4h", limit: int = 42) -> list[dict]:
    """OI history. period: 5m/15m/30m/1h/2h/4h/6h/12h/1d."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{BASE}/futures/data/openInterestHist",
            params={"symbol": symbol, "period": period, "limit": limit},
        )
        r.raise_for_status()
    return r.json()


async def get_klines(symbol: str, interval: str = "4h", limit: int = 50) -> list[list]:
    """OHLCV klines from Binance Futures."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{BASE}/fapi/v1/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        r.raise_for_status()
    return r.json()


async def get_taker_ratio(symbol: str, period: str = "4h", limit: int = 10) -> Optional[float]:
    """Long/short taker ratio. Returns avg ratio over limit periods."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{BASE}/futures/data/takerlongshortRatio",
            params={"symbol": symbol, "period": period, "limit": limit},
        )
        r.raise_for_status()
        data = r.json()
    if not data:
        return None
    # buySellRatio = longVol / shortVol; > 1 means more buy takers
    ratios = [float(d["buySellRatio"]) for d in data]
    avg = sum(ratios) / len(ratios)
    # normalize to 0-1: ratio/(1+ratio)
    return avg / (1 + avg)


async def get_24h_ticker(symbol: str) -> Optional[dict]:
    """24h price change stats."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{BASE}/fapi/v1/ticker/24hr", params={"symbol": symbol})
        r.raise_for_status()
    return r.json()


async def get_all_24h_tickers() -> list[dict]:
    """All futures 24h tickers at once (efficient)."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{BASE}/fapi/v1/ticker/24hr")
        r.raise_for_status()
    return r.json()


async def get_btc_klines_daily(limit: int = 30) -> list[list]:
    """BTC daily klines for regime calculation."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{BASE}/fapi/v1/klines",
            params={"symbol": "BTCUSDT", "interval": "1d", "limit": limit},
        )
        r.raise_for_status()
    return r.json()


async def get_price_change_7d(symbol: str) -> Optional[float]:
    """Approximate 7d price change % from klines."""
    klines = await get_klines(symbol, interval="1d", limit=8)
    if len(klines) < 2:
        return None
    open_7d = float(klines[0][1])  # open of 7 days ago
    close_now = float(klines[-1][4])  # last close
    if open_7d == 0:
        return None
    return (close_now - open_7d) / open_7d * 100


async def get_funding_trend(symbol: str) -> str:
    """Returns 'improving', 'neutral', 'worsening' based on recent funding history."""
    history = await get_funding_history(symbol, limit=12)
    if len(history) < 3:
        return "neutral"
    rates = [float(h["fundingRate"]) * 100 for h in history[-6:]]
    first_half = sum(rates[:3]) / 3
    second_half = sum(rates[3:]) / 3
    delta = second_half - first_half
    if delta < -0.05:
        return "improving"  # funding getting less positive / more negative
    if delta > 0.05:
        return "worsening"
    return "neutral"
