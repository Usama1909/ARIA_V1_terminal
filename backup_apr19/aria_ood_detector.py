import numpy as np
import psycopg2
import logging

log = logging.getLogger()

DB = {"host":"localhost","port":5432,"dbname":"aria_db","user":"postgres","password":"aria_secure_2026"}

FEATURE_NAMES = [
    'rsi','macd','macd_hist','volatility','bb_position','ma_distance',
    'price_change_5','price_change_10','price_change_24',
    'rsi_momentum','volume_ratio','volume_trend',
    'rsi_4h','dist_from_high','dist_from_low','range_position',
    'candle_range','candle_close_pos','upper_wick','lower_wick',
    'adx_proxy','z_score','momentum_5','momentum_10',
    'atr_pct','vpin_norm','vpin_signal'
]

FEATURE_STATS = {
    'rsi':            {'mean': 50.0,  'std': 15.0},
    'macd':           {'mean': 0.0,   'std': 100.0},
    'macd_hist':      {'mean': 0.0,   'std': 50.0},
    'volatility':     {'mean': 0.02,  'std': 0.01},
    'bb_position':    {'mean': 0.5,   'std': 0.25},
    'ma_distance':    {'mean': 0.0,   'std': 3.0},
    'price_change_5': {'mean': 0.0,   'std': 2.0},
    'price_change_10':{'mean': 0.0,   'std': 3.0},
    'price_change_24':{'mean': 0.0,   'std': 5.0},
    'rsi_momentum':   {'mean': 0.0,   'std': 5.0},
    'volume_ratio':   {'mean': 1.0,   'std': 0.5},
    'volume_trend':   {'mean': 0.0,   'std': 0.3},
    'rsi_4h':         {'mean': 50.0,  'std': 15.0},
    'dist_from_high': {'mean': 5.0,   'std': 4.0},
    'dist_from_low':  {'mean': 5.0,   'std': 4.0},
    'range_position': {'mean': 0.5,   'std': 0.25},
    'candle_range':   {'mean': 0.5,   'std': 0.4},
    'candle_close_pos':{'mean': 0.5,  'std': 0.1},
    'upper_wick':     {'mean': 0.0,   'std': 0.001},
    'lower_wick':     {'mean': 0.0,   'std': 0.001},
    'adx_proxy':      {'mean': 1.0,   'std': 0.8},
    'z_score':        {'mean': 0.0,   'std': 1.5},
    'momentum_5':     {'mean': 0.0,   'std': 0.02},
    'momentum_10':    {'mean': 0.0,   'std': 0.03},
    'atr_pct':        {'mean': 1.5,   'std': 1.0},
    'vpin_norm':      {'mean': 0.5,   'std': 0.2},
    'vpin_signal':    {'mean': 0.0,   'std': 1.0},
}

def detect_ood(symbol, features):
    try:
        if features is None:
            return {'ood_score': 0.0, 'is_ood': False, 'size_multiplier': 1.0, 'reason': 'no_features'}

        fvec = features[0]
        z_scores = []

        for i, fname in enumerate(FEATURE_NAMES):
            if fname in FEATURE_STATS:
                mean = FEATURE_STATS[fname]['mean']
                std  = FEATURE_STATS[fname]['std']
                if std > 0:
                    z = abs((fvec[i] - mean) / std)
                    z_scores.append((fname, z))

        if not z_scores:
            return {'ood_score': 0.0, 'is_ood': False, 'size_multiplier': 1.0, 'reason': 'no_stats'}

        outliers = [(f, z) for f, z in z_scores if z > 2.0]
        ood_score = len(outliers) / len(z_scores)

        if ood_score > 0.4:
            is_ood = True
            size_multiplier = 0.25
            reason = f"EXTREME_OOD: {len(outliers)}/{len(z_scores)} features outlying"
        elif ood_score > 0.25:
            is_ood = True
            size_multiplier = 0.50
            reason = f"MODERATE_OOD: {len(outliers)}/{len(z_scores)} features outlying"
        elif ood_score > 0.15:
            is_ood = False
            size_multiplier = 0.75
            reason = f"MILD_OOD: {len(outliers)}/{len(z_scores)} features outlying"
        else:
            is_ood = False
            size_multiplier = 1.0
            reason = "IN_DISTRIBUTION"

        return {
            'ood_score': round(ood_score, 3),
            'is_ood': is_ood,
            'size_multiplier': size_multiplier,
            'reason': reason,
            'outlier_features': [f for f, z in outliers[:3]]
        }

    except Exception as e:
        log.warning(f"OOD detection failed for {symbol}: {e}")
        return {'ood_score': 0.0, 'is_ood': False, 'size_multiplier': 1.0, 'reason': 'error'}

if __name__ == "__main__":
    import sys
    sys.path.insert(0, '/root')
    from aria_model_inference import build_feature_vector
    print("=== OOD Detection Test ===")
    for symbol in ['BTC','ETH','AAPL','NVDA','TSLA','GLD']:
        features = build_feature_vector(symbol)
        result = detect_ood(symbol, features)
        print(f"{symbol}: {result['reason']} | size_mult:{result['size_multiplier']} | ood_score:{result['ood_score']}")
