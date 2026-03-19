# main.py - ARIA Terminal - Complete Deployable Version
# Combines Cells 34, 35, 36, 37, 38, 39

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
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn

# ── CONFIGURATION ─────────────────────────────────────────
PORT = int(os.environ.get('PORT', 8001))
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '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')

print("ARIA TERMINAL - STARTING UP")
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
    print(f"  Sentiment: not found - using empty")

print(f"\nModels loaded: {len(production_models)}/6")

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
            'timestamp':     now.isoformat(),
            'symbol':        symbol,
            'signal':        signal,
            'confidence':    round(confidence * 100, 1),
            'price':         round(price, 4),
            'sentiment':     sentiment,
            'rsi':           round(rsi, 1),
            'outcome':       'PENDING',
            'outcome_price': None,
            'outcome_time':  None,
            'pnl_pct':       None
        }
        history.append(entry)
        with open(SIGNAL_HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"Signal log error: {e}")

# ── FASTAPI APP ───────────────────────────────────────────
app = FastAPI(
    title="ARIA - Advanced Retail Intelligence & Analytics",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── REQUEST MODELS ────────────────────────────────────────
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
            'user_id':          user_id,
            'balance':          STARTING_BALANCE,
            'starting_balance': STARTING_BALANCE,
            'open_trades':      [],
            'closed_trades':    [],
            'created_at':       datetime.now().isoformat()
        }
        save_paper_portfolios(portfolios)
    return portfolios[user_id]

