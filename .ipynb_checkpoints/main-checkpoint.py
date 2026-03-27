# main.py - ARIA Terminal v2 - Complete Deployable Version
# Fixes: portfolio loading, adds backtesting, FRED indicators

import anthropic
import pickle
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import json
import os
import math
import time
import threading
import warnings
import requests as req
from scipy import stats
from scipy.stats import t as student_t
warnings.filterwarnings('ignore')

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn

# ── CONFIGURATION ─────────────────────────────────────────
PORT = int(os.environ.get('PORT', 8001))
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

print("ARIA TERMINAL v2 - STARTING UP")
print("="*60)
print(f"Port: {PORT}")
print(f"API Key: {'SET' if ANTHROPIC_API_KEY else 'MISSING'}")

# ── LOAD MODELS ───────────────────────────────────────────
print("\nLoading models...")
production_models = {}
for symbol in ['BTC', 'ETH', 'AAPL', 'NVDA', 'TSLA', 'GLD']:
    try:
        with open(f'quant_engine_v3_{symbol}.pkl', 'rb') as f:
            production_models[symbol] = pickle.load(f)
        print(f"  {symbol}: loaded")
    except Exception as e:
        print(f"  {symbol}: not found - {e}")

# Load sentiment
try:
    with open('live_sentiment.pkl', 'rb') as f:
        live_sentiment = pickle.load(f)
    print(f"  Sentiment: loaded")
except:
    live_sentiment = {}
    print(f"  Sentiment: not found - building live")

print(f"\nModels loaded: {len(production_models)}/6")

# ── BUILD LIVE SENTIMENT IF EMPTY ────────────────────────
def build_default_sentiment():
    default = {}
    for symbol in ['BTC', 'ETH', 'AAPL', 'NVDA', 'TSLA', 'GLD']:
        try:
            yf_map = {
                'BTC': 'BTC-USD', 'ETH': 'ETH-USD',
                'AAPL': 'AAPL', 'NVDA': 'NVDA',
                'TSLA': 'TSLA', 'GLD': 'GLD'
            }
            ticker  = yf.Ticker(yf_map[symbol])
            hist    = ticker.history(period='5d', interval='1h')
            fg_value = 50
            try:
                fg_r = req.get('https://api.alternative.me/fng/?limit=1', timeout=5)
                fg_value = int(fg_r.json()['data'][0]['value'])
            except:
                fg_value = 23
            if len(hist) > 10:
                returns    = hist['Close'].pct_change().dropna()
                avg_return = float(returns.mean())
                if avg_return > 0.001:   label = 'POSITIVE'; score = 0.6
                elif avg_return < -0.001: label = 'NEGATIVE'; score = -0.6
                else:                     label = 'NEUTRAL';  score = 0.0
            else:
                label = 'NEUTRAL'; score = 0.0
            default[symbol] = {
                'sentiment_label':  label,
                'composite_score':  score,
                'news_count':       0,
                'fear_greed_value': fg_value,
                'fear_greed_label': 'Extreme Fear' if fg_value < 25 else 'Fear' if fg_value < 45 else 'Neutral',
                'top_headlines':    []
            }
        except:
            default[symbol] = {
                'sentiment_label': 'NEUTRAL', 'composite_score': 0,
                'news_count': 0, 'fear_greed_value': 23,
                'fear_greed_label': 'Extreme Fear', 'top_headlines': []
            }
    return default

if not live_sentiment:
    print("Building live sentiment...")
    live_sentiment = build_default_sentiment()
    print(f"Sentiment ready for {len(live_sentiment)} assets")

# ── SIGNAL HISTORY ────────────────────────────────────────
SIGNAL_HISTORY_FILE = 'signal_history.json'
_logged_this_session = set()

