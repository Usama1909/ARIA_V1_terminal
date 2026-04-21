# aria_ensemble.py - ARIA Ensemble Decision Engine
# Combines XGBoost + PPO + Geo signals for final decisions
# This is the "brain" that replaces simple agent_loop decisions

import requests
import numpy as np
import time
import pickle
import os
from datetime import datetime
from stable_baselines3 import PPO
from aria_trading_env import fetch_training_data, build_features

# ── CONFIG ────────────────────────────────────────────────
ARIA_URL     = "https://web-production-548c0.up.railway.app"
SYMBOLS      = ['BTC', 'ETH', 'AAPL', 'NVDA', 'TSLA', 'GLD']
LOOP_INTERVAL= 60

# Ensemble weights
W_XGBOOST = 0.60  # XGBoost gets 60% weight (more reliable)
W_PPO     = 0.40  # PPO gets 40% weight

MIN_ENSEMBLE_CONFIDENCE = 0.62

# ── LOAD MODELS ───────────────────────────────────────────
def load_models():
    xgb_models = {}
    ppo_models = {}

    # Load XGBoost models
    for symbol in SYMBOLS:
        try:
            with open(f'quant_engine_v3_{symbol}.pkl', 'rb') as f:
                xgb_models[symbol] = pickle.load(f)
            print(f"  XGBoost {symbol}: loaded")
        except:
            print(f"  XGBoost {symbol}: not found")

    # Load PPO models
    ppo_files = {
        'BTC': 'aria_ppo_btc.zip',
        'ETH': 'aria_ppo_eth.zip',
        'AAPL': 'aria_ppo_aapl.zip',
        'NVDA': 'aria_ppo_nvda.zip',
        'TSLA': 'aria_ppo_tsla.zip',
        'GLD':  'aria_ppo_gld.zip'
    }
    for symbol, path in ppo_files.items():
        try:
            ppo_models[symbol] = PPO.load(path)
            print(f"  PPO {symbol}: loaded")
        except:
            print(f"  PPO {symbol}: not found")

    return xgb_models, ppo_models

# ── GET XGBOOST SIGNAL ────────────────────────────────────
def get_xgboost_signal(symbol, xgb_models):
    try:
        model_data = xgb_models.get(symbol)
        if not model_data:
            return None, 0.5

        df   = fetch_training_data(symbol, period='60d', interval='1h')
        feat = build_features(df)
        if len(feat) == 0:
            return None, 0.5

        feature_cols = [c for c in feat.columns if c != 'price'][:27]
        latest = feat[feature_cols].iloc[-1].values.reshape(1, -1)

        xgb_proba = model_data['xgb_model'].predict_proba(latest)
        rf_proba  = model_data['rf_model'].predict_proba(latest)
        ensemble  = (xgb_proba + rf_proba) / 2

        tp_prob = float(ensemble[0][1])
        sl_prob = float(ensemble[0][0])

        if tp_prob > sl_prob:
            return 'BUY', tp_prob
        else:
            return 'SELL', sl_prob

    except Exception as e:
        print(f"  XGBoost {symbol} error: {e}")
        return None, 0.5

# ── GET PPO SIGNAL ────────────────────────────────────────
def get_ppo_signal(symbol, ppo_models):
    try:
        model = ppo_models.get(symbol)
        if not model:
            return None, 0.5

        df   = fetch_training_data(symbol, period='60d', interval='1h')
        feat = build_features(df)
        if len(feat) < 50:
            return None, 0.5

        from aria_trading_env import ARIATradingEnv
        env  = ARIATradingEnv(feat, symbol=symbol)
        obs, _ = env.reset()

        # Fast forward to latest
        for _ in range(len(feat) - 2):
            action, _ = model.predict(obs, deterministic=True)
            obs, _, terminated, truncated, _ = env.step(action)
            if terminated or truncated:
                break

        action, _ = model.predict(obs, deterministic=True)

        if action == 1:
            return 'BUY', 0.65
        elif action == 2:
            return 'SELL', 0.65
        else:
            return 'HOLD', 0.55

    except Exception as e:
        print(f"  PPO {symbol} error: {e}")
        return None, 0.5

