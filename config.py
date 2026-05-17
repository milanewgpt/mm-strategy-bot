import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # Telegram
    telegram_token: str = field(default_factory=lambda: os.environ.get("TELEGRAM_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.environ.get("TELEGRAM_CHAT_ID", ""))

    # Binance
    binance_api_key: str = field(default_factory=lambda: os.environ.get("BINANCE_API_KEY", ""))
    binance_api_secret: str = field(default_factory=lambda: os.environ.get("BINANCE_API_SECRET", ""))

    # Scanner intervals (seconds)
    scan_interval: int = 3600       # full scan every hour
    regime_interval: int = 900      # regime check every 15 min
    monitor_interval: int = 300     # open positions check every 5 min

    # Universe filters
    min_market_cap_usd: float = 20_000_000
    min_daily_volume_usd: float = 10_000_000

    # Mode A — Long thresholds
    mode_a_max_float_pct: float = 25.0
    mode_a_min_oi_growth_7d: float = 50.0
    mode_a_min_price_growth_7d: float = 20.0
    mode_a_max_funding_pct: float = 0.1        # funding must be below this (neutral/neg)
    mode_a_max_exchange_concentration: float = 65.0

    # Mode B — Short thresholds
    mode_b_max_float_pct: float = 25.0
    mode_b_min_oi_growth_7d: float = 100.0
    mode_b_min_price_growth_7d: float = 50.0
    mode_b_min_funding_pct: float = 0.5        # funding must be above this
    mode_b_min_taker_ratio: float = 0.65
    mode_b_max_exchange_concentration: float = 65.0

    # Mode A exit signals
    exit_a_funding_partial: float = 0.5        # close 50% at this funding
    exit_a_funding_full: float = 1.0           # close all at this funding

    # Regime filter
    regime_btc_ema_period: int = 20            # BTC 20D EMA
    regime_alt_funding_threshold: float = 0.3  # broad alt funding threshold

    # Paper trading
    paper_virtual_equity: float = 10_000.0
    paper_position_size_pct: float = 2.0
    paper_max_leverage: float = 3.0
    paper_max_concurrent: int = 3
    paper_slippage_pct: float = 0.1
    paper_fee_pct: float = 0.05                # taker fee

    # DB
    db_path: str = field(default_factory=lambda: os.environ.get("DB_PATH", "/home/gpt/mm-strategy-bot/data/mm_strategy.db"))


cfg = Config()
