import psycopg2
import logging

log = logging.getLogger()
DB = {"host":"localhost","port":5432,"dbname":"aria_db","user":"postgres","password":"aria_secure_2026"}

def get_db():
    return psycopg2.connect(**DB)

# Known macro causal chains
# Format: (condition, affected_symbol, direction, confidence, reasoning)
CAUSAL_CHAINS = [
    # Fed / FOMC chains
    ('FOMC_HAWKISH', 'BTC',  'SHORT', 0.06, 'Hawkish Fed → risk off → crypto sells'),
    ('FOMC_HAWKISH', 'ETH',  'SHORT', 0.06, 'Hawkish Fed → risk off → crypto sells'),
    ('FOMC_HAWKISH', 'NVDA', 'SHORT', 0.05, 'Hawkish Fed → rates up → tech multiple compression'),
    ('FOMC_HAWKISH', 'TSLA', 'SHORT', 0.05, 'Hawkish Fed → rates up → growth stock pressure'),
    ('FOMC_HAWKISH', 'GLD',  'SHORT', 0.03, 'Hawkish Fed → real rates up → gold headwind'),
    ('FOMC_DOVISH',  'BTC',  'LONG',  0.06, 'Dovish Fed → liquidity → crypto rallies'),
    ('FOMC_DOVISH',  'GLD',  'LONG',  0.05, 'Dovish Fed → inflation fear → gold bid'),
    ('FOMC_DOVISH',  'NVDA', 'LONG',  0.04, 'Dovish Fed → growth multiple expansion'),
    # DXY chains
    ('DXY_RISING',   'BTC',  'SHORT', 0.05, 'Strong dollar → risk off → BTC pressure'),
    ('DXY_RISING',   'GLD',  'SHORT', 0.05, 'Strong dollar → gold headwind'),
    ('DXY_FALLING',  'BTC',  'LONG',  0.05, 'Weak dollar → crypto bid'),
    ('DXY_FALLING',  'GLD',  'LONG',  0.06, 'Weak dollar → gold tailwind'),
    # Fear & Greed chains
    ('EXTREME_FEAR', 'GLD',  'LONG',  0.07, 'Extreme fear → safe haven demand → GLD'),
    ('EXTREME_FEAR', 'BTC',  'SHORT', 0.04, 'Extreme fear → crypto selling'),
    ('EXTREME_GREED','BTC',  'LONG',  0.05, 'Extreme greed → crypto momentum'),
    ('EXTREME_GREED','GLD',  'SHORT', 0.04, 'Greed → risk on → gold sells off'),
    # Regime chains
    ('CRISIS',       'GLD',  'LONG',  0.08, 'Crisis regime → flight to safety'),
    ('CRISIS',       'BTC',  'SHORT', 0.06, 'Crisis regime → risk assets sell'),
    ('CRISIS',       'NVDA', 'SHORT', 0.05, 'Crisis regime → tech sells off'),
]

def get_dxy_signal():
    """Check if DXY is rising or falling based on recent price data."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT price FROM price_data 
            WHERE symbol='DXY' 
            ORDER BY timestamp DESC LIMIT 10
        """)
        rows = cur.fetchall()
        cur.close(); conn.close()
        if len(rows) < 5:
            return 'NEUTRAL'
        recent = float(rows[0][0])
        older  = float(rows[-1][0])
        change = (recent - older) / older * 100
        if change > 0.3:   return 'DXY_RISING'
        elif change < -0.3: return 'DXY_FALLING'
        else:               return 'NEUTRAL'
    except Exception as e:
        log.warning(f"DXY signal failed: {e}")
        return 'NEUTRAL'

def evaluate(symbol, fomc_signal='NEUTRAL', fear_greed=50, regime='NORMAL'):
    """
    Evaluate all causal chains for a symbol.
    Returns net confidence modifier and list of active chains.
    """
    try:
        dxy = get_dxy_signal()
        fg_condition = 'EXTREME_FEAR' if fear_greed < 25 else 'EXTREME_GREED' if fear_greed > 75 else 'NEUTRAL'
        active_conditions = set()
        if fomc_signal == 'HAWKISH': active_conditions.add('FOMC_HAWKISH')
        if fomc_signal == 'DOVISH':  active_conditions.add('FOMC_DOVISH')
        if dxy == 'DXY_RISING':      active_conditions.add('DXY_RISING')
        if dxy == 'DXY_FALLING':     active_conditions.add('DXY_FALLING')
        if fg_condition != 'NEUTRAL': active_conditions.add(fg_condition)
        if regime == 'CRISIS':        active_conditions.add('CRISIS')
        long_modifier  = 0.0
        short_modifier = 0.0
        active_chains  = []
        for condition, sym, direction, conf, reasoning in CAUSAL_CHAINS:
            if sym == symbol and condition in active_conditions:
                if direction == 'LONG':
                    long_modifier += conf
                else:
                    short_modifier += conf
                active_chains.append(f"{condition}→{direction}({conf:+.2f})")
        net_modifier = long_modifier - short_modifier
        return {
            'net_modifier': round(net_modifier, 3),
            'long_pressure': round(long_modifier, 3),
            'short_pressure': round(short_modifier, 3),
            'active_chains': active_chains,
            'dxy_signal': dxy
        }
    except Exception as e:
        log.warning(f"Causal graph eval failed for {symbol}: {e}")
        return {'net_modifier': 0.0, 'long_pressure': 0.0, 'short_pressure': 0.0, 'active_chains': [], 'dxy_signal': 'NEUTRAL'}

if __name__ == "__main__":
    print("=== Causal Graph Test ===")
    for symbol in ['BTC','ETH','AAPL','NVDA','TSLA','GLD']:
        result = evaluate(symbol, fomc_signal='HAWKISH', fear_greed=23, regime='CRISIS')
        print(f"{symbol}: net:{result['net_modifier']:+.3f} chains:{result['active_chains']}")
