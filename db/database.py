import sqlite3
import os
from config import cfg


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(cfg.db_path), exist_ok=True)
    conn = sqlite3.connect(cfg.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS tokens (
            symbol          TEXT PRIMARY KEY,
            market_cap_usd  REAL,
            daily_volume_usd REAL,
            float_pct       REAL,
            listing_age_days INTEGER,
            phase           TEXT,
            structural_score REAL,
            last_updated    TEXT
        );

        CREATE TABLE IF NOT EXISTS signals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            mode            TEXT NOT NULL,   -- LONG | SHORT
            confidence      REAL,
            phase           TEXT,
            price           REAL,
            funding_4h      REAL,
            oi_growth_7d    REAL,
            price_growth_7d REAL,
            taker_ratio     REAL,
            exchange_concentration REAL,
            float_pct       REAL,
            market_cap_usd  REAL,
            listing_age_days INTEGER,
            btc_regime      TEXT,
            narrative       TEXT,
            entry_low       REAL,
            entry_high      REAL,
            invalidation    REAL,
            target_1        REAL,
            target_2        REAL,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS paper_trades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id       INTEGER REFERENCES signals(id),
            symbol          TEXT NOT NULL,
            direction       TEXT NOT NULL,   -- LONG | SHORT
            entry_price     REAL,
            size_usd        REAL,
            leverage        REAL,
            status          TEXT DEFAULT 'open',  -- open | closed
            exit_price      REAL,
            exit_reason     TEXT,
            pnl_usd         REAL,
            pnl_pct         REAL,
            funding_at_entry REAL,
            oi_percentile   REAL,
            float_pct       REAL,
            listing_age_days INTEGER,
            market_cap_usd  REAL,
            btc_regime      TEXT,
            exchange_concentration REAL,
            taker_ratio     REAL,
            opened_at       TEXT DEFAULT (datetime('now')),
            closed_at       TEXT
        );

        CREATE TABLE IF NOT EXISTS regime_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            btc_price   REAL,
            btc_ema20   REAL,
            btc_regime  TEXT,
            shorts_allowed INTEGER,
            longs_allowed  INTEGER,
            recorded_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()
