#!/usr/bin/env python3
"""
ARIA Model Inference — aria_model_inference.py
===============================================
Builds the 27-feature vector from price_data table and runs
the XGBoost+RF ensemble for each symbol.

Features required by quant_engine_v3:
  rsi, macd, macd_hist, volatility, bb_position, ma_distance,
  price_change_5, price_change_10, price_change_24,
  rsi_momentum, volume_ratio, volume_trend,
  rsi_4h, dist_from_high, dist_from_low, range_position,
  candle_range, candle_close_pos, upper_wick, lower_wick,
  adx_proxy, z_score, momentum_5, momentum_10,
  atr_pct, vpin_norm, vpin_signal

Returns: (direction, confidence, reasoning)
  direction  = 'LONG' | 'SHORT' | None
  confidence = float 0.0–1.0
  reasoning  = str
"""
import numpy as np
import pickle
import psycopg2
import logging
from datetime import datetime

log = logging.getLogger(__name__)

DB_CONFIG = {'host':'localhost','port':5432,'dbname':'aria_db',
             'user':'postgres','password':'aria_secure_2026'}

MODEL_CACHE = {}  # loaded once per process

def get_db():
    return psycopg2.connect(**DB_CONFIG)

def load_model(symbol):
    """Load model from pkl, cache in memory."""
    if symbol in MODEL_CACHE:
        return MODEL_CACHE[symbol]
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with open(f'/root/backup_20260401/quant_engine_v3_{symbol}.pkl','rb') as f:
                m = pickle.load(f)
        MODEL_CACHE[symbol] = m
        log.info(f"Model loaded for {symbol} | acc:{m['overall_accuracy']:.3f} wf:{m['walk_forward_acc']:.3f}")
        return m
    except Exception as e:
        log.warning(f"Model load failed for {symbol}: {e}")
        return None