# ── CORE FUNCTIONS ────────────────────────────────────────
def get_live_features(symbol):
    yf_map = {
        'BTC': 'BTC-USD', 'ETH': 'ETH-USD',
        'AAPL': 'AAPL', 'NVDA': 'NVDA',
        'TSLA': 'TSLA', 'GLD': 'GLD'
    }
    ticker = yf.Ticker(yf_map[symbol])
    df = ticker.history(period='60d', interval='1h')
    if len(df) < 100:
        return None, None
    df = df.reset_index()
    df.columns = [c.replace(' ', '_') for c in df.columns]
    prices = df['Close']
    volume = df['Volume']
    high   = df['High']
    low    = df['Low']
    tr1 = high - low
    tr2 = abs(high - prices.shift(1))
    tr3 = abs(low  - prices.shift(1))
    atr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean()
    delta = prices.diff()
    gain  = delta.where(delta > 0, 0).rolling(14).mean()
    loss  = -delta.where(delta < 0, 0).rolling(14).mean()
    rsi   = 100 - (100 / (1 + gain / loss))
    ema_fast    = prices.ewm(span=12).mean()
    ema_slow    = prices.ewm(span=26).mean()
    macd        = ema_fast - ema_slow
    macd_signal = macd.ewm(span=9).mean()
    macd_hist   = macd - macd_signal
    ma_20    = prices.rolling(20).mean()
    std_20   = prices.rolling(20).std()
    bb_upper = ma_20 + (std_20 * 2)
    bb_lower = ma_20 - (std_20 * 2)
    ma_50    = prices.rolling(50).mean()
    volatility      = prices.pct_change().rolling(10).std()
    bb_position     = (prices - bb_lower) / (bb_upper - bb_lower)
    ma_distance     = (ma_20 - ma_50) / ma_50
    price_change_5  = prices.pct_change(5)
    price_change_10 = prices.pct_change(10)
    price_change_24 = prices.pct_change(24)
    rsi_momentum    = rsi.diff()
    volume_ratio    = volume / volume.rolling(20).mean()
    volume_trend    = volume.rolling(5).mean() / volume.rolling(20).mean()
    prices_4h = prices.rolling(4).mean()
    delta_4h  = prices_4h.diff()
    gain_4h   = delta_4h.where(delta_4h > 0, 0).rolling(14).mean()
    loss_4h   = -delta_4h.where(delta_4h < 0, 0).rolling(14).mean()
    rsi_4h    = 100 - (100 / (1 + gain_4h / loss_4h))
    high_24          = prices.rolling(24).max()
    low_24           = prices.rolling(24).min()
    dist_from_high   = (prices - high_24) / high_24
    dist_from_low    = (prices - low_24)  / low_24
    range_24         = high_24 - low_24
    range_position   = np.where(range_24 > 0, (prices - low_24) / range_24, 0.5)
    candle_range     = (high - low) / prices
    candle_close_pos = (prices - low) / (high - low + 1e-9)
    upper_wick       = (high - prices) / (high - low + 1e-9)
    lower_wick       = (prices - low)  / (high - low + 1e-9)
    adx_proxy        = abs(ma_distance) / volatility.replace(0, np.nan)
    z_score          = (prices - prices.rolling(20).mean()) / prices.rolling(20).std()
    momentum_5       = prices / prices.shift(5)  - 1
    momentum_10      = prices / prices.shift(10) - 1
    atr_pct          = atr / prices
    pct_change   = prices.pct_change()
    buy_vol_frac = np.where(
        pct_change > 0.001, 0.9,
        np.where(pct_change < -0.001, 0.1,
        np.where(pct_change > 0, 0.6,
        np.where(pct_change < 0, 0.4, 0.5)))
    )
    buy_volume  = volume * buy_vol_frac
    ofi         = abs(buy_volume - volume * (1 - buy_vol_frac))
    vpin_raw    = ofi.rolling(50).sum() / volume.rolling(50).sum()
    vpin_10     = vpin_raw.quantile(0.10)
    vpin_90     = vpin_raw.quantile(0.90)
    vpin_norm   = ((vpin_raw - vpin_10) / (vpin_90 - vpin_10 + 1e-9)).clip(0, 1)
    vpin_signal = np.where(vpin_norm > 0.7, 1, np.where(vpin_norm < 0.3, -1, 0))
    feature_names = [
        'rsi', 'macd', 'macd_hist', 'volatility',
        'bb_position', 'ma_distance', 'price_change_5',
        'price_change_10', 'price_change_24', 'rsi_momentum',
        'volume_ratio', 'volume_trend', 'rsi_4h',
        'dist_from_high', 'dist_from_low', 'range_position',
        'candle_range', 'candle_close_pos', 'upper_wick', 'lower_wick',
        'adx_proxy', 'z_score', 'momentum_5', 'momentum_10',
        'atr_pct', 'vpin_norm', 'vpin_signal'
    ]
    features = pd.DataFrame({
        'rsi': rsi, 'macd': macd, 'macd_hist': macd_hist,
        'volatility': volatility, 'bb_position': bb_position,
        'ma_distance': ma_distance, 'price_change_5': price_change_5,
        'price_change_10': price_change_10, 'price_change_24': price_change_24,
        'rsi_momentum': rsi_momentum, 'volume_ratio': volume_ratio,
        'volume_trend': volume_trend, 'rsi_4h': rsi_4h,
        'dist_from_high': dist_from_high, 'dist_from_low': dist_from_low,
        'range_position': pd.Series(range_position, index=prices.index),
        'candle_range': candle_range,
        'candle_close_pos': pd.Series(candle_close_pos.values if hasattr(candle_close_pos, 'values') else candle_close_pos, index=prices.index),
        'upper_wick': pd.Series(upper_wick.values if hasattr(upper_wick, 'values') else upper_wick, index=prices.index),
        'lower_wick': pd.Series(lower_wick.values if hasattr(lower_wick, 'values') else lower_wick, index=prices.index),
        'adx_proxy': adx_proxy, 'z_score': z_score,
        'momentum_5': momentum_5, 'momentum_10': momentum_10,
        'atr_pct': atr_pct, 'vpin_norm': vpin_norm,
        'vpin_signal': pd.Series(vpin_signal, index=prices.index)
    })
    latest        = features.dropna().iloc[-1]
    current_price = float(prices.iloc[-1])
    current_atr   = float(atr.dropna().iloc[-1])
    return latest[feature_names].values.reshape(1, -1), {
        'price':         current_price,
        'atr':           current_atr,
        'rsi':           float(rsi.dropna().iloc[-1]),
        'macd':          float(macd.dropna().iloc[-1]),
        'ma_distance':   float(ma_distance.dropna().iloc[-1]),
        'volatility':    float(volatility.dropna().iloc[-1]),
        'vpin_norm':     float(vpin_norm.dropna().iloc[-1]),
        'price_24h_ago': float(prices.iloc[-25]) if len(prices) > 25 else current_price,
    }

