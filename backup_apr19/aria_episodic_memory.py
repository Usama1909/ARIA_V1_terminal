import psycopg2
import logging

log = logging.getLogger()

DB = {"host":"localhost","port":5432,"dbname":"aria_db","user":"postgres","password":"aria_secure_2026"}

def get_db():
    return psycopg2.connect(**DB)

def ensure_table():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS episodic_memory (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10),
            direction VARCHAR(10),
            regime VARCHAR(20),
            fear_greed_bucket VARCHAR(10),
            nlp_label VARCHAR(20),
            fomc_signal VARCHAR(20),
            outcome VARCHAR(10),
            pnl_pct FLOAT,
            timestamp TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def recall(symbol, direction, regime, fear_greed, nlp_label='NEUTRAL', fomc='NEUTRAL'):
    """
    Query similar past episodes and return win rate + avg pnl.
    Similarity: same symbol + direction + regime + fear_greed bucket
    """
    try:
        fg_bucket = 'EXTREME_FEAR' if fear_greed < 25 else \
                    'FEAR' if fear_greed < 45 else \
                    'NEUTRAL' if fear_greed < 55 else \
                    'GREED' if fear_greed < 75 else 'EXTREME_GREED'

        conn = get_db()
        cur = conn.cursor()

        # Query similar episodes from closed_trades
        cur.execute("""
            SELECT outcome, pnl_pct FROM closed_trades
            WHERE symbol=%s
            AND direction=%s
            AND regime_at_entry=%s
            AND ABS(fear_greed_at_entry - %s) <= 15
        """, (symbol, direction, regime, fear_greed))

        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            return {'win_rate': None, 'avg_pnl': None, 'sample_size': 0, 'confidence_modifier': 0.0}

        wins = sum(1 for r in rows if r[0] == 'WIN')
        win_rate = wins / len(rows)
        avg_pnl = sum(r[1] for r in rows) / len(rows)

        # Confidence modifier based on historical win rate
        if win_rate >= 0.70 and len(rows) >= 3:
            modifier = +0.05
        elif win_rate >= 0.60 and len(rows) >= 3:
            modifier = +0.03
        elif win_rate <= 0.40 and len(rows) >= 3:
            modifier = -0.05
        elif win_rate <= 0.30 and len(rows) >= 3:
            modifier = -0.08
        else:
            modifier = 0.0

        return {
            'win_rate': round(win_rate, 3),
            'avg_pnl': round(avg_pnl, 4),
            'sample_size': len(rows),
            'confidence_modifier': modifier,
            'fg_bucket': fg_bucket
        }

    except Exception as e:
        log.warning(f"Episodic recall failed for {symbol}: {e}")
        return {'win_rate': None, 'avg_pnl': None, 'sample_size': 0, 'confidence_modifier': 0.0}

if __name__ == "__main__":
    ensure_table()
    print("Episodic memory table ready")
    # Test recall
    result = recall('NVDA', 'LONG', 'NORMAL', 23)
    print(f"NVDA LONG NORMAL F&G:23 → {result}")