def load_signal_history():
    if os.path.exists(SIGNAL_HISTORY_FILE):
        try:
            with open(SIGNAL_HISTORY_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_signal_to_history(symbol, signal, confidence, price, sentiment, rsi):
    try:
        session_key = f"{symbol}_{signal}"
        if session_key in _logged_this_session:
            return
        _logged_this_session.add(session_key)
        history = load_signal_history()
        now = datetime.now()
        for existing in history[-20:]:
            if existing['symbol'] == symbol:
                existing_time = datetime.fromisoformat(existing['timestamp'])
                minutes_ago = (now - existing_time).total_seconds() / 60
                if minutes_ago < 60:
                    return
        entry = {
            'timestamp': now.isoformat(), 'symbol': symbol,
            'signal': signal, 'confidence': round(confidence * 100, 1),
            'price': round(price, 4), 'sentiment': sentiment,
            'rsi': round(rsi, 1), 'outcome': 'PENDING',
            'outcome_price': None, 'outcome_time': None, 'pnl_pct': None
        }
        history.append(entry)
        with open(SIGNAL_HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"Signal log error: {e}")

# ── FASTAPI APP ───────────────────────────────────────────
app = FastAPI(title="ARIA - Advanced Retail Intelligence & Analytics", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ChatRequest(BaseModel):
    message:    str
    symbol:     Optional[str] = None
    user_level: Optional[str] = 'intermediate'
    user_id:    Optional[str] = 'anonymous'

class TradeRequest(BaseModel):
    user_id:    str
    symbol:     str
    direction:  str
    amount_usd: Optional[float] = 100.0

class CloseTradeRequest(BaseModel):
    user_id:  str
    trade_id: str

# ── PRICE CACHE ───────────────────────────────────────────
_price_cache      = {}
_price_cache_time = {}
CACHE_SECONDS     = 60

# ── PAPER TRADING ─────────────────────────────────────────
PAPER_TRADES_FILE = 'paper_trades.json'
STARTING_BALANCE  = 10000.0

def load_paper_portfolios():
    if os.path.exists(PAPER_TRADES_FILE):
        try:
            with open(PAPER_TRADES_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_paper_portfolios(portfolios):
    with open(PAPER_TRADES_FILE, 'w') as f:
        json.dump(portfolios, f, indent=2)

def get_or_create_portfolio(user_id):
    portfolios = load_paper_portfolios()
    if user_id not in portfolios:
        portfolios[user_id] = {
            'user_id': user_id, 'balance': STARTING_BALANCE,
            'starting_balance': STARTING_BALANCE,
            'open_trades': [], 'closed_trades': [],
            'created_at': datetime.now().isoformat()
        }
        save_paper_portfolios(portfolios)
    return portfolios[user_id]

# ── CORE FUNCTIONS ────────────────────────────────────────
def get_live_features(symbol):
    yf_map = {
        'BTC': 'BTC-USD', 'ETH': 'ETH-USD',
        'AAPL': 'AAPL', 'NVDA': 'NVDA', 'TSLA': 'TSLA', 'GLD': 'GLD'
    }
    ticker = yf.Ticker(yf_map[symbol])
    df = ticker.history(period='60d', interval='1h')
    if len(df) < 100:
        return None, None
    df = df.reset_index()
    df.columns = [c.replace(' ', '_') for c in df.columns]
    prices = df['Close']; volume = df['Volume']
    high = df['High'];    low    = df['Low']
    tr1 = high - low
    tr2 = abs(high - prices.shift(1))
    tr3 = abs(low  - prices.shift(1))
    atr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean()
    delta = prices.diff()
    gain  = delta.where(delta > 0, 0).rolling(14).mean()
    loss  = -delta.where(delta < 0, 0).rolling(14).mean()
    rsi   = 100 - (100 / (1 + gain / loss))
    ema_fast = prices.ewm(span=12).mean(); ema_slow = prices.ewm(span=26).mean()
    macd = ema_fast - ema_slow; macd_signal = macd.ewm(span=9).mean(); macd_hist = macd - macd_signal
    ma_20 = prices.rolling(20).mean(); std_20 = prices.rolling(20).std()
    bb_upper = ma_20 + (std_20 * 2); bb_lower = ma_20 - (std_20 * 2); ma_50 = prices.rolling(50).mean()
    volatility = prices.pct_change().rolling(10).std()
    bb_position = (prices - bb_lower) / (bb_upper - bb_lower)
    ma_distance = (ma_20 - ma_50) / ma_50
    price_change_5 = prices.pct_change(5); price_change_10 = prices.pct_change(10); price_change_24 = prices.pct_change(24)
    rsi_momentum = rsi.diff(); volume_ratio = volume / volume.rolling(20).mean()
    volume_trend = volume.rolling(5).mean() / volume.rolling(20).mean()
    prices_4h = prices.rolling(4).mean(); delta_4h = prices_4h.diff()
    gain_4h = delta_4h.where(delta_4h > 0, 0).rolling(14).mean()
    loss_4h = -delta_4h.where(delta_4h < 0, 0).rolling(14).mean()
    rsi_4h = 100 - (100 / (1 + gain_4h / loss_4h))
    high_24 = prices.rolling(24).max(); low_24 = prices.rolling(24).min()
    dist_from_high = (prices - high_24) / high_24; dist_from_low = (prices - low_24) / low_24
    range_24 = high_24 - low_24
    range_position = np.where(range_24 > 0, (prices - low_24) / range_24, 0.5)
    candle_range = (high - low) / prices
    candle_close_pos = (prices - low) / (high - low + 1e-9)
    upper_wick = (high - prices) / (high - low + 1e-9); lower_wick = (prices - low) / (high - low + 1e-9)
    adx_proxy = abs(ma_distance) / volatility.replace(0, np.nan)
    z_score = (prices - prices.rolling(20).mean()) / prices.rolling(20).std()
    momentum_5 = prices / prices.shift(5) - 1; momentum_10 = prices / prices.shift(10) - 1
    atr_pct = atr / prices
    pct_change = prices.pct_change()
    buy_vol_frac = np.where(pct_change > 0.001, 0.9, np.where(pct_change < -0.001, 0.1, np.where(pct_change > 0, 0.6, np.where(pct_change < 0, 0.4, 0.5))))
    buy_volume = volume * buy_vol_frac; ofi = abs(buy_volume - volume * (1 - buy_vol_frac))
    vpin_raw = ofi.rolling(50).sum() / volume.rolling(50).sum()
    vpin_10 = vpin_raw.quantile(0.10); vpin_90 = vpin_raw.quantile(0.90)
    vpin_norm = ((vpin_raw - vpin_10) / (vpin_90 - vpin_10 + 1e-9)).clip(0, 1)
    vpin_signal = np.where(vpin_norm > 0.7, 1, np.where(vpin_norm < 0.3, -1, 0))
    feature_names = [
        'rsi','macd','macd_hist','volatility','bb_position','ma_distance',
        'price_change_5','price_change_10','price_change_24','rsi_momentum',
        'volume_ratio','volume_trend','rsi_4h','dist_from_high','dist_from_low',
        'range_position','candle_range','candle_close_pos','upper_wick','lower_wick',
        'adx_proxy','z_score','momentum_5','momentum_10','atr_pct','vpin_norm','vpin_signal'
    ]
    features = pd.DataFrame({
        'rsi': rsi, 'macd': macd, 'macd_hist': macd_hist, 'volatility': volatility,
        'bb_position': bb_position, 'ma_distance': ma_distance,
        'price_change_5': price_change_5, 'price_change_10': price_change_10,
        'price_change_24': price_change_24, 'rsi_momentum': rsi_momentum,
        'volume_ratio': volume_ratio, 'volume_trend': volume_trend, 'rsi_4h': rsi_4h,
        'dist_from_high': dist_from_high, 'dist_from_low': dist_from_low,
        'range_position': pd.Series(range_position, index=prices.index),
        'candle_range': candle_range,
        'candle_close_pos': pd.Series(candle_close_pos.values if hasattr(candle_close_pos, 'values') else candle_close_pos, index=prices.index),
        'upper_wick': pd.Series(upper_wick.values if hasattr(upper_wick, 'values') else upper_wick, index=prices.index),
        'lower_wick': pd.Series(lower_wick.values if hasattr(lower_wick, 'values') else lower_wick, index=prices.index),
        'adx_proxy': adx_proxy, 'z_score': z_score, 'momentum_5': momentum_5,
        'momentum_10': momentum_10, 'atr_pct': atr_pct, 'vpin_norm': vpin_norm,
        'vpin_signal': pd.Series(vpin_signal, index=prices.index)
    })
    latest = features.dropna().iloc[-1]
    current_price = float(prices.iloc[-1]); current_atr = float(atr.dropna().iloc[-1])
    return latest[feature_names].values.reshape(1, -1), {
        'price': current_price, 'atr': current_atr,
        'rsi': float(rsi.dropna().iloc[-1]), 'macd': float(macd.dropna().iloc[-1]),
        'ma_distance': float(ma_distance.dropna().iloc[-1]),
        'volatility': float(volatility.dropna().iloc[-1]),
        'vpin_norm': float(vpin_norm.dropna().iloc[-1]),
        'price_24h_ago': float(prices.iloc[-25]) if len(prices) > 25 else current_price,
        'prices': prices, 'high': high, 'low': low, 'volume': volume, 'atr_series': atr
    }

def get_model_signal(symbol, features_array):
    if symbol not in production_models:
        return None
    model_data = production_models[symbol]
    try:
        xgb_proba = model_data['xgb_model'].predict_proba(features_array)
        rf_proba  = model_data['rf_model'].predict_proba(features_array)
        ensemble_proba = (xgb_proba + rf_proba) / 2
        tp_prob = float(ensemble_proba[0][1]); sl_prob = float(ensemble_proba[0][0])
        return {
            'signal': 'TAKE_PROFIT' if tp_prob > sl_prob else 'STOP_LOSS',
            'confidence': max(tp_prob, sl_prob),
            'tp_probability': tp_prob, 'sl_probability': sl_prob
        }
    except:
        return None

def get_live_price_only(symbol):
    now = time.time()
    if symbol in _price_cache and (now - _price_cache_time.get(symbol, 0)) < CACHE_SECONDS:
        return _price_cache[symbol]
    try:
        features_array, market_data = get_live_features(symbol)
        if not market_data:
            return _price_cache.get(symbol, None)
        model_signal = get_model_signal(symbol, features_array) if features_array is not None else None
        sentiment    = live_sentiment.get(symbol, {})
        price        = market_data['price']
        price_24h    = market_data['price_24h_ago']
        change_24h   = ((price - price_24h) / price_24h) * 100
        result = {
            'symbol': symbol, 'price': round(price, 4),
            'change_24h': round(change_24h, 2), 'rsi': round(market_data['rsi'], 2),
            'signal': model_signal,
            'sentiment': sentiment.get('sentiment_label', 'NEUTRAL'),
            'fear_greed': sentiment.get('fear_greed_value', 50),
            'timestamp': datetime.now().isoformat()
        }
        _price_cache[symbol] = result; _price_cache_time[symbol] = now
        return result
    except:
        return _price_cache.get(symbol, None)

def build_aria_context(symbol):
    features_array, market_data = get_live_features(symbol)
    if features_array is None:
        return None
    model_signal = get_model_signal(symbol, features_array)
    sentiment = live_sentiment.get(symbol, {
        'sentiment_label': 'NEUTRAL', 'composite_score': 0,
        'news_count': 0, 'fear_greed_value': 50,
        'fear_greed_label': 'Neutral', 'top_headlines': []
    })
    atr = market_data['atr']; price = market_data['price']
    barriers = production_models[symbol]['atr_params'] if symbol in production_models else {'tp_mult': 1.5, 'sl_mult': 1.0}
    price_24h = market_data['price_24h_ago']
    if model_signal and model_signal['confidence'] >= 0.55:
        save_signal_to_history(symbol, model_signal['signal'], model_signal['confidence'], price, sentiment.get('sentiment_label', 'NEUTRAL'), market_data['rsi'])
    return {
        'symbol': symbol, 'price': price,
        'change_24h': ((price - price_24h) / price_24h) * 100,
        'atr': atr, 'atr_pct': (atr/price)*100,
        'rsi': market_data['rsi'], 'macd': market_data['macd'],
        'ma_distance': market_data['ma_distance'],
        'volatility': market_data['volatility'],
        'vpin_norm': market_data['vpin_norm'],
        'tp_level': price + (atr * barriers['tp_mult']),
        'sl_level': price - (atr * barriers['sl_mult']),
        'model_signal': model_signal, 'sentiment': sentiment,
        'timestamp': datetime.now().isoformat()
    }

# ── BACKTESTING ENGINE ────────────────────────────────────
_backtest_cache = {}
_backtest_cache_time = {}

def run_backtest(symbol):
    """
    Run full backtest on 60 days of historical data
    Uses our actual XGBoost model signals
    Returns real win rates, Sharpe, drawdown
    """
    now = time.time()
    if symbol in _backtest_cache and (now - _backtest_cache_time.get(symbol, 0)) < 3600:
        return _backtest_cache[symbol]

    try:
        yf_map = {
            'BTC': 'BTC-USD', 'ETH': 'ETH-USD',
            'AAPL': 'AAPL', 'NVDA': 'NVDA', 'TSLA': 'TSLA', 'GLD': 'GLD'
        }
        ticker = yf.Ticker(yf_map[symbol])
        df     = ticker.history(period='60d', interval='1h')

        if len(df) < 200:
            raise ValueError("Not enough data")

        df     = df.reset_index()
        df.columns = [c.replace(' ', '_') for c in df.columns]
        prices = df['Close'].values
        high   = df['High'].values
        low    = df['Low'].values

        barriers = production_models[symbol]['atr_params'] if symbol in production_models else {'tp_mult': 1.5, 'sl_mult': 1.0, 'horizon': 24}
        horizon  = barriers.get('horizon', 24)

        wins = []; losses = []
        win_pcts = []; loss_pcts = []
        equity = [10000.0]
        trades = []

        # Walk forward - simulate every 24 hours
        for i in range(50, len(prices) - horizon - 1, 24):
            try:
                # Build features for this point in time
                slice_df = df.iloc[max(0, i-60):i+1].copy()
                slice_prices = slice_df['Close']
                slice_volume = slice_df['Volume']
                slice_high   = slice_df['High']
                slice_low    = slice_df['Low']

                if len(slice_prices) < 50:
                    continue

                # Calculate ATR for barriers
                tr1 = slice_high - slice_low
                tr2 = abs(slice_high - slice_prices.shift(1))
                tr3 = abs(slice_low  - slice_prices.shift(1))
                atr_series = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean()
                current_atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else prices[i] * 0.02

                entry_price   = prices[i]
                tp = entry_price + current_atr * barriers['tp_mult']
                sl = entry_price - current_atr * barriers['sl_mult']

                # Get model signal at this point
                delta = slice_prices.diff()
                gain  = delta.where(delta > 0, 0).rolling(14).mean()
                loss  = -delta.where(delta < 0, 0).rolling(14).mean()
                rsi   = 100 - (100 / (1 + gain / loss))

                ema_fast = slice_prices.ewm(span=12).mean()
                ema_slow = slice_prices.ewm(span=26).mean()
                macd     = ema_fast - ema_slow
                macd_hist= macd - macd.ewm(span=9).mean()

                ma_20 = slice_prices.rolling(20).mean()
                ma_50 = slice_prices.rolling(50).mean()
                std_20 = slice_prices.rolling(20).std()
                bb_upper = ma_20 + std_20 * 2
                bb_lower = ma_20 - std_20 * 2

                volatility    = slice_prices.pct_change().rolling(10).std()
                bb_position   = (slice_prices - bb_lower) / (bb_upper - bb_lower)
                ma_distance   = (ma_20 - ma_50) / ma_50
                price_change_5 = slice_prices.pct_change(5)
                price_change_10= slice_prices.pct_change(10)
                price_change_24= slice_prices.pct_change(min(24, len(slice_prices)-1))
                rsi_momentum  = rsi.diff()
                volume_ratio  = slice_volume / slice_volume.rolling(20).mean()
                volume_trend  = slice_volume.rolling(5).mean() / slice_volume.rolling(20).mean()

                prices_4h = slice_prices.rolling(4).mean()
                delta_4h  = prices_4h.diff()
                gain_4h   = delta_4h.where(delta_4h > 0, 0).rolling(14).mean()
                loss_4h   = -delta_4h.where(delta_4h < 0, 0).rolling(14).mean()
                rsi_4h    = 100 - (100 / (1 + gain_4h / loss_4h))

                high_24 = slice_prices.rolling(min(24, len(slice_prices))).max()
                low_24  = slice_prices.rolling(min(24, len(slice_prices))).min()
                dist_from_high = (slice_prices - high_24) / high_24
                dist_from_low  = (slice_prices - low_24)  / low_24
                range_24       = high_24 - low_24
                range_position = np.where(range_24 > 0, (slice_prices - low_24) / range_24, 0.5)

                candle_range     = (slice_high - slice_low) / slice_prices
                candle_close_pos = (slice_prices - slice_low) / (slice_high - slice_low + 1e-9)
                upper_wick = (slice_high - slice_prices) / (slice_high - slice_low + 1e-9)
                lower_wick = (slice_prices - slice_low)  / (slice_high - slice_low + 1e-9)
                adx_proxy  = abs(ma_distance) / volatility.replace(0, np.nan)
                z_score    = (slice_prices - slice_prices.rolling(20).mean()) / slice_prices.rolling(20).std()
                momentum_5 = slice_prices / slice_prices.shift(5) - 1
                momentum_10= slice_prices / slice_prices.shift(10) - 1
                atr_pct    = atr_series / slice_prices

                pct_change   = slice_prices.pct_change()
                buy_vol_frac = np.where(pct_change > 0.001, 0.9, np.where(pct_change < -0.001, 0.1, 0.5))
                buy_volume   = slice_volume * buy_vol_frac
                ofi          = abs(buy_volume - slice_volume * (1 - buy_vol_frac))
                vpin_raw     = ofi.rolling(50).sum() / slice_volume.rolling(50).sum()
                vpin_10      = vpin_raw.quantile(0.10)
                vpin_90      = vpin_raw.quantile(0.90)
                vpin_norm    = ((vpin_raw - vpin_10) / (vpin_90 - vpin_10 + 1e-9)).clip(0, 1)
                vpin_signal  = np.where(vpin_norm > 0.7, 1, np.where(vpin_norm < 0.3, -1, 0))

                feature_names = [
                    'rsi','macd','macd_hist','volatility','bb_position','ma_distance',
                    'price_change_5','price_change_10','price_change_24','rsi_momentum',
                    'volume_ratio','volume_trend','rsi_4h','dist_from_high','dist_from_low',
                    'range_position','candle_range','candle_close_pos','upper_wick','lower_wick',
                    'adx_proxy','z_score','momentum_5','momentum_10','atr_pct','vpin_norm','vpin_signal'
                ]

                feat_df = pd.DataFrame({
                    'rsi': rsi, 'macd': macd, 'macd_hist': macd_hist,
                    'volatility': volatility, 'bb_position': bb_position,
                    'ma_distance': ma_distance, 'price_change_5': price_change_5,
                    'price_change_10': price_change_10, 'price_change_24': price_change_24,
                    'rsi_momentum': rsi_momentum, 'volume_ratio': volume_ratio,
                    'volume_trend': volume_trend, 'rsi_4h': rsi_4h,
                    'dist_from_high': dist_from_high, 'dist_from_low': dist_from_low,
                    'range_position': pd.Series(range_position, index=slice_prices.index),
                    'candle_range': candle_range,
                    'candle_close_pos': pd.Series(candle_close_pos.values if hasattr(candle_close_pos, 'values') else candle_close_pos, index=slice_prices.index),
                    'upper_wick': pd.Series(upper_wick.values if hasattr(upper_wick, 'values') else upper_wick, index=slice_prices.index),
                    'lower_wick': pd.Series(lower_wick.values if hasattr(lower_wick, 'values') else lower_wick, index=slice_prices.index),
                    'adx_proxy': adx_proxy, 'z_score': z_score,
                    'momentum_5': momentum_5, 'momentum_10': momentum_10,
                    'atr_pct': atr_pct, 'vpin_norm': vpin_norm,
                    'vpin_signal': pd.Series(vpin_signal, index=slice_prices.index)
                })

                feat_df = feat_df.dropna()
                if len(feat_df) == 0:
                    continue

                latest_features = feat_df[feature_names].iloc[-1].values.reshape(1, -1)
                signal = get_model_signal(symbol, latest_features)

                if not signal:
                    continue

                direction = signal['signal']

                # Check if TP or SL hit first in next horizon hours
                future_prices = prices[i+1:i+horizon+1]
                outcome = None
                exit_price = future_prices[-1] if len(future_prices) > 0 else entry_price

                for fp in future_prices:
                    if direction == 'TAKE_PROFIT':
                        if fp >= tp:
                            outcome = 'WIN'; exit_price = tp; break
                        elif fp <= sl:
                            outcome = 'LOSS'; exit_price = sl; break
                    else:
                        if fp <= sl:
                            outcome = 'WIN'; exit_price = sl; break
                        elif fp >= tp:
                            outcome = 'LOSS'; exit_price = tp; break

                if outcome is None:
                    # Time exit
                    exit_price = future_prices[-1] if len(future_prices) > 0 else entry_price
                    if direction == 'TAKE_PROFIT':
                        outcome = 'WIN' if exit_price > entry_price else 'LOSS'
                    else:
                        outcome = 'WIN' if exit_price < entry_price else 'LOSS'

                if direction == 'TAKE_PROFIT':
                    pnl_pct = (exit_price - entry_price) / entry_price * 100
                else:
                    pnl_pct = (entry_price - exit_price) / entry_price * 100

                pnl_usd = (pnl_pct / 100) * 100  # $100 position size

                if outcome == 'WIN':
                    wins.append(pnl_usd)
                    win_pcts.append(abs(pnl_pct))
                else:
                    losses.append(pnl_usd)
                    loss_pcts.append(abs(pnl_pct))

                equity.append(equity[-1] + pnl_usd)
                trades.append({
                    'direction': direction, 'outcome': outcome,
                    'pnl_pct': round(pnl_pct, 2), 'confidence': round(signal['confidence'], 3)
                })

            except Exception:
                continue

        total = len(wins) + len(losses)
        if total == 0:
            raise ValueError("No trades generated")

        win_rate    = len(wins) / total
        avg_win_pct = float(np.mean(win_pcts)) if win_pcts else 0
        avg_loss_pct= float(np.mean(loss_pcts)) if loss_pcts else 0

        # Sharpe ratio
        all_pnls = [t['pnl_pct'] for t in trades]
        sharpe   = float(np.mean(all_pnls) / np.std(all_pnls) * np.sqrt(252)) if np.std(all_pnls) > 0 else 0

        # Max drawdown
        equity_arr = np.array(equity)
        peak       = np.maximum.accumulate(equity_arr)
        drawdown   = (equity_arr - peak) / peak * 100
        max_dd     = float(np.min(drawdown))

        # Profit factor
        total_wins   = sum(abs(w) for w in wins)
        total_losses = sum(abs(l) for l in losses)
        profit_factor= round(total_wins / total_losses, 2) if total_losses > 0 else 0

        result = {
            'symbol':         symbol,
            'total_trades':   total,
            'win_rate':       round(win_rate * 100, 1),
            'avg_win_pct':    round(avg_win_pct, 2),
            'avg_loss_pct':   round(avg_loss_pct, 2),
            'sharpe_ratio':   round(sharpe, 2),
            'max_drawdown':   round(max_dd, 2),
            'profit_factor':  profit_factor,
            'total_pnl':      round(sum(wins) + sum(losses), 2),
            'equity_curve':   [round(e, 2) for e in equity[-50:]],
            'source':         'backtest_60d_live',
            'timestamp':      datetime.now().isoformat()
        }

        _backtest_cache[symbol]      = result
        _backtest_cache_time[symbol] = now
        print(f"  Backtest {symbol}: {total} trades, {win_rate*100:.1f}% win rate, Sharpe {sharpe:.2f}")
        return result

    except Exception as e:
        print(f"Backtest error {symbol}: {e}")
        defaults = {
            'BTC':  {'win_rate': 52.0, 'avg_win_pct': 1.8, 'avg_loss_pct': 1.2, 'sharpe_ratio': 0.8},
            'ETH':  {'win_rate': 51.0, 'avg_win_pct': 2.0, 'avg_loss_pct': 1.4, 'sharpe_ratio': 0.7},
            'AAPL': {'win_rate': 54.0, 'avg_win_pct': 1.2, 'avg_loss_pct': 0.9, 'sharpe_ratio': 1.1},
            'NVDA': {'win_rate': 53.0, 'avg_win_pct': 1.5, 'avg_loss_pct': 1.1, 'sharpe_ratio': 0.9},
            'TSLA': {'win_rate': 51.0, 'avg_win_pct': 2.2, 'avg_loss_pct': 1.6, 'sharpe_ratio': 0.6},
            'GLD':  {'win_rate': 55.0, 'avg_win_pct': 0.9, 'avg_loss_pct': 0.7, 'sharpe_ratio': 1.2},
        }
        d = defaults.get(symbol, {'win_rate': 52.0, 'avg_win_pct': 1.5, 'avg_loss_pct': 1.0, 'sharpe_ratio': 0.8})
        return {**d, 'symbol': symbol, 'total_trades': 0,
                'max_drawdown': -15.0, 'profit_factor': 1.2,
                'total_pnl': 0, 'equity_curve': [],
                'source': 'default', 'timestamp': datetime.now().isoformat()}

# ── FRED LEADING INDICATORS ───────────────────────────────
_macro_cache = {}
_macro_cache_time = 0

def get_macro_indicators():
    """
    Fetch leading indicators from FRED and Yahoo Finance
    These are Burry-type signals that move BEFORE price
    Free, no API key needed for Yahoo Finance proxies
    """
    global _macro_cache, _macro_cache_time
    now = time.time()
    if _macro_cache and (now - _macro_cache_time) < 3600:
        return _macro_cache

    try:
        indicators = {}

        # Yield curve (10Y - 2Y) - recession predictor
        try:
            tnx = yf.Ticker('^TNX')  # 10Y Treasury
            irx = yf.Ticker('^IRX')  # 13-week T-bill proxy for 2Y
            hist_10y = tnx.history(period='30d', interval='1d')
            hist_2y  = irx.history(period='30d', interval='1d')
            if len(hist_10y) > 0 and len(hist_2y) > 0:
                rate_10y = float(hist_10y['Close'].iloc[-1])
                rate_2y  = float(hist_2y['Close'].iloc[-1]) / 100
                spread   = rate_10y - rate_2y
                indicators['yield_curve'] = {
                    'value':       round(spread, 3),
                    'rate_10y':    round(rate_10y, 3),
                    'rate_2y':     round(rate_2y * 100, 3),
                    'signal':      'INVERTED' if spread < 0 else 'NORMAL',
                    'warning':     spread < 0,
                    'description': 'Yield curve inverted - historically precedes recession by 12-18 months' if spread < 0 else 'Yield curve normal',
                    'burry_signal': spread < -0.5
                }
        except Exception as e:
            indicators['yield_curve'] = {'value': 0, 'signal': 'UNAVAILABLE', 'warning': False, 'burry_signal': False}

        # VIX - Fear index
        try:
            vix = yf.Ticker('^VIX')
            vix_hist = vix.history(period='30d', interval='1d')
            if len(vix_hist) > 0:
                vix_current = float(vix_hist['Close'].iloc[-1])
                vix_avg     = float(vix_hist['Close'].mean())
                indicators['vix'] = {
                    'current':     round(vix_current, 2),
                    'avg_30d':     round(vix_avg, 2),
                    'signal':      'EXTREME_FEAR' if vix_current > 35 else 'HIGH_FEAR' if vix_current > 25 else 'ELEVATED' if vix_current > 18 else 'NORMAL',
                    'warning':     vix_current > 25,
                    'description': f'VIX at {vix_current:.1f} - {"crisis level" if vix_current > 35 else "elevated fear" if vix_current > 25 else "normal"}',
                    'burry_signal': vix_current > 30
                }
        except:
            indicators['vix'] = {'current': 20, 'signal': 'UNAVAILABLE', 'warning': False, 'burry_signal': False}

        # HYG - High Yield Credit Spreads (proxy for credit stress)
        try:
            hyg = yf.Ticker('HYG')   # High yield bonds
            lqd = yf.Ticker('LQD')   # Investment grade bonds
            hyg_hist = hyg.history(period='30d', interval='1d')
            lqd_hist = lqd.history(period='30d', interval='1d')
            if len(hyg_hist) > 0 and len(lqd_hist) > 0:
                hyg_return = float((hyg_hist['Close'].iloc[-1] / hyg_hist['Close'].iloc[0] - 1) * 100)
                lqd_return = float((lqd_hist['Close'].iloc[-1] / lqd_hist['Close'].iloc[0] - 1) * 100)
                spread = hyg_return - lqd_return
                indicators['credit_spreads'] = {
                    'hyg_return_30d': round(hyg_return, 2),
                    'lqd_return_30d': round(lqd_return, 2),
                    'spread':         round(spread, 2),
                    'signal':         'STRESS' if spread < -2 else 'ELEVATED' if spread < -0.5 else 'NORMAL',
                    'warning':        spread < -2,
                    'description':    f'Credit spreads {"widening - stress signal" if spread < -2 else "normal"}',
                    'burry_signal':   spread < -3
                }
        except:
            indicators['credit_spreads'] = {'spread': 0, 'signal': 'UNAVAILABLE', 'warning': False, 'burry_signal': False}

        # DXY - Dollar strength
        try:
            dxy = yf.Ticker('DX-Y.NYB')
            dxy_hist = dxy.history(period='30d', interval='1d')
            if len(dxy_hist) > 0:
                dxy_current = float(dxy_hist['Close'].iloc[-1])
                dxy_change  = float((dxy_hist['Close'].iloc[-1] / dxy_hist['Close'].iloc[0] - 1) * 100)
                indicators['dollar_index'] = {
                    'current':    round(dxy_current, 2),
                    'change_30d': round(dxy_change, 2),
                    'signal':     'STRONG' if dxy_change > 3 else 'WEAK' if dxy_change < -3 else 'NEUTRAL',
                    'warning':    abs(dxy_change) > 5,
                    'description': f'Dollar {"surging - risk-off signal" if dxy_change > 3 else "weakening - risk-on" if dxy_change < -3 else "stable"}',
                    'burry_signal': dxy_change > 5
                }
        except:
            indicators['dollar_index'] = {'current': 100, 'signal': 'UNAVAILABLE', 'warning': False, 'burry_signal': False}

        # Gold vs BTC ratio (crisis hedge)
        try:
            gld  = yf.Ticker('GLD')
            btc  = yf.Ticker('BTC-USD')
            gld_hist = gld.history(period='30d', interval='1d')
            btc_hist = btc.history(period='30d', interval='1d')
            if len(gld_hist) > 0 and len(btc_hist) > 0:
                gld_chg = float((gld_hist['Close'].iloc[-1] / gld_hist['Close'].iloc[0] - 1) * 100)
                btc_chg = float((btc_hist['Close'].iloc[-1] / btc_hist['Close'].iloc[0] - 1) * 100)
                indicators['gold_vs_crypto'] = {
                    'gold_30d':   round(gld_chg, 2),
                    'btc_30d':    round(btc_chg, 2),
                    'signal':     'RISK_OFF' if gld_chg > btc_chg + 5 else 'RISK_ON' if btc_chg > gld_chg + 5 else 'NEUTRAL',
                    'description': f'Gold {"outperforming - flight to safety" if gld_chg > btc_chg + 5 else "underperforming - risk appetite present" if btc_chg > gld_chg + 5 else "neutral vs crypto"}',
                    'burry_signal': gld_chg > btc_chg + 10
                }
        except:
            indicators['gold_vs_crypto'] = {'signal': 'UNAVAILABLE', 'burry_signal': False}

        # Overall crisis score
        burry_signals = sum(1 for k, v in indicators.items() if v.get('burry_signal', False))
        warnings      = sum(1 for k, v in indicators.items() if v.get('warning', False))

        crisis_score = min(100, burry_signals * 25 + warnings * 10)
        if crisis_score >= 75:   overall = 'CRISIS'
        elif crisis_score >= 50: overall = 'HIGH_RISK'
        elif crisis_score >= 25: overall = 'ELEVATED'
        else:                    overall = 'NORMAL'

        indicators['summary'] = {
            'crisis_score':  crisis_score,
            'overall':       overall,
            'burry_signals': burry_signals,
            'warnings':      warnings,
            'interpretation': f'{burry_signals} Burry-type signals active. {"CRISIS CONDITIONS DETECTED" if crisis_score >= 75 else "Elevated risk environment" if crisis_score >= 50 else "Monitor closely" if crisis_score >= 25 else "Markets appear stable"}',
            'timestamp':     datetime.now().isoformat()
        }

        _macro_cache      = indicators
        _macro_cache_time = now
        return indicators

    except Exception as e:
        return {'summary': {'crisis_score': 0, 'overall': 'UNAVAILABLE', 'error': str(e)}}

# ── NEWS CACHE ────────────────────────────────────────────
news_cache = {'headlines': [], 'last_updated': None}

def fetch_news_background():
    import xml.etree.ElementTree as ET
    RSS_FEEDS = [
        ('https://feeds.bbci.co.uk/news/world/rss.xml',           'bbc'),
        ('https://rss.nytimes.com/services/xml/rss/nyt/World.xml', 'nytimes'),
        ('https://cointelegraph.com/rss',                          'cointelegraph'),
        ('https://bitcoinmagazine.com/.rss/full/',                 'bitcoinmagazine'),
        ('https://www.investing.com/rss/news.rss',                 'investing'),
        ('https://feeds.a.dj.com/rss/RSSMarketsMain.xml',         'wsj'),
        ('https://decrypt.co/feed',                                'decrypt'),
    ]
    KEYWORDS = {
        'war':       ['war','conflict','attack','missile','troops','military','invasion','strike'],
        'fed':       ['fed','federal reserve','interest rate','inflation','powell','fomc','monetary'],
        'crypto':    ['bitcoin','ethereum','crypto','blockchain','defi','btc','eth','binance'],
        'ai':        ['artificial intelligence','ai ','machine learning','openai','llm','gpt'],
        'energy':    ['oil','gas','opec','energy','petroleum','crude'],
        'sanctions': ['sanctions','embargo','tariff','trade war','export ban'],
        'markets':   ['stock','market','nasdaq','s&p','dow','equity','rally','selloff'],
    }
    while True:
        try:
            all_headlines = []
            seen_titles   = set()
            for url, source in RSS_FEEDS:
                try:
                    r = req.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                    root = ET.fromstring(r.content)
                    items = root.findall('.//item')[:8]
                    for item in items:
                        title = item.findtext('title', '')
                        link  = item.findtext('link', '')
                        if title in seen_titles:
                            continue
                        seen_titles.add(title)
                        title_lower = title.lower()
                        tag = 'markets'; priority = 0
                        for kw_tag, keywords in KEYWORDS.items():
                            if any(kw in title_lower for kw in keywords):
                                tag = kw_tag
                                priority = 2 if kw_tag in ['war', 'fed', 'crypto'] else 1
                                break
                        all_headlines.append({'title': title, 'link': link, 'source': source, 'tag': tag, 'priority': priority})
                except:
                    pass
            all_headlines.sort(key=lambda x: x['priority'], reverse=True)
            news_cache['headlines']    = all_headlines[:47]
            news_cache['last_updated'] = datetime.now().strftime('%H:%M UTC')
            print(f"  News updated: {len(all_headlines)} headlines fetched")
        except Exception as e:
            print(f"  News fetch error: {e}")
        time.sleep(300)

threading.Thread(target=fetch_news_background, daemon=True).start()

# ── ASK ARIA ─────────────────────────────────────────────
conversation_history = {}
usage_tracker        = {}

def check_rate_limit(user_id, limit=50):
    now = time.time()
    if user_id not in usage_tracker:
        usage_tracker[user_id] = []
    usage_tracker[user_id] = [t for t in usage_tracker[user_id] if now - t < 3600]
    if len(usage_tracker[user_id]) >= limit:
        return False
    usage_tracker[user_id].append(now)
    return True

def get_live_news_context():
    try:
        headlines = news_cache.get('headlines', [])[:12]
        if not headlines:
            return "No live news available."
        lines = []
        for h in headlines:
            lines.append(f"  [{h.get('tag','news').upper()}] {h.get('title','')} ({h.get('source','')})")
        return "\n".join(lines)
    except:
        return "Live news temporarily unavailable."

def ask_aria(user_message, symbol=None, user_level='intermediate'):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    context_data = {}
    symbols_to_analyse = [symbol] if symbol else list(production_models.keys())
    for sym in symbols_to_analyse[:2]:
        ctx = build_aria_context(sym)
        if ctx:
            context_data[sym] = ctx
    context_str  = json.dumps(context_data, indent=2, default=str)
    fg_value     = list(context_data.values())[0]['sentiment']['fear_greed_value'] if context_data else 'N/A'
    news_context = get_live_news_context()
    system_prompt = f"""You are ARIA (Advanced Retail Intelligence & Analytics),
a professional financial intelligence assistant backed by real quant models.
USER LEVEL: {user_level}
- beginner: plain English only
- intermediate: some technical terms ok
- professional: full quant terminology
RULES:
1. Never say buy or sell directly
2. Always mention key risk alongside opportunity
3. Below 70% confidence: describe what is forming
4. Above 70% confidence: describe confirmed pattern
5. Always be honest about uncertainty
LIVE NEWS:
{news_context}
MARKET DATA:
{context_str}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
Fear/Greed: {fg_value}"""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )
    return response.content[0].text

# ── RISK ENGINE ───────────────────────────────────────────
SLIPPAGE_MODEL = {
    'BTC': 0.0005, 'ETH': 0.0007, 'AAPL': 0.0003,
    'NVDA': 0.0005, 'TSLA': 0.0006, 'GLD': 0.0004,
}
BID_ASK_SPREAD = {
    'BTC': 0.0001, 'ETH': 0.0002, 'AAPL': 0.0001,
    'NVDA': 0.0002, 'TSLA': 0.0003, 'GLD': 0.0002,
}
REGIME_KELLY_MULTIPLIER = {
    'CRISIS': 0.25, 'BEAR': 0.50, 'SIDEWAYS': 0.75,
    'BULL': 1.00, 'EUPHORIA': 0.50,
}

def clean_floats(obj):
    if isinstance(obj, dict):
        return {k: clean_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_floats(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return 0.0
        return obj
    return obj

def total_trade_cost_pct(symbol):
    return (SLIPPAGE_MODEL.get(symbol, 0.0005) + BID_ASK_SPREAD.get(symbol, 0.0002)) * 2

def detect_market_regime(symbol):
    try:
        price_data = get_live_price_only(symbol)
        if not price_data:
            return 'SIDEWAYS'
        fg  = price_data.get('fear_greed', 50)
        rsi = price_data.get('rsi', 50)
        if fg < 20 and rsi < 30:   return 'CRISIS'
        elif fg > 75 and rsi > 70: return 'EUPHORIA'
        elif fg < 40 and rsi < 45: return 'BEAR'
        elif fg > 60 and rsi > 55: return 'BULL'
        else:                      return 'SIDEWAYS'
    except:
        return 'SIDEWAYS'

def get_realised_volatility(symbol):
    yf_map = {
        'BTC': 'BTC-USD', 'ETH': 'ETH-USD',
        'AAPL': 'AAPL', 'NVDA': 'NVDA', 'TSLA': 'TSLA', 'GLD': 'GLD'
    }
    try:
        ticker  = yf.Ticker(yf_map[symbol])
        df      = ticker.history(period='30d', interval='1h')
        returns = df['Close'].pct_change().dropna()
        hourly_vol = float(returns.std())
        daily_vol  = hourly_vol * np.sqrt(24)
        annual_vol = daily_vol * np.sqrt(252)
        df_t, _, _ = student_t.fit(returns.values)
        df_t = max(3, min(30, df_t))
        return {
            'daily_vol': round(float(daily_vol), 4),
            'annual_vol': round(float(annual_vol * 100), 1),
            'hourly_vol': round(float(hourly_vol), 4),
            'student_t_df': round(float(df_t), 1),
            'is_crypto': symbol in ['BTC', 'ETH']
        }
    except:
        defaults = {
            'BTC': 0.025, 'ETH': 0.030, 'AAPL': 0.012,
            'NVDA': 0.020, 'TSLA': 0.025, 'GLD': 0.008
        }
        return {
            'daily_vol': defaults.get(symbol, 0.02),
            'annual_vol': defaults.get(symbol, 0.02) * np.sqrt(252) * 100,
            'hourly_vol': defaults.get(symbol, 0.02) / np.sqrt(24),
            'student_t_df': 4.0, 'is_crypto': symbol in ['BTC', 'ETH']
        }

def get_backtested_win_rates(symbol):
    """Use real backtest results if available"""
    now = time.time()
    if symbol in _backtest_cache and (now - _backtest_cache_time.get(symbol, 0)) < 3600:
        bt = _backtest_cache[symbol]
        return {
            'win_rate':     bt['win_rate'] / 100,
            'avg_win_pct':  bt['avg_win_pct'],
            'avg_loss_pct': bt['avg_loss_pct'],
            'sample_size':  bt['total_trades'],
            'source':       bt['source']
        }
    defaults = {
        'BTC':  {'win_rate': 0.52, 'avg_win_pct': 1.8, 'avg_loss_pct': 1.2},
        'ETH':  {'win_rate': 0.51, 'avg_win_pct': 2.0, 'avg_loss_pct': 1.4},
        'AAPL': {'win_rate': 0.54, 'avg_win_pct': 1.2, 'avg_loss_pct': 0.9},
        'NVDA': {'win_rate': 0.53, 'avg_win_pct': 1.5, 'avg_loss_pct': 1.1},
        'TSLA': {'win_rate': 0.51, 'avg_win_pct': 2.2, 'avg_loss_pct': 1.6},
        'GLD':  {'win_rate': 0.55, 'avg_win_pct': 0.9, 'avg_loss_pct': 0.7},
    }
    d = defaults.get(symbol, {'win_rate': 0.52, 'avg_win_pct': 1.5, 'avg_loss_pct': 1.0})
    d['sample_size'] = 0; d['source'] = 'conservative_default'
    return d

def kelly_criterion(win_rate, avg_win_pct, avg_loss_pct, regime='SIDEWAYS', max_fraction=0.20):
    if avg_loss_pct <= 0 or win_rate <= 0 or win_rate >= 1:
        return 0.02
    b = avg_win_pct / avg_loss_pct; p = win_rate; q = 1 - win_rate
    kelly = (b * p - q) / b
    multiplier = REGIME_KELLY_MULTIPLIER.get(regime, 0.75)
    return round(max(0.01, min(kelly / 2 * multiplier, max_fraction)), 4)

def monte_carlo_simulation(entry_price, direction, vol_data, holding_period_hours, trade_cost_pct, num_simulations=10000):
    daily_vol = vol_data['daily_vol']; df_t = vol_data['student_t_df']; hourly_vol = vol_data['hourly_vol']
    np.random.seed(None)
    hourly_returns = student_t.rvs(df=df_t, loc=0, scale=hourly_vol, size=(num_simulations, holding_period_hours))
    price_paths  = entry_price * np.exp(np.cumsum(hourly_returns, axis=1))
    final_prices = price_paths[:, -1]
    if direction == 'LONG':
        returns = (final_prices - entry_price) / entry_price * 100
    else:
        returns = (entry_price - final_prices) / entry_price * 100
    returns = returns - (trade_cost_pct * 100)
    profitable = returns > 0
    return {
        'probability_profit':  round(float(np.mean(profitable)) * 100, 1),
        'expected_return_pct': round(float(np.mean(returns)), 2),
        'median_return_pct':   round(float(np.median(returns)), 2),
        'best_case_pct':       round(float(np.percentile(returns, 95)), 2),
        'worst_case_pct':      round(float(np.percentile(returns, 5)), 2),
        'std_dev_pct':         round(float(np.std(returns)), 2),
        'skewness':            round(float(stats.skew(returns)), 2),
        'kurtosis':            round(float(stats.kurtosis(returns)), 2),
        'distribution':        f'Student-t (df={df_t:.1f})',
        'simulations_run':     num_simulations
    }

def calculate_var_cvar(position_usd, vol_data, confidence=0.95, horizon_days=1):
    daily_vol = vol_data['daily_vol']; df_t = vol_data['student_t_df']
    t_quantile = student_t.ppf(1 - confidence, df=df_t)
    var = position_usd * daily_vol * np.sqrt(horizon_days) * abs(t_quantile)
    try:
        samples = student_t.rvs(df=df_t, scale=daily_vol, size=100000)
        cutoff  = student_t.ppf(1 - confidence, df=df_t)
        tail    = samples[samples < cutoff]
        cvar    = position_usd * abs(float(np.mean(tail))) * np.sqrt(horizon_days)
        if math.isnan(cvar) or math.isinf(cvar):
            cvar = var * 1.3
    except:
        cvar = var * 1.3
    return {
        'var_95': round(float(var), 2), 'cvar_95': round(float(cvar), 2),
        'var_99': round(float(position_usd * daily_vol * abs(student_t.ppf(0.01, df=df_t))), 2),
        'method': 'Student-t (fat tails)'
    }

def analyse_trade_risk(symbol, direction, amount_usd, entry_price, portfolio_balance, signal_confidence, num_simulations=1000):
    regime      = detect_market_regime(symbol)
    regime_mult = REGIME_KELLY_MULTIPLIER.get(regime, 0.75)
    vol_data    = get_realised_volatility(symbol)
    win_data    = get_backtested_win_rates(symbol)
    win_rate    = win_data['win_rate']; avg_win_pct = win_data['avg_win_pct']; avg_loss_pct = win_data['avg_loss_pct']
    trade_cost  = total_trade_cost_pct(symbol)
    kelly_frac  = kelly_criterion(win_rate, avg_win_pct, avg_loss_pct, regime)
    kelly_amount= portfolio_balance * kelly_frac; kelly_pct = kelly_frac * 100
    position_pct= (amount_usd / portfolio_balance) * 100
    holding_hours = 48 if symbol in ['BTC', 'ETH'] else 24
    mc       = monte_carlo_simulation(entry_price, direction, vol_data, holding_hours, trade_cost, num_simulations)
    var_cvar = calculate_var_cvar(amount_usd, vol_data)
    ev_pct   = (win_rate * avg_win_pct) - ((1 - win_rate) * avg_loss_pct) - (trade_cost * 100)
    ev_usd   = round((ev_pct / 100) * amount_usd, 2)
    rr_ratio = round(avg_win_pct / avg_loss_pct, 2) if avg_loss_pct > 0 else 0
    if position_pct > kelly_pct * 2:      sizing = "OVER-SIZED"
    elif position_pct > kelly_pct * 1.25: sizing = "SLIGHTLY HIGH"
    elif position_pct <= kelly_pct:       sizing = "OPTIMAL"
    else:                                 sizing = "ACCEPTABLE"
    risk_score = min(100, int(
        (min(position_pct / max(kelly_pct, 0.1), 3) * 25) +
        (var_cvar['var_95'] / amount_usd * 100 * 25) +
        ((1 - mc['probability_profit'] / 100) * 25) +
        ((1 - signal_confidence) * 25)
    ))
    lines = []
    if regime == 'CRISIS':     lines.append("CRISIS REGIME: Reduce all position sizes significantly.")
    elif regime == 'BEAR':     lines.append("BEAR REGIME: Favour SHORT positions, reduce LONG sizes.")
    elif regime == 'EUPHORIA': lines.append("EUPHORIA REGIME: Late stage rally, reversal risk elevated.")
    if ev_usd <= 0:
        lines.append(f"NEGATIVE EV: Expected value ${ev_usd} after costs. Avoid this trade.")
    elif sizing == "OVER-SIZED":
        lines.append(f"REDUCE SIZE: Position exceeds Kelly optimal by 2x+.")
    elif mc['probability_profit'] > 65 and ev_usd > 0 and signal_confidence > 0.6:
        lines.append(f"FAVOURABLE: {mc['probability_profit']}% profit probability. EV +${ev_usd}.")
    elif mc['probability_profit'] > 55:
        lines.append(f"MARGINAL EDGE: {mc['probability_profit']}% profit probability. EV +${ev_usd}.")
    else:
        lines.append(f"WEAK SETUP: Only {mc['probability_profit']}% profit probability.")
    if win_data['source'] == 'conservative_default':
        lines.append("NOTE: Win rate from defaults. Run /backtest for real rates.")
    elif win_data['source'] == 'backtest_60d_live':
        lines.append(f"Win rate from {win_data['sample_size']} backtested trades.")
    return clean_floats({
        'symbol': symbol, 'direction': direction, 'amount_usd': amount_usd,
        'regime': {'current': regime, 'multiplier': regime_mult, 'meaning': f"Kelly adjusted to {regime_mult*100:.0f}% in {regime} regime"},
        'volatility': {'daily_pct': round(vol_data['daily_vol'] * 100, 2), 'annual_pct': vol_data['annual_vol'], 'distribution': f"Student-t (df={vol_data['student_t_df']:.1f})", 'fat_tails': vol_data['student_t_df'] < 10},
        'kelly': {'optimal_fraction': kelly_frac, 'optimal_pct': round(kelly_pct, 1), 'optimal_amount': round(kelly_amount, 2), 'your_pct': round(position_pct, 1), 'assessment': sizing, 'regime_adjusted': True},
        'win_rate_data': {'win_rate': round(win_rate * 100, 1), 'avg_win_pct': avg_win_pct, 'avg_loss_pct': avg_loss_pct, 'rr_ratio': rr_ratio, 'sample_size': win_data['sample_size'], 'source': win_data['source']},
        'monte_carlo': mc,
        'risk_metrics': {**var_cvar, 'expected_value_usd': ev_usd, 'trade_cost_pct': round(trade_cost * 100, 3), 'risk_score': risk_score},
        'recommendation': " ".join(lines),
        'timestamp': datetime.now().isoformat()
    })

def calculate_portfolio_pnl(portfolio):
    total_unrealised = 0.0; updated_trades = []
    for trade in portfolio['open_trades']:
        symbol = trade['symbol']
        try:
            price_data = get_live_price_only(symbol)
            if price_data:
                current_price = price_data['price']; entry_price = trade['entry_price']
                amount_usd = trade['amount_usd']; direction = trade['direction']
                if direction == 'LONG':
                    pnl_pct = ((current_price - entry_price) / entry_price) * 100
                else:
                    pnl_pct = ((entry_price - current_price) / entry_price) * 100
                pnl_usd = (pnl_pct / 100) * amount_usd
                trade['current_price'] = round(current_price, 4)
                trade['pnl_pct']       = round(pnl_pct, 2)
                trade['pnl_usd']       = round(pnl_usd, 2)
                total_unrealised      += pnl_usd
        except:
            trade['current_price'] = trade['entry_price']; trade['pnl_pct'] = 0.0; trade['pnl_usd'] = 0.0
        updated_trades.append(trade)
    portfolio['open_trades'] = updated_trades
    return portfolio, round(total_unrealised, 2)

# ── FASTAPI ENDPOINTS ─────────────────────────────────────

@app.get("/")
def root():
    return {"name": "ARIA Terminal", "version": "2.0.0", "status": "operational"}

@app.get("/health")
def health():
    return {"status": "healthy", "models_loaded": len(production_models), "timestamp": datetime.now().isoformat()}

@app.get("/price/{symbol}")
def get_price(symbol: str):
    symbol = symbol.upper()
    if symbol not in ['BTC','ETH','AAPL','NVDA','TSLA','GLD']:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    data = get_live_price_only(symbol)
    if not data:
        raise HTTPException(status_code=503, detail="Could not fetch data")
    return data

@app.get("/sentiment")
def get_sentiment():
    summary = {}
    for symbol, data in live_sentiment.items():
        summary[symbol] = {
            "label": data.get('sentiment_label', 'NEUTRAL'),
            "score": data.get('composite_score', 0),
            "news_count": data.get('news_count', 0),
            "fear_greed": data.get('fear_greed_value', 50)
        }
    return {"sentiment": summary, "timestamp": datetime.now().isoformat()}

@app.get("/news")
def get_news():
    return {
        "headlines":    news_cache.get('headlines', []),
        "count":        len(news_cache.get('headlines', [])),
        "last_updated": news_cache.get('last_updated', 'loading...'),
        "timestamp":    datetime.now().isoformat()
    }

@app.post("/chat")
def chat(request: ChatRequest):
    if not check_rate_limit(request.user_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")
    try:
        user_id = request.user_id or 'anonymous'
        if user_id not in conversation_history:
            conversation_history[user_id] = []
        conversation_history[user_id].append({"role": "user", "content": request.message})
        if len(conversation_history[user_id]) > 20:
            conversation_history[user_id] = conversation_history[user_id][-20:]
        history_text = ""
        if len(conversation_history[user_id]) > 1:
            history_text = "\n\nPREVIOUS CONVERSATION:\n"
            for msg in conversation_history[user_id][:-1]:
                role = "User" if msg["role"] == "user" else "ARIA"
                history_text += f"{role}: {msg['content'][:300]}\n"
        response = ask_aria(
            user_message=request.message + history_text,
            symbol=request.symbol.upper() if request.symbol else None,
            user_level=request.user_level
        )
        conversation_history[user_id].append({"role": "assistant", "content": response})
        return {"response": response, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/riskscore/{symbol}")
def get_risk_analysis(symbol: str, direction: str = 'LONG', amount_usd: float = 100.0, user_id: str = 'aria-user'):
    symbol = symbol.upper()
    if symbol not in ['BTC','ETH','AAPL','NVDA','TSLA','GLD']:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    try:
        price_data = get_live_price_only(symbol)
        if not price_data:
            raise HTTPException(status_code=503, detail="Could not fetch price")
        entry_price = price_data['price']
        signal      = price_data.get('signal', {})
        confidence  = signal.get('confidence', 0.5) if signal else 0.5
        portfolio   = get_or_create_portfolio(user_id)
        balance     = portfolio['balance']
        risk = analyse_trade_risk(symbol, direction.upper(), amount_usd, entry_price, balance, confidence)
        return risk
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/backtest/{symbol}")
def get_backtest(symbol: str):
    """
    Run full backtest on 60 days of historical data
    Uses real XGBoost model signals
    Returns win rate, Sharpe, drawdown, profit factor
    """
    symbol = symbol.upper()
    if symbol not in ['BTC','ETH','AAPL','NVDA','TSLA','GLD']:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    try:
        result = run_backtest(symbol)
        return clean_floats(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/backtest/all")
def get_all_backtests():
    """Run backtests for all 6 assets"""
    results = {}
    for symbol in ['BTC','ETH','AAPL','NVDA','TSLA','GLD']:
        try:
            results[symbol] = run_backtest(symbol)
        except Exception as e:
            results[symbol] = {'error': str(e)}
    return clean_floats(results)

@app.get("/macro")
def get_macro():
    """
    FRED leading indicators - Burry-type signals
    Yield curve, VIX, credit spreads, dollar, gold vs crypto
    """
    try:
        return clean_floats(get_macro_indicators())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/riskportfolio/{user_id}")
def get_portfolio_risk(user_id: str):
    try:
        portfolio = get_or_create_portfolio(user_id)
        closed    = portfolio['closed_trades']
        if len(closed) < 2:
            return {"message": "Need at least 2 closed trades for analytics"}
        pnl_list = [t.get('pnl_usd', 0) for t in closed]
        wins     = [p for p in pnl_list if p > 0]
        win_rate = len(wins) / len(closed)
        return clean_floats({
            'total_trades': len(closed),
            'win_rate':     round(win_rate * 100, 1),
            'total_pnl':    round(sum(pnl_list), 2),
            'timestamp':    datetime.now().isoformat()
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/paper/trade")
def open_paper_trade(request: TradeRequest):
    symbol = request.symbol.upper(); direction = request.direction.upper()
    if symbol not in ['BTC','ETH','AAPL','NVDA','TSLA','GLD']:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    if direction not in ['LONG','SHORT']:
        raise HTTPException(status_code=400, detail="Direction must be LONG or SHORT")
    if request.amount_usd < 10 or request.amount_usd > 10000:
        raise HTTPException(status_code=400, detail="Amount must be between $10 and $10,000")
    try:
        portfolios = load_paper_portfolios(); portfolio = get_or_create_portfolio(request.user_id)
        if portfolio['balance'] < request.amount_usd:
            raise HTTPException(status_code=400, detail="Insufficient balance")
        price_data = get_live_price_only(symbol)
        if not price_data:
            raise HTTPException(status_code=503, detail="Could not fetch price")
        current_price = price_data['price']; signal = price_data['signal']
        trade_id = f"{request.user_id}_{symbol}_{int(time.time())}"
        trade = {
            'trade_id': trade_id, 'symbol': symbol, 'direction': direction,
            'entry_price': round(current_price, 4), 'current_price': round(current_price, 4),
            'amount_usd': round(request.amount_usd, 2), 'pnl_pct': 0.0, 'pnl_usd': 0.0,
            'signal_at_entry': signal['signal'] if signal else 'UNKNOWN',
            'confidence_at_entry': round(signal['confidence'] * 100, 1) if signal else 0,
            'opened_at': datetime.now().isoformat(), 'status': 'OPEN'
        }
        portfolio['balance'] -= request.amount_usd
        portfolio['open_trades'].append(trade)
        portfolios[request.user_id] = portfolio
        save_paper_portfolios(portfolios)
        return {"success": True, "trade": trade, "balance": round(portfolio['balance'], 2), "message": f"Opened {direction} on {symbol} @ ${current_price:.2f}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/paper/portfolio/{user_id}")
def get_paper_portfolio(user_id: str):
    try:
        portfolio = get_or_create_portfolio(user_id)
        portfolio, unrealised_pnl = calculate_portfolio_pnl(portfolio)
        total_value  = portfolio['balance'] + sum(t['amount_usd'] + t['pnl_usd'] for t in portfolio['open_trades'])
        total_return = ((total_value - STARTING_BALANCE) / STARTING_BALANCE) * 100
        closed   = portfolio['closed_trades']
        wins     = [t for t in closed if t.get('pnl_usd', 0) > 0]
        win_rate = round(len(wins) / len(closed) * 100, 1) if closed else 0
        return {
            "user_id": user_id, "balance": round(portfolio['balance'], 2),
            "starting_balance": STARTING_BALANCE, "total_value": round(total_value, 2),
            "total_return_pct": round(total_return, 2), "unrealised_pnl": round(unrealised_pnl, 2),
            "open_trades": portfolio['open_trades'], "open_count": len(portfolio['open_trades']),
            "closed_count": len(closed), "win_rate": win_rate,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/paper/close")
def close_paper_trade(request: CloseTradeRequest):
    try:
        portfolios = load_paper_portfolios()
        if request.user_id not in portfolios:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        portfolio = portfolios[request.user_id]
        trade     = next((t for t in portfolio['open_trades'] if t['trade_id'] == request.trade_id), None)
        if not trade:
            raise HTTPException(status_code=404, detail="Trade not found")
        price_data    = get_live_price_only(trade['symbol'])
        current_price = price_data['price'] if price_data else trade['entry_price']
        entry_price = trade['entry_price']; amount_usd = trade['amount_usd']; direction = trade['direction']
        if direction == 'LONG':
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100
        pnl_usd = (pnl_pct / 100) * amount_usd
        trade['exit_price'] = round(current_price, 4); trade['pnl_pct'] = round(pnl_pct, 2)
        trade['pnl_usd'] = round(pnl_usd, 2); trade['closed_at'] = datetime.now().isoformat()
        trade['status'] = 'CLOSED'; trade['outcome'] = 'WIN' if pnl_usd > 0 else 'LOSS'
        portfolio['balance'] += amount_usd + pnl_usd
        portfolio['open_trades']   = [t for t in portfolio['open_trades'] if t['trade_id'] != request.trade_id]
        portfolio['closed_trades'].append(trade)
        portfolios[request.user_id] = portfolio
        save_paper_portfolios(portfolios)
        return {"success": True, "trade": trade, "balance": round(portfolio['balance'], 2), "pnl_usd": round(pnl_usd, 2), "outcome": trade['outcome']}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/paper/history/{user_id}")
def get_trade_history(user_id: str):
    try:
        portfolio = get_or_create_portfolio(user_id)
        closed    = portfolio['closed_trades']
        wins      = [t for t in closed if t.get('outcome') == 'WIN']
        total_pnl = sum(t.get('pnl_usd', 0) for t in closed)
        return {"user_id": user_id, "total_trades": len(closed), "wins": len(wins), "losses": len(closed) - len(wins), "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0, "total_pnl": round(total_pnl, 2), "trades": closed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/paper/leaderboard")
def get_leaderboard():
    try:
        portfolios = load_paper_portfolios(); board = []
        for user_id, portfolio in portfolios.items():
            closed = portfolio['closed_trades']
            wins   = [t for t in closed if t.get('outcome') == 'WIN']
            total_val = portfolio['balance'] + sum(t['amount_usd'] + t.get('pnl_usd', 0) for t in portfolio['open_trades'])
            ret_pct   = ((total_val - STARTING_BALANCE) / STARTING_BALANCE) * 100
            board.append({"user_id": user_id, "return_pct": round(ret_pct, 2), "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0, "trades": len(closed)})
        board.sort(key=lambda x: x['return_pct'], reverse=True)
        return {"leaderboard": board[:10], "timestamp": datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── FRONTEND ──────────────────────────────────────────────
# ── FRONTEND ──────────────────────────────────────────────
os.makedirs('static', exist_ok=True)

html_content = open('aria_terminal.html', 'r', encoding='utf-8').read() if os.path.exists('aria_terminal.html') else None

if not html_content:
    html_content = "<h1>ARIA Terminal</h1><p>Frontend loading...</p>"
else:
    html_content = html_content.replace('var API = "http://127.0.0.1:8001";', 'var API = "";')
    html_content = html_content.replace('    setTimeout(loadRiskPanel, 100);\n', '')
    print("  HTML loaded from local file")

with open('static/index.html', 'w', encoding='utf-8') as f:
    f.write(html_content)
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except:
    pass

@app.get("/terminal")
def serve_terminal():
    return FileResponse('static/index.html')

# ── WARMUP CACHE ──────────────────────────────────────────
def warmup_cache():
    time.sleep(8)
    print("Warming up price cache...")
    for symbol in ['BTC', 'ETH', 'AAPL', 'NVDA', 'TSLA', 'GLD']:
        try:
            get_live_price_only(symbol)
            print(f"  {symbol}: cached")
        except:
            pass
    print("Cache warm.")
    # Run backtests in background after warmup
    print("Running background backtests...")
    for symbol in ['BTC', 'ETH', 'AAPL', 'NVDA', 'TSLA', 'GLD']:
        try:
            run_backtest(symbol)
        except:
            pass
    print("Background backtests complete.")

threading.Thread(target=warmup_cache, daemon=True).start()

# ── START SERVER ──────────────────────────────────────────
print("\nARIA TERMINAL v2 READY")
print(f"URL: http://0.0.0.0:{PORT}")
print("="*60)
print("New endpoints:")
print("  GET /backtest/{symbol}   real win rates from 60d backtest")
print("  GET /backtest/all        all 6 assets")
print("  GET /macro               FRED leading indicators")
print("="*60)
# ── AGENT STATE ENDPOINT ──────────────────────────────────
@app.get("/agent/state")
def get_agent_state():
    try:
        state = {
            'timestamp': datetime.now().isoformat(),
            'assets': {},
            'macro': {},
            'news': [],
            'fear_greed': 50
        }

        for symbol in ['BTC', 'ETH', 'AAPL', 'NVDA', 'TSLA', 'GLD']:
            try:
                price_data = get_live_price_only(symbol)
                if price_data:
                    regime = detect_market_regime(symbol)
                    bt = _backtest_cache.get(symbol, {})
                    state['assets'][symbol] = {
                        'price':      price_data['price'],
                        'change_24h': price_data['change_24h'],
                        'rsi':        price_data['rsi'],
                        'signal':     price_data['signal']['signal'] if price_data['signal'] else 'HOLD',
                        'confidence': price_data['signal']['confidence'] if price_data['signal'] else 0.5,
                        'sentiment':  price_data['sentiment'],
                        'fear_greed': price_data['fear_greed'],
                        'regime':     regime,
                        'win_rate':   bt.get('win_rate', 52.0),
                        'sharpe':     bt.get('sharpe_ratio', 0.8),
                        'max_dd':     bt.get('max_drawdown', -15.0),
                    }
                    state['fear_greed'] = price_data['fear_greed']
            except:
                pass

        try:
            macro = get_macro_indicators()
            summary = macro.get('summary', {})
            state['macro'] = {
                'crisis_score':   summary.get('crisis_score', 0),
                'overall':        summary.get('overall', 'NORMAL'),
                'burry_signals':  summary.get('burry_signals', 0),
                'yield_curve':    macro.get('yield_curve', {}).get('signal', 'NORMAL'),
                'vix':            macro.get('vix', {}).get('current', 20),
                'vix_signal':     macro.get('vix', {}).get('signal', 'NORMAL'),
                'dollar':         macro.get('dollar_index', {}).get('signal', 'NEUTRAL'),
                'credit':         macro.get('credit_spreads', {}).get('signal', 'NORMAL'),
                'gold_vs_crypto': macro.get('gold_vs_crypto', {}).get('signal', 'NEUTRAL'),
            }
        except:
            pass

        try:
            state['news'] = [
                {'title': h['title'], 'tag': h['tag'], 'priority': h['priority']}
                for h in news_cache.get('headlines', [])[:20]
            ]
        except:
            pass

        return clean_floats(state)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── AGENT REPORT ENDPOINTS ────────────────────────────────
_agent_reports = []
AGENT_REPORTS_FILE = 'agent_reports.json'

def load_agent_reports():
    if os.path.exists(AGENT_REPORTS_FILE):
        try:
            with open(AGENT_REPORTS_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_agent_reports(reports):
    try:
        with open(AGENT_REPORTS_FILE, 'w') as f:
            json.dump(reports[:100], f, indent=2)
    except:
        pass

_agent_reports = load_agent_reports()

class AgentReport(BaseModel):
    agent_id:   str
    agent_type: str
    symbol:     Optional[str] = None
    action:     str
    confidence: float
    reasoning:  str
    pnl_today:  Optional[float] = 0.0
@app.post("/agent/report")
def receive_agent_report(report: AgentReport):
    entry = {**report.dict(), 'timestamp': datetime.now().isoformat()}
    _agent_reports.insert(0, entry)
    if len(_agent_reports) > 100:
        _agent_reports.pop()
    save_agent_reports(_agent_reports)
    return {"received": True}
@app.get("/agent/reports")
def get_agent_reports():
    return {
        "reports":   _agent_reports[:50],
        "count":     len(_agent_reports),
        "timestamp": datetime.now().isoformat()
    }

# ── KILL SWITCH ───────────────────────────────────────────
_agents_stopped = False

@app.post("/agents/stop")
def stop_agents():
    global _agents_stopped
    _agents_stopped = True
    return {"stopped": True, "message": "All agents halted"}

@app.post("/agents/resume")
def resume_agents():
    global _agents_stopped
    _agents_stopped = False
    return {"stopped": False, "message": "Agents resumed"}

@app.get("/agents/status")
def agents_status():
    return {"stopped": _agents_stopped, "timestamp": datetime.now().isoformat()
           }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")