def get_model_signal(symbol, features_array):
    if symbol not in production_models:
        return None
    model_data = production_models[symbol]
    try:
        xgb_proba      = model_data['xgb_model'].predict_proba(features_array)
        rf_proba       = model_data['rf_model'].predict_proba(features_array)
        ensemble_proba = (xgb_proba + rf_proba) / 2
        tp_prob        = float(ensemble_proba[0][1])
        sl_prob        = float(ensemble_proba[0][0])
        return {
            'signal':         'TAKE_PROFIT' if tp_prob > sl_prob else 'STOP_LOSS',
            'confidence':     max(tp_prob, sl_prob),
            'tp_probability': tp_prob,
            'sl_probability': sl_prob
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
            'symbol':     symbol,
            'price':      round(price, 4),
            'change_24h': round(change_24h, 2),
            'rsi':        round(market_data['rsi'], 2),
            'signal':     model_signal,
            'sentiment':  sentiment.get('sentiment_label', 'NEUTRAL'),
            'fear_greed': sentiment.get('fear_greed_value', 50),
            'timestamp':  datetime.now().isoformat()
        }
        _price_cache[symbol]      = result
        _price_cache_time[symbol] = now
        return result
    except:
        return _price_cache.get(symbol, None)

def build_aria_context(symbol):
    features_array, market_data = get_live_features(symbol)
    if features_array is None:
        return None
    model_signal = get_model_signal(symbol, features_array)
    sentiment    = live_sentiment.get(symbol, {
        'sentiment_label':  'NEUTRAL',
        'composite_score':  0,
        'news_count':       0,
        'fear_greed_value': 50,
        'fear_greed_label': 'Neutral',
        'top_headlines':    []
    })
    atr      = market_data['atr']
    price    = market_data['price']
    barriers = production_models[symbol]['atr_params'] if symbol in production_models else {'tp_mult': 1.5, 'sl_mult': 1.0}
    price_24h= market_data['price_24h_ago']
    if model_signal and model_signal['confidence'] >= 0.55:
        save_signal_to_history(
            symbol     = symbol,
            signal     = model_signal['signal'],
            confidence = model_signal['confidence'],
            price      = price,
            sentiment  = sentiment.get('sentiment_label', 'NEUTRAL'),
            rsi        = market_data['rsi']
        )
    return {
        'symbol':       symbol,
        'price':        price,
        'change_24h':   ((price - price_24h) / price_24h) * 100,
        'atr':          atr,
        'atr_pct':      (atr/price)*100,
        'rsi':          market_data['rsi'],
        'macd':         market_data['macd'],
        'ma_distance':  market_data['ma_distance'],
        'volatility':   market_data['volatility'],
        'vpin_norm':    market_data['vpin_norm'],
        'tp_level':     price + (atr * barriers['tp_mult']),
        'sl_level':     price - (atr * barriers['sl_mult']),
        'model_signal': model_signal,
        'sentiment':    sentiment,
        'timestamp':    datetime.now().isoformat()
    }

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
            for url, source in RSS_FEEDS:
                try:
                    r = req.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                    root = ET.fromstring(r.content)
                    items = root.findall('.//item')[:8]
                    for item in items:
                        title = item.findtext('title', '')
                        link  = item.findtext('link', '')
                        title_lower = title.lower()
                        tag = 'markets'
                        priority = 0
                        for kw_tag, keywords in KEYWORDS.items():
                            if any(kw in title_lower for kw in keywords):
                                tag = kw_tag
                                priority = 2 if kw_tag in ['war', 'fed', 'crypto'] else 1
                                break
                        all_headlines.append({
                            'title':    title,
                            'link':     link,
                            'source':   source,
                            'tag':      tag,
                            'priority': priority
                        })
                except:
                    pass
            all_headlines.sort(key=lambda x: x['priority'], reverse=True)
            news_cache['headlines']    = all_headlines[:47]
            news_cache['last_updated'] = datetime.now().strftime('%H:%M UTC')
            print(f"  News updated: {len(all_headlines)} headlines fetched")
        except Exception as e:
            print(f"  News fetch error: {e}")
        time.sleep(300)

