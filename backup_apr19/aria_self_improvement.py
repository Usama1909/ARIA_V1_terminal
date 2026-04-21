import psycopg2
import logging
from datetime import datetime, timedelta

log = logging.getLogger()
DB = {"host":"localhost","port":5432,"dbname":"aria_db","user":"postgres","password":"aria_secure_2026"}

def get_db():
    return psycopg2.connect(**DB)

def ensure_table():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS improvement_log (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10),
            metric VARCHAR(50),
            current_value FLOAT,
            baseline_value FLOAT,
            action_taken VARCHAR(100),
            timestamp TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close(); conn.close()

def get_recent_performance(symbol, window=20):
    """Get win rate over last N trades for a symbol."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT outcome FROM closed_trades
            WHERE symbol=%s
            ORDER BY id DESC LIMIT %s
        """, [symbol, window])
        rows = cur.fetchall()
        cur.close(); conn.close()
        if len(rows) < 5:
            return None
        wins = sum(1 for r in rows if r[0] == 'WIN')
        return round(wins / len(rows), 3)
    except Exception as e:
        log.warning(f"Performance check failed for {symbol}: {e}")
        return None

def get_baseline_performance(symbol):
    """Get overall historical win rate for a symbol."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*), SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END)
            FROM closed_trades WHERE symbol=%s
        """, [symbol])
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row or not row[0] or row[0] < 5:
            return None
        return round(float(row[1]) / float(row[0]), 3)
    except Exception as e:
        log.warning(f"Baseline check failed for {symbol}: {e}")
        return None

def run_improvement_check():
    """Check all symbols for performance degradation."""
    ensure_table()
    symbols = ['BTC','ETH','AAPL','NVDA','TSLA','GLD']
    actions = []
    for symbol in symbols:
        recent = get_recent_performance(symbol, window=20)
        baseline = get_baseline_performance(symbol)
        if recent is None or baseline is None:
            continue
        degradation = baseline - recent
        if degradation > 0.15:
            action = f"RETRAIN_RECOMMENDED"
            log.warning(f"  {symbol} DEGRADATION: recent:{recent:.0%} baseline:{baseline:.0%} drop:{degradation:.0%} → {action}")
        elif degradation > 0.08:
            action = f"MONITOR_CLOSELY"
            log.info(f"  {symbol} DRIFT: recent:{recent:.0%} baseline:{baseline:.0%} drop:{degradation:.0%} → {action}")
        else:
            action = "STABLE"
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO improvement_log (symbol, metric, current_value, baseline_value, action_taken)
                VALUES (%s, %s, %s, %s, %s)
            """, [symbol, 'win_rate', recent, baseline, action])
            conn.commit()
            cur.close(); conn.close()
        except Exception as e:
            log.warning(f"Improvement log write failed: {e}")
        actions.append({'symbol': symbol, 'recent': recent, 'baseline': baseline, 'action': action})
    return actions

if __name__ == "__main__":
    print("=== Self-Improvement Check ===")
    results = run_improvement_check()
    for r in results:
        print(f"{r['symbol']}: recent:{r['recent']:.0%} baseline:{r['baseline']:.0%} action:{r['action']}")
