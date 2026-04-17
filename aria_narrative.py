import psycopg2
import logging

log = logging.getLogger()
DB = {"host":"localhost","port":5432,"dbname":"aria_db","user":"postgres","password":"aria_secure_2026"}

def get_db():
    return psycopg2.connect(**DB)

def get_current_narrative():
    """Fetch latest world state narrative."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT narrative, narrative_detail, macro_phase, risk_appetite
            FROM world_state ORDER BY id DESC LIMIT 1
        """)
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row:
            return None
        return {'narrative': row[0], 'detail': row[1], 'macro_phase': row[2], 'risk_appetite': row[3]}
    except Exception as e:
        log.warning(f"Narrative fetch failed: {e}")
        return None

def get_narrative_modifier(symbol, direction):
    """Apply narrative context to confidence."""
    state = get_current_narrative()
    if not state:
        return 0.0, "NO_NARRATIVE"

    narrative = state['narrative']
    risk = state['risk_appetite']
    modifier = 0.0
    reason = narrative

    NARRATIVE_RULES = {
        'SAFE_HAVEN_DEMAND': {'GLD': +0.06, 'BTC': -0.04, 'ETH': -0.04, 'NVDA': -0.03},
        'AI_OPTIMISM':       {'NVDA': +0.06, 'AAPL': +0.04, 'BTC': +0.03},
        'CRYPTO_FEAR':       {'BTC': -0.06, 'ETH': -0.06},
        'INFLATION_FEAR':    {'GLD': +0.06, 'BTC': +0.03, 'TSLA': -0.03},
        'LIQUIDITY_CRUNCH':  {'BTC': -0.05, 'ETH': -0.05, 'NVDA': -0.04},
        'CONSOLIDATION':     {},
    }

    asset_mod = NARRATIVE_RULES.get(narrative, {}).get(symbol, 0.0)

    if direction == 'LONG':
        modifier = asset_mod
    else:
        modifier = -asset_mod

    if risk == 'LOW' and direction == 'LONG' and symbol not in ['GLD']:
        modifier -= 0.02

    return round(modifier, 3), f"NARRATIVE:{narrative}"

if __name__ == "__main__":
    print("=== Narrative Engine Test ===")
    state = get_current_narrative()
    print(f"Current: {state}")
    for symbol in ['BTC','ETH','AAPL','NVDA','TSLA','GLD']:
        mod, reason = get_narrative_modifier(symbol, 'LONG')
        print(f"{symbol} LONG: modifier:{mod:+.3f} reason:{reason}")