# Start news fetcher
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
            tag   = h.get('tag', 'news').upper()
            title = h.get('title', '')
            source= h.get('source', '')
            lines.append(f"  [{tag}] {title} ({source})")
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
            'daily_vol':    round(float(daily_vol), 4),
            'annual_vol':   round(float(annual_vol * 100), 1),
            'hourly_vol':   round(float(hourly_vol), 4),
            'student_t_df': round(float(df_t), 1),
            'is_crypto':    symbol in ['BTC', 'ETH']
        }
    except:
        defaults = {
            'BTC': 0.025, 'ETH': 0.030, 'AAPL': 0.012,
            'NVDA': 0.020, 'TSLA': 0.025, 'GLD': 0.008
        }
        return {
            'daily_vol':    defaults.get(symbol, 0.02),
            'annual_vol':   defaults.get(symbol, 0.02) * np.sqrt(252) * 100,
            'hourly_vol':   defaults.get(symbol, 0.02) / np.sqrt(24),
            'student_t_df': 4.0,
            'is_crypto':    symbol in ['BTC', 'ETH']
        }

_win_rate_cache      = {}
_win_rate_cache_time = {}

def get_backtested_win_rates(symbol):
    now = time.time()
    if symbol in _win_rate_cache and (now - _win_rate_cache_time.get(symbol, 0)) < 3600:
        return _win_rate_cache[symbol]
    try:
        history  = load_signal_history()
        resolved = [s for s in history if s['symbol'] == symbol and s['outcome'] != 'PENDING']
        if len(resolved) >= 10:
            wins     = [s for s in resolved if s['outcome'] == 'WIN']
            win_rate = len(wins) / len(resolved)
            pnl_list = [s.get('pnl_pct', 0) for s in resolved]
            avg_win  = float(np.mean([p for p in pnl_list if p > 0])) if any(p > 0 for p in pnl_list) else 1.5
            avg_loss = abs(float(np.mean([p for p in pnl_list if p < 0]))) if any(p < 0 for p in pnl_list) else 1.0
            result = {
                'win_rate': round(win_rate, 3), 'avg_win_pct': round(avg_win, 2),
                'avg_loss_pct': round(avg_loss, 2), 'sample_size': len(resolved),
                'source': 'signal_history'
            }
            _win_rate_cache[symbol]      = result
            _win_rate_cache_time[symbol] = now
            return result
    except:
        pass
    defaults = {
        'BTC':  {'win_rate': 0.52, 'avg_win_pct': 1.8, 'avg_loss_pct': 1.2},
        'ETH':  {'win_rate': 0.51, 'avg_win_pct': 2.0, 'avg_loss_pct': 1.4},
        'AAPL': {'win_rate': 0.54, 'avg_win_pct': 1.2, 'avg_loss_pct': 0.9},
        'NVDA': {'win_rate': 0.53, 'avg_win_pct': 1.5, 'avg_loss_pct': 1.1},
        'TSLA': {'win_rate': 0.51, 'avg_win_pct': 2.2, 'avg_loss_pct': 1.6},
        'GLD':  {'win_rate': 0.55, 'avg_win_pct': 0.9, 'avg_loss_pct': 0.7},
    }
    d = defaults.get(symbol, {'win_rate': 0.52, 'avg_win_pct': 1.5, 'avg_loss_pct': 1.0})
    d['sample_size'] = 0
    d['source']      = 'conservative_default'
    return d

