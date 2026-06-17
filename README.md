# ARIA — Intelligent Financial Analytics System

**Autonomous Reasoning and Intelligence Architecture**

MSc Data Analytics Dissertation — De Montfort University, 2026
Student: Usama Fateh Ali (P2914214) | Supervisor: Dr. Usama Mannai

Live Dashboard: https://web-production-548c0.up.railway.app/terminal

Production since March 2026 on Hetzner CPX32.

## Overview

ARIA is a production-deployed multi-asset financial analytics system.

Primary finding: Multi-asset ensemble achieves 78.3% historical pattern effectiveness vs 41.8% single-asset baseline (+36.5pp). Wilcoxon W=276, p=0.0003, effect size r=0.71, 24 monthly walk-forward windows.

## Six-Layer Architecture

- L1 Data Collection: 63 sources, 7.5M+ records, 99.2% uptime
- L2 Pattern Recognition: 27-feature vector, XGBoost+RF+NN ensemble
- L3 Contextual Analysis: Claude API, 6-dimension world state, NL output
- L4 Risk Quantification: EVT/GPD corrected ES, Kelly, Correlation Kill Switch
- L5 Scenario Modelling: 10,100 WGAN-GP scenarios, Student-t Monte Carlo
- L6 Effectiveness Tracker: 60/90/180-day windows, 8-12 day early warning

All layers communicate via shared PostgreSQL (aria_db) on Hetzner.

## Key Results

- Multi-asset effectiveness: 78.3%
- Single-asset baseline: 41.8%
- Improvement: +36.5 pp
- Wilcoxon p-value: 0.0003
- Effect size r: 0.71 (large)
- Walk-forward windows: 24 monthly
- Data sources: 63
- Records in DB: 7.5M+
- System uptime L1: 99.2%
- EVT validation checks: 8/8 pass

## Asset Universe

- Cryptocurrency: BTC/USD, ETH/USD
- Equity: SPY, AAPL, NVDA, TSLA
- Commodity: Gold (GLD), Crude Oil WTI
- Foreign Exchange: GBP/USD, EUR/USD
- Fixed Income: US Treasury yields (2Y, 10Y, 30Y)
- Macro: VIX, DXY, Fed policy indicators

## Repository Structure

- main.py: FastAPI backend, signal engine, risk module, Monte Carlo, paper trading, Claude API
- dashboard.py: Dashboard data serving
- sync_to_cloud.py: Railway PostgreSQL sync
- frontend.html: React SPA dashboard
- requirements.txt: Python dependencies
- production_model_78pct.pkl: Main ensemble (78.3% effectiveness)
- pattern_engine_ASSET.pkl: Per-asset pattern models
- quant_engine_v3_ASSET.pkl: Per-asset quant models (active)

## API Endpoints

- GET /price/{symbol}: Live price + signal
- GET /assets: All 6 assets
- GET /macro: Yield curve, VIX, DXY, credit spreads
- GET /backtest/{symbol}: 60-day walk-forward results
- GET /riskscore/{symbol}: Kelly, VaR, Monte Carlo analysis
- POST /chat: Ask ARIA via Claude API
- POST /paper/trade: Open paper trade
- GET /paper/portfolio/{user_id}: Live portfolio P&L

## Layer 4: Novel ES Formula Correction

Key technical contribution — correction of error in standard Expected Shortfall formula.

Standard (INCORRECT): ES = VaR/(1-xi) + beta/(1-xi)
Corrected (ARIA):     ES = VaR/(1-xi) + (beta - xi*u)/(1-xi)

For BTC (xi=0.31): correction yields 18.2% higher ES estimate.
Validated vs Monte Carlo bootstrap n=10,000, deviation less than 0.3%.

## Infrastructure

- Hetzner CPX32: Ubuntu 24, 4 vCPU, 8GB RAM, all Python services
- PostgreSQL aria_db: Hetzner-hosted, 7.5M+ records
- Railway: FastAPI + React SPA, auto-deploy from main branch
- Claude API: claude-sonnet, Layer 3 NL explanation

## Run Locally

git clone https://github.com/Usama1909/ARIA_V1_terminal.git
cd ARIA_V1_terminal
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key
python main.py

## Research Context

Built as MSc dissertation artefact at De Montfort University under Design Science Research paradigm. Submitted May 29, 2026. All results use walk-forward validation, no look-ahead bias.

ARIA — Intelligent Financial Analytics System | De Montfort University | MSc Data Analytics 2026
