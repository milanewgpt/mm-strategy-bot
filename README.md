# MM Squeeze & Unwind Detection Strategy

Event-driven paper trading bot for Binance Futures.  
Detects MM-driven squeeze and exhaustion phases on low-float tokens.

---

## What it does

Scans Binance Futures perpetuals every hour. Classifies each token into one of 7 phases based on OI growth, funding rate, price structure, and taker ratio. Generates LONG or SHORT signals when conditions align. Paper trades with slippage + fees simulation. Sends all signals to Telegram.

**It does NOT trade blindly on momentum.** It tries to identify *which phase* a move is in before acting.

---

## Strategy Logic

### Phases

```
ACCUMULATION → EARLY_SQUEEZE → ACTIVE_SQUEEZE → LATE_SQUEEZE → EXHAUSTION → UNWIND → DEAD
```

| Phase | Signal |
|---|---|
| EARLY_SQUEEZE | Mode A — Long entry |
| EXHAUSTION | Mode B — Short entry |
| UNWIND | Mode B — Short hold (OI↑ + Price↓ = trapped longs) |

### Mode A — Squeeze Continuation LONG

All conditions required:

| Condition | Threshold |
|---|---|
| Float | < 25% |
| OI growth 7d | > +50% |
| Price growth 7d | > +20% |
| Funding 4h | Neutral or negative |
| Funding trend | Improving or neutral |
| Exchange concentration | < 65% |

### Mode B — Exhaustion / Unwind SHORT

Entry only after exhaustion confirmation. **SHORT is blocked if price is still making strong higher highs.**

| Condition | Threshold |
|---|---|
| Float | < 25% |
| OI growth 7d | > +100% |
| Price growth 7d | > +50% |
| Funding 4h | > +0.5% |
| Taker ratio | > 0.65 |
| OI behavior | Flattening or reversing |

Strongest signal: **OI↑ while Price↓** — trapped longs, distribution, MM unwind.

### Regime Filter

| BTC condition | Effect |
|---|---|
| Above EMA20 + accelerating | Shorts blocked |
| Below EMA20 + accelerating down | Longs blocked |
| Broad alt funding > 0.3% | Shorts blocked |

---

## Structural Score

Each token gets a composite score 0–100:

| Component | Weight |
|---|---|
| OI growth | 25% |
| Funding extremity | 20% |
| Float tightness | 20% |
| Vol/OI abnormality | 10% |
| Exchange dispersion | 10% |
| Taker activity | 15% |

---

## Signal Format

```
🚨 EXHAUSTION SIGNAL

Token: MYXUSDT
Mode: 🔴 SHORT
Phase: 💥 EXHAUSTION
Confidence: 78%
Structural Score: 59/100

Price: $1.42
Funding: +0.82% / 4h
OI 7D: +143%
Price 7D: +61%
Taker ratio: 0.68
Float: 18%
Exchange conc: 45%
Market cap: $200M

Detected:
  • Float 18.0%
  • OI 7d +143%
  • Funding +0.82% (overheated)
  • Failed breakout detected
  • OI↑ + Price↓ = trapped longs

Entry: 1.39 — 1.45
Invalidation: 1.63
Targets: 1.18 / 0.96

Market Regime: Neutral
```

---

## Paper Trading

| Parameter | Value |
|---|---|
| Virtual equity | $10,000 |
| Position size | 2% per trade |
| Max leverage | 3x |
| Max concurrent | 3 |
| Slippage | 0.1% |
| Fees | 0.05% taker |

Per-trade fields saved: funding at entry, OI percentile, float, listing age, market cap, BTC regime, exchange concentration, taker ratio.

---

## Data Sources

| Source | Data | Access |
|---|---|---|
| Binance Futures public API | OI, funding, taker ratio, klines, listings | Free, no key |
| CoinGecko free | Float proxy, market cap, exchange concentration | Free |

---

## Architecture

```
mm-strategy-bot/
├── main.py               # APScheduler + Telegram bot entry point
├── config.py             # All thresholds and parameters
├── scanner/
│   ├── binance_api.py    # Binance Futures public API
│   ├── coingecko.py      # Float, MC, exchange concentration
│   └── universe.py       # Two-stage universe builder
├── classifier/
│   ├── phase.py          # 7-phase classification
│   ├── scorer.py         # Structural score
│   └── regime.py         # BTC regime filter
├── strategy/
│   ├── mode_a.py         # Long entry + exit logic
│   ├── mode_b.py         # Short entry + exit logic
│   └── signals.py        # Signal generation
├── paper/
│   ├── engine.py         # Paper trade execution
│   └── metrics.py        # Win rate, profit factor, breakdown
├── bot/
│   ├── telegram.py       # Bot commands
│   └── formatter.py      # Signal formatting
└── db/
    └── database.py       # SQLite: signals, trades, regime log
```

**Scan loop:**
- Every 60 min — full universe scan
- Every 15 min — regime check
- Every 5 min — monitor open positions for exit

---

## Setup

```bash
git clone https://github.com/milanewgpt/mm-strategy-bot.git
cd mm-strategy-bot
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
# fill in TELEGRAM_TOKEN and TELEGRAM_CHAT_ID
venv/bin/python main.py
```

**VPS / systemd:**
```bash
sudo cp mm-strategy.service /etc/systemd/system/
sudo systemctl enable --now mm-strategy
journalctl -u mm-strategy -f
```

---

## Telegram Commands

| Command | Action |
|---|---|
| `/start` | Bot info |
| `/regime` | Current market regime (BTC EMA20, shorts/longs status) |
| `/status` | Open paper positions |
| `/metrics` | Performance stats (win rate, profit factor, long vs short) |
| `/scan` | Trigger manual scan |
| `/help` | All commands |

---

## Expected Performance (Paper)

| Metric | Realistic range |
|---|---|
| Win rate | 40–55% |
| Profit factor | 1.3–1.8 |
| Avg hold | 3–18 days |

This is an event-driven strategy. Equity curve will not be smooth. Long dry spells between signals are normal.

---

## Risks

- **Early shorting** — biggest killer. Blocked unless phase is EXHAUSTION or UNWIND.
- **Narrative override** — AI/meme narratives can break the model. Regime filter partially handles this.
- **Fake OI** — some exchanges inflate OI. Cross-check with CoinGecko exchange concentration.
- **CoinGecko rate limits** — free tier (~15 req/min). Scanner handles this with delays.