def kelly_criterion(win_rate, avg_win_pct, avg_loss_pct, regime='SIDEWAYS', max_fraction=0.20):
    if avg_loss_pct <= 0 or win_rate <= 0 or win_rate >= 1:
        return 0.02
    b     = avg_win_pct / avg_loss_pct
    p     = win_rate
    q     = 1 - win_rate
    kelly = (b * p - q) / b
    half_kelly = kelly / 2
    multiplier = REGIME_KELLY_MULTIPLIER.get(regime, 0.75)
    return round(max(0.01, min(half_kelly * multiplier, max_fraction)), 4)

def monte_carlo_simulation(entry_price, direction, vol_data, holding_period_hours, trade_cost_pct, num_simulations=10000):
    daily_vol  = vol_data['daily_vol']
    df_t       = vol_data['student_t_df']
    hourly_vol = vol_data['hourly_vol']
    np.random.seed(None)
    hourly_returns = student_t.rvs(df=df_t, loc=0, scale=hourly_vol, size=(num_simulations, holding_period_hours))
    price_paths  = entry_price * np.exp(np.cumsum(hourly_returns, axis=1))
    final_prices = price_paths[:, -1]
    if direction == 'LONG':
        returns = (final_prices - entry_price) / entry_price * 100
    else:
        returns = (entry_price - final_prices) / entry_price * 100
    returns    = returns - (trade_cost_pct * 100)
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
    daily_vol  = vol_data['daily_vol']
    df_t       = vol_data['student_t_df']
    t_quantile = student_t.ppf(1 - confidence, df=df_t)
    var        = position_usd * daily_vol * np.sqrt(horizon_days) * abs(t_quantile)
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
        'var_95':  round(float(var), 2),
        'cvar_95': round(float(cvar), 2),
        'var_99':  round(float(position_usd * daily_vol * abs(student_t.ppf(0.01, df=df_t))), 2),
        'method':  'Student-t (fat tails)'
    }

