import logging
import psycopg2

log = logging.getLogger()
DB = {"host":"localhost","port":5432,"dbname":"aria_db","user":"postgres","password":"aria_secure_2026"}

def get_db():
    return psycopg2.connect(**DB)

CROSS_ASSET_RULES = [
    ('BTC',  'ETH',  +0.85, 'BTC leads ETH by 1 cycle'),
    ('DXY',  'GLD',  -0.70, 'DXY inverse to GLD'),
    ('DXY',  'BTC',  -0.60, 'DXY inverse to BTC'),
    ('GLD',  'AAPL', -0.30, 'Risk-off GLD means tech pressure'),
    ('BTC',  'NVDA', +0.50, 'Risk-on crypto correlates with tech'),
    ('ETH',  'BTC',  +0.80, 'ETH confirms BTC direction'),
    ('NVDA', 'AAPL', +0.60, 'Tech sector co-movement'),
]

def get_current_prices():
    """Get latest prices for all symbols."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT symbol, price FROM market_state_latest")
        rows = cur.fetchall()
        cur.close(); conn.close()
        return {r[0]: float(r[1]) for r in rows}
    except Exception as e:
        log.warning(f"Cross-asset price fetch failed: {e}")
        return {}

def evaluate(symbol, market_data):
    """
    Check cross-asset signals for a symbol.
    Returns confidence modifier based on leader asset movements.
    """
    try:
        modifier = 0.0
        active = []
        for leader, follower, correlation, reason in CROSS_ASSET_RULES:
            if follower != symbol:
                continue
            if leader not in market_data:
                continue
            leader_change = market_data[leader].get('change_24h', 0)
            if abs(leader_change) < 0.5:
                continue
            signal = correlation * (1 if leader_change > 0 else -1)
            modifier += signal * 0.03
            active.append(f"{leader}({leader_change:+.1f}%)→{follower}")
        modifier = round(max(-0.10, min(0.10, modifier)), 3)
        return {'modifier': modifier, 'active': active}
    except Exception as e:
        log.warning(f"Cross-asset eval failed for {symbol}: {e}")
        return {'modifier': 0.0, 'active': []}

if __name__ == "__main__":
    print("=== Cross-Asset Test ===")
    mock_market = {
        'BTC': {'change_24h': 2.5}, 'ETH': {'change_24h': 1.8},
        'DXY': {'change_24h': -0.8}, 'GLD': {'change_24h': 1.2},
        'NVDA': {'change_24h': 3.1}, 'AAPL': {'change_24h': 0.5}
    }
    for symbol in ['BTC','ETH','AAPL','NVDA','TSLA','GLD']:
        result = evaluate(symbol, mock_market)
        print(f"{symbol}: modifier:{result['modifier']:+.3f} chains:{result['active']}")