# ── ENSEMBLE DECISION ─────────────────────────────────────
def ensemble_decision(symbol, xgb_models, ppo_models, geo_risk):
    xgb_signal, xgb_conf = get_xgboost_signal(symbol, xgb_models)
    ppo_signal, ppo_conf = get_ppo_signal(symbol, ppo_models)

    # Convert signals to scores
    def signal_to_score(signal):
        if signal == 'BUY':   return 1.0
        elif signal == 'SELL': return -1.0
        else:                  return 0.0

    xgb_score = signal_to_score(xgb_signal) * xgb_conf if xgb_signal else 0
    ppo_score = signal_to_score(ppo_signal) * ppo_conf if ppo_signal else 0

    # Weighted ensemble
    ensemble_score = (xgb_score * W_XGBOOST) + (ppo_score * W_PPO)

    # Geo risk adjustment
    if geo_risk > 60:
        if symbol in ['BTC', 'ETH', 'NVDA', 'TSLA']:
            ensemble_score *= 0.5  # reduce risk appetite
        elif symbol == 'GLD':
            ensemble_score *= 1.3  # boost gold in high geo risk

    # Final decision
    confidence = abs(ensemble_score)
    if ensemble_score > 0.3 and confidence >= MIN_ENSEMBLE_CONFIDENCE:
        action = 'BUY'
    elif ensemble_score < -0.3 and confidence >= MIN_ENSEMBLE_CONFIDENCE:
        action = 'SELL'
    else:
        action = 'HOLD'

    agreement = xgb_signal == ppo_signal if xgb_signal and ppo_signal else False

    return action, confidence, agreement, xgb_signal, ppo_signal

# ── REPORT TO ARIA ────────────────────────────────────────
def report_to_aria(symbol, action, confidence, agreement, xgb_sig, ppo_sig):
    try:
        reasoning = (
            f"ENSEMBLE: XGBoost={xgb_sig} PPO={ppo_sig} "
            f"Agreement={'YES' if agreement else 'NO'} "
            f"Confidence={confidence:.2f}"
        )
        requests.post(f"{ARIA_URL}/agent/report", json={
            'agent_id':   f'ensemble_{symbol.lower()}',
            'agent_type': 'ENSEMBLE',
            'symbol':     symbol,
            'action':     action,
            'confidence': round(confidence, 4),
            'reasoning':  reasoning,
            'pnl_today':  0.0
        }, timeout=5)
    except:
        pass

# ── EXECUTE TRADE ─────────────────────────────────────────
def execute_trade(symbol, action):
    try:
        direction = 'LONG' if action == 'BUY' else 'SHORT'
        r = requests.post(f"{ARIA_URL}/paper/trade", json={
            'user_id':    'aria-ensemble',
            'symbol':     symbol,
            'direction':  direction,
            'amount_usd': 100.0
        }, timeout=10)
        result = r.json()
        if result.get('success'):
            print(f"  ENSEMBLE EXECUTED: {action} {symbol} @ ${result['trade']['entry_price']}")
    except Exception as e:
        print(f"  Execution error: {e}")

# ── MAIN LOOP ─────────────────────────────────────────────
def main():
    print("="*60)
    print("ARIA ENSEMBLE ENGINE - STARTING")
    print(f"XGBoost weight: {W_XGBOOST*100:.0f}%")
    print(f"PPO weight:     {W_PPO*100:.0f}%")
    print(f"Min confidence: {MIN_ENSEMBLE_CONFIDENCE}")
    print("="*60)

    xgb_models, ppo_models = load_models()
    print(f"\nXGBoost models: {len(xgb_models)}/6")
    print(f"PPO models:     {len(ppo_models)}/6")

    cycle = 0
    while True:
        cycle += 1
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Ensemble Cycle {cycle}")

        # Get geo risk from ARIA
        geo_risk = 50
        try:
            state = requests.get(f"{ARIA_URL}/agent/state", timeout=10).json()
            geo_risk = state.get('macro', {}).get('crisis_score', 50)
        except:
            pass

        print(f"  Geo risk: {geo_risk}/100")

        for symbol in SYMBOLS:
            try:
                action, confidence, agreement, xgb_sig, ppo_sig = ensemble_decision(
                    symbol, xgb_models, ppo_models, geo_risk
                )
                agreement_str = "✅ AGREE" if agreement else "❌ DISAGREE"
                print(f"  {symbol}: {action} ({confidence:.2f}) XGB={xgb_sig} PPO={ppo_sig} {agreement_str}")

                report_to_aria(symbol, action, confidence, agreement, xgb_sig, ppo_sig)

                if action in ['BUY', 'SELL'] and agreement:
                    execute_trade(symbol, action)

            except Exception as e:
                print(f"  {symbol} error: {e}")

        print(f"  Sleeping {LOOP_INTERVAL}s...")
        time.sleep(LOOP_INTERVAL)

if __name__ == "__main__":
    main()