def analyse_trade_risk(symbol, direction, amount_usd, entry_price, portfolio_balance, signal_confidence):
    regime      = detect_market_regime(symbol)
    regime_mult = REGIME_KELLY_MULTIPLIER.get(regime, 0.75)
    vol_data    = get_realised_volatility(symbol)
    win_data    = get_backtested_win_rates(symbol)
    win_rate    = win_data['win_rate']
    avg_win_pct = win_data['avg_win_pct']
    avg_loss_pct= win_data['avg_loss_pct']
    trade_cost  = total_trade_cost_pct(symbol)
    kelly_frac  = kelly_criterion(win_rate, avg_win_pct, avg_loss_pct, regime)
    kelly_amount = portfolio_balance * kelly_frac
    kelly_pct    = kelly_frac * 100
    position_pct = (amount_usd / portfolio_balance) * 100
    holding_hours = 48 if symbol in ['BTC', 'ETH'] else 24
    mc = monte_carlo_simulation(entry_price, direction, vol_data, holding_hours, trade_cost, 10000)
    var_cvar = calculate_var_cvar(amount_usd, vol_data)
    ev_pct   = (win_rate * avg_win_pct) - ((1 - win_rate) * avg_loss_pct) - (trade_cost * 100)
    ev_usd   = round((ev_pct / 100) * amount_usd, 2)
    rr_ratio = round(avg_win_pct / avg_loss_pct, 2) if avg_loss_pct > 0 else 0
    if position_pct > kelly_pct * 2:       sizing = "OVER-SIZED"
    elif position_pct > kelly_pct * 1.25:  sizing = "SLIGHTLY HIGH"
    elif position_pct <= kelly_pct:        sizing = "OPTIMAL"
    else:                                  sizing = "ACCEPTABLE"
    risk_score = min(100, int(
        (min(position_pct / max(kelly_pct, 0.1), 3) * 25) +
        (var_cvar['var_95'] / amount_usd * 100 * 25) +
        ((1 - mc['probability_profit'] / 100) * 25) +
        ((1 - signal_confidence) * 25)
    ))
    lines = []
    if regime == 'CRISIS':    lines.append("CRISIS REGIME: Reduce all position sizes significantly.")
    elif regime == 'BEAR':    lines.append("BEAR REGIME: Favour SHORT positions, reduce LONG sizes.")
    elif regime == 'EUPHORIA':lines.append("EUPHORIA REGIME: Late stage rally, reversal risk elevated.")
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
        lines.append("NOTE: Win rate based on defaults.")
    recommendation = " ".join(lines)
    return {
        'symbol': symbol, 'direction': direction, 'amount_usd': amount_usd,
        'regime': {'current': regime, 'multiplier': regime_mult, 'meaning': f"Kelly adjusted to {regime_mult*100:.0f}% in {regime} regime"},
        'volatility': {'daily_pct': round(vol_data['daily_vol'] * 100, 2), 'annual_pct': vol_data['annual_vol'], 'distribution': f"Student-t (df={vol_data['student_t_df']:.1f})", 'fat_tails': vol_data['student_t_df'] < 10},
        'kelly': {'optimal_fraction': kelly_frac, 'optimal_pct': round(kelly_pct, 1), 'optimal_amount': round(kelly_amount, 2), 'your_pct': round(position_pct, 1), 'assessment': sizing, 'regime_adjusted': True},
        'win_rate_data': {'win_rate': round(win_rate * 100, 1), 'avg_win_pct': avg_win_pct, 'avg_loss_pct': avg_loss_pct, 'rr_ratio': rr_ratio, 'sample_size': win_data['sample_size'], 'source': win_data['source']},
        'monte_carlo': mc,
        'risk_metrics': {**var_cvar, 'expected_value_usd': ev_usd, 'trade_cost_pct': round(trade_cost * 100, 3), 'risk_score': risk_score},
        'recommendation': recommendation,
        'timestamp': datetime.now().isoformat()
    }

def calculate_portfolio_pnl(portfolio):
    total_unrealised = 0.0
    updated_trades   = []
    for trade in portfolio['open_trades']:
        symbol = trade['symbol']
        try:
            price_data = get_live_price_only(symbol)
            if price_data:
                current_price = price_data['price']
                entry_price   = trade['entry_price']
                amount_usd    = trade['amount_usd']
                direction     = trade['direction']
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
            trade['current_price'] = trade['entry_price']
            trade['pnl_pct']       = 0.0
            trade['pnl_usd']       = 0.0
        updated_trades.append(trade)
    portfolio['open_trades'] = updated_trades
    return portfolio, round(total_unrealised, 2)

# ── FASTAPI ENDPOINTS ─────────────────────────────────────

@app.get("/")
def root():
    return {"name": "ARIA Terminal", "version": "1.0.0", "status": "operational"}

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
            "label":      data.get('sentiment_label', 'NEUTRAL'),
            "score":      data.get('composite_score', 0),
            "news_count": data.get('news_count', 0),
            "fear_greed": data.get('fear_greed_value', 50)
        }
    return {"sentiment": summary, "timestamp": datetime.now().isoformat()}

