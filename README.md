# ARIA — Advanced Retail Intelligence & Analytics

> **Autonomous multi-agent trading and risk analytics system** — live in production, built from scratch as an MSc capstone at De Montfort University.

[![Live System](https://img.shields.io/badge/status-live-brightgreen)](https://web-production-548c0.up.railway.app/terminal)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue)](https://postgresql.org)

**[Live Terminal →](https://web-production-548c0.up.railway.app/terminal)**

---

## What is ARIA?

ARIA is a production-grade autonomous trading intelligence system that makes real-time decisions across 6 assets (BTC, ETH, AAPL, NVDA, TSLA, GLD) using a multi-layer agent architecture. It is not a backtest or a demo — it runs 24/7 on dedicated infrastructure, processes live market data, and manages its own risk.

The system was built to answer a research question: *can a domain-bounded autonomous agent achieve institutional-grade decision quality without human intervention?*

**Core academic finding:** Multi-asset XGBoost+RF ensemble achieves **78.3% accuracy** vs **41.8%** for single-asset models — a 36.5 percentage point improvement from cross-asset feature learning.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    ARIA 7-Layer Stack                        │
├─────────────────────────────────────────────────────────────┤
│  Layer 7 │ World Model        │ WHY markets move             │
│  Layer 6 │ Learning Loop      │ Weekly self-retraining       │
│  Layer 5 │ Meta-Controller    │ Capital allocation (BOOST/KILL)│
│  Layer 4 │ Stress Report      │ EVT + GAN black swan         │
│  Layer 3 │ Guardian           │ 50% portfolio protection     │
│  Layer 2 │ Kill Switch        │ Emergency stop               │
│  Layer 1 │ Position Sizer     │ Kelly Criterion (5 multipliers)│
├─────────────────────────────────────────────────────────────┤
│          │ Agent Loop v5      │ Core decision engine         │
│          │ Anomaly Detector   │ Safety spine                 │
│          │ Model Inference    │ XGBoost+RF ensemble          │
└─────────────────────────────────────────────────────────────┘
```

**Infrastructure:**
- **Hetzner CPX32** (65.108.217.183) — PostgreSQL `aria_db`, all agents, collectors, 9 systemd services
- **Railway Hobby** — FastAPI frontend, auto-deploy from GitHub master, never sleeps
- **32 PostgreSQL tables** — price_data (37M+ BTC ticks), closed_trades, pattern_library, world_state, system_health, and more

---

## Key Technical Components

### Signal Generation — Model + Rules Fusion

```python
# Three-way fusion: XGBoost+RF ensemble × rule-based regime logic × world state
if model_dir == rules_dir:
    final_conf = min(0.92, (model_conf * 0.6 + rules_conf * 0.4) + 0.05)  # Agreement boost
elif model_dir != rules_dir:
    return 'HOLD'  # Disagreement = skip trade
```

### 27-Feature Vector
Built in real-time from `price_data` table:

| Category | Features |
|----------|----------|
| Price/Trend | RSI, MACD, MACD histogram, SMA 20/50, momentum 5/10 |
| Volatility | ATR%, realized vol 1h/24h, Bollinger width, Z-score |
| Sentiment | Sentiment score, trend, Fear/Greed index, news volatility |
| Macro/Regime | DXY change, VIX, world state encoded, liquidity regime |
| Market Structure | VPIN (order flow), volume ratio/trend, ADX proxy |

### Kelly Criterion — 5 Multipliers
```
position_size = kelly × regime_mult × fg_mult × vol_mult × vel_mult × world_mult
```
Where `world_mult` is derived live from the world model narrative and liquidity state. Currently running at **0.24x** in CRISIS regime with FRAGILE liquidity.

### Safety Spine — Anomaly Detector
Monitors all feeds every 60 seconds. Writes `system_mode` to DB:
- `NORMAL` (score 100) — full trading
- `DEGRADED` (score 60-99) — reduced trading, warning logged
- `SAFE` (score <60) — no new trades, exits only

Agent loop reads `system_mode` before every decision cycle.

### Risk Engine — Problem C
- **EVT/GPD tail risk** — Peaks-Over-Threshold with bootstrap CIs (BTC 29.5% CI width)
- **GAN stress scenarios** — 10,100 synthetic crisis scenarios, uniqueness=1.0, diversity=7.56/8
- **Kupiec + Christoffersen backtests** — pass all 6 assets
- **Student-t Copula** — tail dependence across assets

### World Model — Layer 7
Classifies macro narrative every 15 minutes from market + sentiment:

```
INFLATION_FEAR → SAFE_HAVEN_DEMAND → AI_OPTIMISM
LIQUIDITY_CRUNCH → CRYPTO_FEAR → RISK_ON → CONSOLIDATION
```

Each narrative adjusts signal confidence and position sizing across all agents.

---

## Live Services (9 systemd units)

| Service | Function | Interval |
|---------|----------|----------|
| `aria_loop_v5` | Core decision engine | 60s |
| `aria_market` | Price collection (Binance + Yahoo) | 60s |
| `aria_sentiment` | Sentiment engine (Problem B) | 5min |
| `aria_meta` | Capital allocation (BOOST/KILL) | 5min |
| `aria_world_model` | Macro narrative classification | 15min |
| `aria_execution` | Order execution worker | continuous |
| `aria_anomaly` | Safety spine + anomaly detection | 60s |
| `aria_learning_loop` | Weekly self-retraining | 1hr check |
| `aria_watchdog` | System watchdog | continuous |

All services use `Restart=always` — survive crashes and reboots automatically.

---

## ML Models

**Architecture:** `quant_engine_v3_{symbol}.pkl` per asset

- XGBoost classifier (60% ensemble weight)
- Random Forest classifier (40% ensemble weight)
- ATR triple-barrier labelling (`tp_mult=1.5`, `sl_mult=1.0`, `horizon=48`)
- VPIN microstructure for order flow imbalance detection
- Walk-forward validation (no lookahead bias)

**Results:**

| Symbol | Overall Accuracy | Walk-Forward |
|--------|-----------------|--------------|
| BTC | 53.2% | 51.3% |
| ETH | 54.5% | 51.8% |
| AAPL | 54.1% | 52.0% |
| NVDA | 55.3% | 53.1% |
| TSLA | 52.8% | 51.5% |
| GLD | 47.1% | 49.6% |
| **Multi-asset ensemble** | **78.3%** | **76.1%** |

The 78.3% multi-asset figure is the dissertation's novel contribution — cross-asset feature learning creates information that no single-asset model can capture.

---

## Chat Interface

ARIA includes a Claude-powered financial intelligence chat layer:
- DB-backed conversation history (persists across Railway deploys)
- Proper multi-turn Claude API messages array
- World state + system mode injected into every system prompt
- ARIA explains *why* it is or isn't trading in plain language

---

## Dissertation

This system is the practical implementation of an MSc dissertation at De Montfort University (CSIP5501_2025_631), supervised by Dr. Usama Mannai. The dissertation includes:
- Full mathematical derivations (VPIN, ATR triple-barrier, GPD/VaR/ES, Kupiec LR, Christoffersen, WGAN-GP, Student-t Copula)
- 12 embedded matplotlib figures
- 19 Harvard references
- Novel finding: multi-asset ensemble superiority

---

## Roadmap — Toward Domain AGI in Finance

ARIA's current architecture is the foundation. The roadmap toward domain-bounded AGI:

1. **Problem B** — FinBERT on FOMC transcripts + Reddit sentiment → expanded feature vector
2. **Causal graph** — Granger causality + lead-lag matrix, live directed graph of asset relationships
3. **Episodic memory** — full context trade memory, similarity-based retrieval before decisions
4. **Uncertainty quantification** — Mahalanobis OOD detection, conformal prediction intervals
5. **Multi-agent debate** — Bull vs Bear agents per asset, meta-controller arbitrates
6. **Adversarial self-testing** — dynamic stress scenarios targeting current positions
7. **Hypothesis engine** — autonomous rule discovery and promotion
8. **Genuine self-improvement** — feature discovery, architecture search

---

## Tech Stack

```
Backend:     FastAPI (Python 3.12)
ML:          XGBoost, scikit-learn, PyTorch, NumPy, pandas
Data:        yfinance, Binance WebSocket, FRED API
Database:    PostgreSQL 16 (Hetzner) + Railway PostgreSQL
AI Chat:     Anthropic Claude Sonnet API
Risk:        SciPy (EVT/GPD), custom WGAN-GP, Student-t Copula
Infra:       Hetzner CPX32, Railway Hobby, systemd, GitHub Actions
```

---

## Author

**Usama** — MSc Data Analytics, De Montfort University (graduating September 2026)

Building autonomous AI systems at the intersection of quantitative finance and AI safety.

Based in Manchester/Huddersfield, UK.

---

*ARIA is a research and portfolio project. Paper trading only. Not financial advice.*
