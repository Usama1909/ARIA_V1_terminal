import psycopg2
import logging
import json
from datetime import datetime

log = logging.getLogger()
DB = {"host":"localhost","port":5432,"dbname":"aria_db","user":"postgres","password":"aria_secure_2026"}

def get_db():
    return psycopg2.connect(**DB)

MIN_SAMPLE = 30
MIN_WIN_RATE = 0.60

def ensure_table():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hypothesis_rules (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10),
            direction VARCHAR(10),
            regime VARCHAR(20),
            condition_key VARCHAR(50),
            win_rate FLOAT,
            sample_size INTEGER,
            avg_pnl FLOAT,
            status VARCHAR(20) DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close(); conn.close()

def get_adaptive_threshold(sample_count):
    if sample_count < 30:    return None
    elif sample_count < 100: return 0.65
    elif sample_count < 500: return 0.62
    else:                    return 0.60

def generate_hypotheses():
    """Scan closed trades and generate validated hypotheses."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT symbol, direction, regime_at_entry,
                   COUNT(*) as total,
                   SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) as wins,
                   AVG(pnl_pct) as avg_pnl
            FROM closed_trades
            GROUP BY symbol, direction, regime_at_entry
            HAVING COUNT(*) >= %s
            ORDER BY wins DESC
        """, [MIN_SAMPLE])
        rows = cur.fetchall()
        hypotheses = []
        for r in rows:
            symbol, direction, regime, total, wins, avg_pnl = r
            win_rate = wins / total
            threshold = get_adaptive_threshold(total)
            if threshold is None or win_rate < threshold:
                continue
            hypotheses.append({
                    'symbol': symbol,
                    'direction': direction,
                    'regime': regime,
                    'win_rate': round(win_rate, 3),
                    'sample_size': total,
                    'avg_pnl': round(float(avg_pnl), 4)
                })
        cur.close(); conn.close()
        return hypotheses
    except Exception as e:
        log.warning(f"Hypothesis generation failed: {e}")
        return []

def apply_hypothesis(symbol, direction, regime):
    """Check if current trade matches a validated hypothesis."""
    try:
        hypotheses = generate_hypotheses()
        for h in hypotheses:
            if h['symbol'] == symbol and h['direction'] == direction and h['regime'] == regime:
                if h['win_rate'] >= 0.85 and h['sample_size'] >= MIN_SAMPLE:
                    modifier = +0.05
                elif h['win_rate'] >= MIN_WIN_RATE and h['sample_size'] >= MIN_SAMPLE:
                    modifier = +0.03
                else:
                    continue
                log.info(f"  {symbol} HYPOTHESIS: wr:{h['win_rate']:.0%} n:{h['sample_size']} → modifier:{modifier:+.2f}")
                return modifier, f"HYP_MATCH(wr:{h['win_rate']:.0%},n:{h['sample_size']})"
        return 0.0, "NO_HYPOTHESIS"
    except Exception as e:
        log.warning(f"Hypothesis apply failed: {e}")
        return 0.0, "ERROR"

if __name__ == "__main__":
    ensure_table()
    print("=== Hypothesis Engine Test ===")
    hypotheses = generate_hypotheses()
    print(f"Generated {len(hypotheses)} validated hypotheses:")
    for h in hypotheses:
        print(f"  {h['symbol']} {h['direction']} {h['regime']}: wr:{h['win_rate']:.0%} n:{h['sample_size']} avg_pnl:{h['avg_pnl']:+.3f}")
    print("\n=== Apply Test ===")
    for symbol, direction, regime in [('NVDA','LONG','NORMAL'),('BTC','LONG','CRISIS'),('GLD','LONG','NORMAL')]:
        mod, reason = apply_hypothesis(symbol, direction, regime)
        print(f"{symbol} {direction} {regime}: modifier:{mod:+.2f} reason:{reason}")