@app.get("/news")
def get_news():
    return {
        "headlines":     news_cache.get('headlines', []),
        "count":         len(news_cache.get('headlines', [])),
        "last_updated":  news_cache.get('last_updated', 'loading...'),
        "timestamp":     datetime.now().isoformat()
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
        return clean_floats(risk)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/riskportfolio/{user_id}")
def get_portfolio_risk(user_id: str):
    try:
        portfolio = get_or_create_portfolio(user_id)
        closed    = portfolio['closed_trades']
        if len(closed) < 2:
            return {"message": "Need at least 2 closed trades for analytics"}
        returns   = [t.get('pnl_pct', 0) for t in closed]
        pnl_list  = [t.get('pnl_usd', 0) for t in closed]
        wins      = [p for p in pnl_list if p > 0]
        losses    = [p for p in pnl_list if p < 0]
        equity    = [10000.0]
        for t in closed:
            equity.append(equity[-1] + t.get('pnl_usd', 0))
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
    symbol    = request.symbol.upper()
    direction = request.direction.upper()
    if symbol not in ['BTC','ETH','AAPL','NVDA','TSLA','GLD']:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    if direction not in ['LONG','SHORT']:
        raise HTTPException(status_code=400, detail="Direction must be LONG or SHORT")
    if request.amount_usd < 10 or request.amount_usd > 10000:
        raise HTTPException(status_code=400, detail="Amount must be between $10 and $10,000")
    try:
        portfolios = load_paper_portfolios()
        portfolio  = get_or_create_portfolio(request.user_id)
        if portfolio['balance'] < request.amount_usd:
            raise HTTPException(status_code=400, detail=f"Insufficient balance")
        price_data = get_live_price_only(symbol)
        if not price_data:
            raise HTTPException(status_code=503, detail="Could not fetch price")
        current_price = price_data['price']
        signal        = price_data['signal']
        trade_id      = f"{request.user_id}_{symbol}_{int(time.time())}"
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
            "closed_count": len(closed), "win_rate": win_rate, "timestamp": datetime.now().isoformat()
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
        entry_price   = trade['entry_price']
        amount_usd    = trade['amount_usd']
        direction     = trade['direction']
        if direction == 'LONG':
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100
        pnl_usd = (pnl_pct / 100) * amount_usd
        trade['exit_price']  = round(current_price, 4)
        trade['pnl_pct']     = round(pnl_pct, 2)
        trade['pnl_usd']     = round(pnl_usd, 2)
        trade['closed_at']   = datetime.now().isoformat()
        trade['status']      = 'CLOSED'
        trade['outcome']     = 'WIN' if pnl_usd > 0 else 'LOSS'
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
        portfolios = load_paper_portfolios()
        board      = []
        for user_id, portfolio in portfolios.items():
            closed    = portfolio['closed_trades']
            wins      = [t for t in closed if t.get('outcome') == 'WIN']
            total_val = portfolio['balance'] + sum(t['amount_usd'] + t.get('pnl_usd', 0) for t in portfolio['open_trades'])
            ret_pct   = ((total_val - STARTING_BALANCE) / STARTING_BALANCE) * 100
            board.append({"user_id": user_id, "return_pct": round(ret_pct, 2), "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0, "trades": len(closed)})
        board.sort(key=lambda x: x['return_pct'], reverse=True)
        return {"leaderboard": board[:10], "timestamp": datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── FRONTEND ──────────────────────────────────────────────
os.makedirs('static', exist_ok=True)

# Write the HTML file
html_content = open('aria_terminal.html', 'r', encoding='utf-8').read() if os.path.exists('aria_terminal.html') else "<h1>ARIA Terminal</h1>"
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
    symbols = ['BTC', 'ETH', 'AAPL', 'NVDA', 'TSLA', 'GLD']
    print("Warming up price cache...")
    for symbol in symbols:
        try:
            get_live_price_only(symbol)
            print(f"  {symbol}: cached")
        except:
            pass
    print("Cache warm.")

threading.Thread(target=warmup_cache, daemon=True).start()

# ── START SERVER ──────────────────────────────────────────
print("\nARIA TERMINAL READY")
print(f"URL: http://0.0.0.0:{PORT}")
print("="*60)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")