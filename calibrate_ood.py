#!/usr/bin/env python3
"""
OOD Calibration Script
Calculates real feature statistics from actual price data
Updates aria_ood_detector.py with calibrated values
"""
import sys
sys.path.insert(0, '/root')
from aria_model_inference import build_feature_vector
import numpy as np
import psycopg2
import json

DB = {'host':'localhost','port':5432,'dbname':'aria_db','user':'postgres','password':'aria_secure_2026'}
SYMBOLS = ['BTC', 'ETH', 'AAPL', 'NVDA', 'TSLA', 'GLD']
FEATURE_NAMES = [
    'rsi','macd','macd_hist','volatility','bb_position','ma_distance',
    'price_change_5','price_change_10','price_change_24',
    'rsi_momentum','volume_ratio','volume_trend',
    'rsi_4h','dist_from_high','dist_from_low','range_position',
    'candle_range','candle_close_pos','upper_wick','lower_wick',
    'adx_proxy','z_score','momentum_5','momentum_10',
    'atr_pct','vpin_norm','vpin_signal'
]

print("Collecting feature vectors for calibration...")
all_features = []

for symbol in SYMBOLS:
    print(f"Processing {symbol}...")
    # Sample multiple times to get distribution
    for _ in range(10):
        try:
            fv = build_feature_vector(symbol)
            if fv is not None:
                all_features.append(fv.flatten())
        except:
            pass

if len(all_features) < 5:
    print("Not enough data — keeping defaults")
    exit()

arr = np.array(all_features)
print(f"Collected {len(arr)} feature vectors")

# Calculate statistics
stats = {}
for i, name in enumerate(FEATURE_NAMES):
    if i < arr.shape[1]:
        mean = float(np.mean(arr[:, i]))
        std = float(np.std(arr[:, i]))
        if std < 1e-8:
            std = 1.0
        stats[name] = {'mean': round(mean, 4), 'std': round(std, 4)}
        print(f"  {name}: mean={mean:.4f} std={std:.4f}")

# Save to DB for reference
conn = psycopg2.connect(**DB)
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS ood_calibration (
        id SERIAL PRIMARY KEY,
        feature_stats JSONB,
        sample_count INTEGER,
        calibrated_at TIMESTAMP DEFAULT NOW()
    )
""")
cur.execute("INSERT INTO ood_calibration (feature_stats, sample_count) VALUES (%s, %s)",
           [json.dumps(stats), len(arr)])
conn.commit(); cur.close(); conn.close()

print(f"\nCalibration complete! {len(stats)} features calibrated.")
print("Updating aria_ood_detector.py...")

# Update the FEATURE_STATS in aria_ood_detector.py
with open('/root/aria_ood_detector.py', 'r') as f:
    content = f.read()

# Build new FEATURE_STATS string
new_stats = "FEATURE_STATS = {\n"
for name, s in stats.items():
    new_stats += f"    '{name}': {{'mean': {s['mean']}, 'std': {s['std']}}},\n"
new_stats += "}"

# Find and replace FEATURE_STATS block
import re
content = re.sub(r'FEATURE_STATS = \{.*?\}', new_stats, content, flags=re.DOTALL)

with open('/root/aria_ood_detector.py', 'w') as f:
    f.write(content)

print("aria_ood_detector.py updated with real statistics!")