def fetch_prices(symbol, n=200):
    """
    Fetch last N price ticks from price_data.
    Returns list of (price, volume, timestamp) sorted oldest first.
    For BTC/ETH (millions of ticks), sample recent window.
    """
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT price, volume, timestamp
            FROM price_data
            WHERE symbol = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """, [symbol, n])
        rows = cur.fetchall()
        cur.close(); conn.close()
        if len(rows) < 30:
            return None
        # Reverse to oldest-first
        rows = list(reversed(rows))
        prices  = np.array([float(r[0]) for r in rows])
        volumes = np.array([float(r[1]) if r[1] else 0.0 for r in rows])
        return prices, volumes
    except Exception as e:
        log.warning(f"fetch_prices failed for {symbol}: {e}")
        return None

def compute_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    deltas = np.diff(prices)
    gains  = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def compute_macd(prices, fast=12, slow=26, signal=9):
    if len(prices) < slow + signal:
        return 0.0, 0.0
    def ema(arr, span):
        alpha = 2 / (span + 1)
        result = [arr[0]]
        for p in arr[1:]:
            result.append(result[-1] * (1 - alpha) + p * alpha)
        return np.array(result)
    ema_fast = ema(prices, fast)
    ema_slow = ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    hist = macd_line[-1] - signal_line[-1]
    return macd_line[-1], hist

def compute_atr(prices, period=14):
    if len(prices) < period + 1:
        return 0.0
    # Simplified ATR using price range as proxy (no OHLC, only close)
    diffs = np.abs(np.diff(prices[-period-1:]))
    return float(np.mean(diffs))

def compute_vpin(volumes, n=50):
    """
    Simplified VPIN proxy.
    Uses volume imbalance between up and down moves as order flow proxy.
    """
    if len(volumes) < n:
        return 0.0, 0
    recent_v = volumes[-n:]
    total_v  = np.sum(recent_v)
    if total_v == 0:
        return 0.0, 0
    # Proxy: alternating buy/sell based on price direction
    return float(np.std(recent_v) / (np.mean(recent_v) + 1e-8)), 1

def build_feature_vector(symbol):
    """
    Build the exact 27-feature vector matching quant_engine_v3 training.
    Returns numpy array shape (1, 27) or None on failure.
    """
    data = fetch_prices(symbol, n=200)
    if data is None:
        return None
    prices, volumes = data
    n = len(prices)

    try:
        # ── Price change features ─────────────────────────
        price_change_5  = (prices[-1] - prices[-6])  / prices[-6]  * 100 if n >= 6  else 0.0
        price_change_10 = (prices[-1] - prices[-11]) / prices[-11] * 100 if n >= 11 else 0.0
        price_change_24 = (prices[-1] - prices[-25]) / prices[-25] * 100 if n >= 25 else 0.0

        # ── RSI ───────────────────────────────────────────
        rsi    = compute_rsi(prices, 14)
        rsi_4h = compute_rsi(prices[-50:], 14) if n >= 50 else rsi  # longer window proxy

        # RSI momentum = change in RSI over last 5 bars
        rsi_prev      = compute_rsi(prices[:-5], 14) if n >= 20 else rsi
        rsi_momentum  = rsi - rsi_prev

        # ── MACD ──────────────────────────────────────────
        macd, macd_hist = compute_macd(prices)

        # ── Volatility ────────────────────────────────────
        returns    = np.diff(prices[-26:]) / prices[-26:-1]
        volatility = float(np.std(returns)) if len(returns) > 1 else 0.0

        # ── Bollinger Bands ───────────────────────────────
        window = min(20, n)
        ma20   = np.mean(prices[-window:])
        std20  = np.std(prices[-window:])
        bb_upper    = ma20 + 2 * std20
        bb_lower    = ma20 - 2 * std20
        bb_position = (prices[-1] - bb_lower) / (bb_upper - bb_lower + 1e-8)

        # ── MA distance ───────────────────────────────────
        ma50        = np.mean(prices[-min(50, n):])
        ma_distance = (prices[-1] - ma50) / ma50 * 100

        # ── Volume features ───────────────────────────────
        vol_mean    = np.mean(volumes[-20:]) if n >= 20 else np.mean(volumes)
        vol_recent  = np.mean(volumes[-5:])  if n >= 5  else volumes[-1]
        volume_ratio = vol_recent / (vol_mean + 1e-8)
        volume_trend = (volumes[-1] - volumes[-6]) / (volumes[-6] + 1e-8) if n >= 6 else 0.0

        # ── High/Low range features ───────────────────────
        high_50      = np.max(prices[-min(50,n):])
        low_50       = np.min(prices[-min(50,n):])
        dist_from_high  = (high_50 - prices[-1]) / high_50 * 100
        dist_from_low   = (prices[-1] - low_50) / low_50  * 100
        range_position  = (prices[-1] - low_50) / (high_50 - low_50 + 1e-8)

        # ── Candle features (using consecutive ticks as proxy) ──
        candle_range    = abs(prices[-1] - prices[-2]) / prices[-2] * 100 if n >= 2 else 0.0
        candle_close_pos = 0.5  # no OHLC data, neutral
        upper_wick      = max(0, prices[-1] - max(prices[-2], prices[-1])) / (prices[-1] + 1e-8)
        lower_wick      = max(0, min(prices[-2], prices[-1]) - prices[-1]) / (prices[-1] + 1e-8)

        # ── ADX proxy (trend strength via momentum consistency) ─
        diffs  = np.diff(prices[-15:]) if n >= 15 else np.diff(prices)
        adx_proxy = float(abs(np.mean(diffs)) / (np.std(diffs) + 1e-8))

        # ── Z-score ───────────────────────────────────────
        z_score = (prices[-1] - ma20) / (std20 + 1e-8)

        # ── Momentum ─────────────────────────────────────
        momentum_5  = (prices[-1] - prices[-6])  / prices[-6]  if n >= 6  else 0.0
        momentum_10 = (prices[-1] - prices[-11]) / prices[-11] if n >= 11 else 0.0

        # ── ATR % ─────────────────────────────────────────
        atr     = compute_atr(prices)
        atr_pct = atr / prices[-1] * 100

        # ── VPIN ──────────────────────────────────────────
        vpin_norm, vpin_signal = compute_vpin(volumes)

        # ── Assemble in exact training order ──────────────
        features = np.array([[
            rsi, macd, macd_hist, volatility, bb_position, ma_distance,
            price_change_5, price_change_10, price_change_24,
            rsi_momentum, volume_ratio, volume_trend,
            rsi_4h, dist_from_high, dist_from_low, range_position,
            candle_range, candle_close_pos, upper_wick, lower_wick,
            adx_proxy, z_score, momentum_5, momentum_10,
            atr_pct, vpin_norm, vpin_signal
        ]], dtype=np.float32)

        # Replace any NaN/inf with 0
        features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)
        return features

    except Exception as e:
        log.warning(f"Feature build failed for {symbol}: {e}")
        return None

def get_model_signal(symbol):
    """
    Run the XGBoost+RF ensemble and return (direction, confidence, reasoning).
    direction  = 'LONG' | 'SHORT' | None
    confidence = float
    reasoning  = str
    """
    model = load_model(symbol)
    if model is None:
        return None, 0.52, "model_unavailable"

    features = build_feature_vector(symbol)
    if features is None:
        return None, 0.52, "features_unavailable"

    try:
        xgb = model['xgb_model']
        rf  = model['rf_model']

        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            xgb_prob = xgb.predict_proba(features)[0]
            rf_prob  = rf.predict_proba(features)[0]

        # Ensemble: 60% XGBoost, 40% RF
        ensemble_prob = 0.6 * xgb_prob + 0.4 * rf_prob

        # Classes: typically [0=SHORT, 1=HOLD, 2=LONG] or [0=DOWN, 1=UP]
        n_classes = len(ensemble_prob)

        if n_classes == 3:
            short_p, hold_p, long_p = ensemble_prob
        elif n_classes == 2:
            short_p = ensemble_prob[0]
            long_p  = ensemble_prob[1]
            hold_p  = 0.0
        else:
            return None, 0.52, f"unexpected_classes:{n_classes}"

        max_p = max(long_p, short_p)

        # Only act if model has conviction above 0.52
        if long_p > short_p and long_p > 0.52:
            direction  = 'LONG'
            confidence = float(long_p)
        elif short_p > long_p and short_p > 0.52:
            direction  = 'SHORT'
            confidence = float(short_p)
        else:
            direction  = None
            confidence = float(max_p)

        reasoning = (f"XGB:{xgb_prob.tolist()} RF:{rf_prob.tolist()} "
                     f"Ensemble→{direction} conf:{confidence:.3f} "
                     f"acc:{model['overall_accuracy']:.3f}")

        return direction, confidence, reasoning

    except Exception as e:
        log.warning(f"Model inference failed for {symbol}: {e}")
        import traceback; traceback.print_exc()
        return None, 0.52, f"inference_error:{e}"


if __name__ == '__main__':
    # Quick test
    logging.basicConfig(level=logging.INFO)
    for sym in ['BTC','ETH','GLD']:
        direction, conf, reason = get_model_signal(sym)
        print(f"{sym}: direction={direction} conf={conf:.3f}")
        print(f"  {reason[:120]}")
