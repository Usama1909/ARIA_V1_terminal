import psycopg2
import numpy as np
import logging

log = logging.getLogger()
DB = {"host":"localhost","port":5432,"dbname":"aria_db","user":"postgres","password":"aria_secure_2026"}

def get_db():
    return psycopg2.connect(**DB)

def get_price_volume(symbol, n=50):
    """Fetch recent price and volume data."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT price, volume FROM price_data
            WHERE symbol=%s
            ORDER BY timestamp DESC LIMIT %s
        """, [symbol, n])
        rows = cur.fetchall()
        cur.close(); conn.close()
        if len(rows) < 10:
            return None, None
        prices  = np.array([float(r[0]) for r in reversed(rows)])
        volumes = np.array([float(r[1]) if r[1] else 1.0 for r in reversed(rows)])
        return prices, volumes
    except Exception as e:
        log.warning(f"Microstructure data fetch failed for {symbol}: {e}")
        return None, None

def compute_microstructure(symbol):
    """
    Compute microstructure signals:
    - Price acceleration: is momentum accelerating or decelerating?
    - Volume imbalance: buying vs selling pressure
    - Tick direction: consecutive up/down moves
    """
    prices, volumes = get_price_volume(symbol)
    if prices is None:
        return {'signal': 'NEUTRAL', 'modifier': 0.0, 'reason': 'no_data'}

    try:
        # Price acceleration
        returns = np.diff(prices) / prices[:-1]
        recent_ret  = np.mean(returns[-5:])
        earlier_ret = np.mean(returns[-15:-5])
        acceleration = recent_ret - earlier_ret

        # Volume imbalance — higher volume on up moves = buying pressure
        up_moves = [volumes[i] for i in range(1, len(prices)) if prices[i] > prices[i-1]]
        down_moves = [volumes[i] for i in range(1, len(prices)) if prices[i] < prices[i-1]]
        up_vol   = np.mean(up_moves) if up_moves else 1.0
        down_vol = np.mean(down_moves) if down_moves else 1.0
        vol_imbalance = (up_vol - down_vol) / (up_vol + down_vol + 1e-8)

        # Tick direction — last 10 ticks
        ticks = [1 if prices[i] > prices[i-1] else -1 for i in range(1, len(prices))]
        tick_score = np.mean(ticks[-10:])

        # Combine signals
        micro_score = (acceleration * 10) + (vol_imbalance * 0.5) + (tick_score * 0.3)

        if micro_score > 0.3:
            signal = 'BULLISH'
            modifier = +0.04
        elif micro_score < -0.3:
            signal = 'BEARISH'
            modifier = -0.04
        else:
            signal = 'NEUTRAL'
            modifier = 0.0

        return {
            'signal': signal,
            'modifier': round(modifier, 3),
            'acceleration': round(float(acceleration), 6),
            'vol_imbalance': round(float(vol_imbalance), 3),
            'tick_score': round(float(tick_score), 3),
            'micro_score': round(float(micro_score), 3)
        }
    except Exception as e:
        log.warning(f"Microstructure compute failed for {symbol}: {e}")
        return {'signal': 'NEUTRAL', 'modifier': 0.0, 'reason': 'compute_error'}

if __name__ == "__main__":
    print("=== Microstructure Test ===")
    for symbol in ['BTC','ETH','AAPL','NVDA','TSLA','GLD']:
        result = compute_microstructure(symbol)
        print(f"{symbol}: {result['signal']} modifier:{result['modifier']:+.3f} micro_score:{result.get('micro_score', 0):+.3f}")
