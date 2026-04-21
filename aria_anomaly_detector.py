#!/usr/bin/env python3
"""
ARIA Anomaly Detector — aria_anomaly_detector.py
=================================================
Runs every 60s. Monitors all data feeds and system state.
Writes anomalies and system mode to DB.
Agent loop reads system_mode before making decisions.

Modes:
  NORMAL   — all feeds healthy, full trading
  DEGRADED — some feeds stale/missing, reduced trading
  SAFE     — critical feeds down, no new trades, exits only

Self-healing:
  Each anomaly has a severity and auto-clears when resolved.
  Mode downgrades automatically when issues resolve.
"""
import time, json, logging, psycopg2
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [ANOMALY] %(message)s')
log = logging.getLogger()

DB_CONFIG = {'host':'localhost','port':5432,'dbname':'aria_db',
             'user':'postgres','password':'aria_secure_2026'}

# Staleness thresholds in seconds
THRESHOLDS = {
    'market_state': {
        'BTC':  120,   # 2 mins — crypto updates every 60s
        'ETH':  120,
        'AAPL': 28800,  # 8 hours — stocks only update during market hours
        'NVDA': 28800,
        'TSLA': 28800,
        'GLD':  28800,
        'DXY':  28800, # 8 hours — macro index
    },
    'sentiment':  600,   # 10 mins
    'world_state': 1800, # 30 mins
    'price_data': {
        'BTC':  120,
        'ETH':  120,
        'AAPL': 300,
        'NVDA': 300,
        'TSLA': 300,
        'GLD':  300,
        'DXY':  28800,
    }
}

# Anomaly severity weights
SEVERITY = {
    'market_stale_critical':   10,  # BTC/ETH stale
    'market_stale_warning':     5,  # stocks stale
    'sentiment_stale':          8,
    'world_stale':              3,
    'price_impossible':        10,  # zero or negative price
    'sentiment_impossible':     8,  # score out of range
    'feed_missing':             9,  # symbol completely absent
}

def get_db():
    return psycopg2.connect(**DB_CONFIG)

def ensure_tables():
    """Create anomaly tables if not exist."""
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_anomalies (
            id          SERIAL PRIMARY KEY,
            anomaly_id  VARCHAR(100) NOT NULL,
            severity    INTEGER DEFAULT 0,
            description TEXT,
            value       FLOAT,
            resolved    BOOLEAN DEFAULT FALSE,
            created_at  TIMESTAMP DEFAULT NOW(),
            resolved_at TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_health (
            id          SERIAL PRIMARY KEY,
            mode        VARCHAR(20) NOT NULL,
            score       INTEGER DEFAULT 100,
            anomaly_count INTEGER DEFAULT 0,
            details     JSONB,
            updated_at  TIMESTAMP DEFAULT NOW()
        )
    """)
    # Add index on anomaly_id for fast lookups
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_anomaly_id
        ON system_anomalies (anomaly_id, resolved)
    """)
    conn.commit(); cur.close(); conn.close()

def check_market_state():
    """Check market_state_latest for staleness and impossible values."""
    anomalies = []
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT symbol, price, change_24h, updated_at
            FROM market_state_latest
        """)
        rows = cur.fetchall()
        cur.close(); conn.close()

        found_symbols = set()
        for row in rows:
            symbol, price, change, updated_at = row
            found_symbols.add(symbol)
            age = (datetime.utcnow() - updated_at.replace(tzinfo=None)).total_seconds()
            threshold = THRESHOLDS['market_state'].get(symbol, 300)

            # Staleness check
            if age > threshold * 3:  # 3x threshold = critical
                is_critical = symbol in ['BTC', 'ETH']
                anomalies.append({
                    'id': f'market_stale_{symbol}',
                    'severity': SEVERITY['market_stale_critical'] if is_critical else SEVERITY['market_stale_warning'],
                    'description': f'{symbol} market data stale for {age/60:.1f} mins (threshold {threshold/60:.0f} mins)',
                    'value': age
                })
            elif age > threshold:
                anomalies.append({
                    'id': f'market_warn_{symbol}',
                    'severity': 2,
                    'description': f'{symbol} market data aging: {age/60:.1f} mins',
                    'value': age
                })

            # Impossible value check
            if price <= 0:
                anomalies.append({
                    'id': f'market_zero_{symbol}',
                    'severity': SEVERITY['price_impossible'],
                    'description': f'{symbol} price is zero or negative: {price}',
                    'value': float(price)
                })

            # Sanity check: change_24h should be between -50% and +50%
            if abs(float(change)) > 50:
                anomalies.append({
                    'id': f'market_change_insane_{symbol}',
                    'severity': 6,
                    'description': f'{symbol} change_24h suspicious: {change:.2f}%',
                    'value': float(change)
                })

        # Check for missing symbols
        expected = {'BTC','ETH','AAPL','NVDA','TSLA','GLD'}
        missing  = expected - found_symbols
        for sym in missing:
            anomalies.append({
                'id': f'market_missing_{sym}',
                'severity': SEVERITY['feed_missing'],
                'description': f'{sym} completely missing from market_state_latest',
                'value': 0
            })

    except Exception as e:
        anomalies.append({
            'id': 'market_db_error',
            'severity': 10,
            'description': f'market_state_latest DB read failed: {e}',
            'value': 0
        })
    return anomalies

def check_sentiment():
    """Check sentiment_latest for staleness and impossible values."""
    anomalies = []
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT score, fear_greed, updated_at FROM sentiment_latest ORDER BY updated_at DESC LIMIT 1")
        row = cur.fetchone(); cur.close(); conn.close()

        if not row:
            anomalies.append({
                'id': 'sentiment_missing',
                'severity': SEVERITY['feed_missing'],
                'description': 'sentiment_latest table is empty',
                'value': 0
            })
            return anomalies

        score, fg, updated_at = row
        age = (datetime.utcnow() - updated_at.replace(tzinfo=None)).total_seconds()

        if age > THRESHOLDS['sentiment']:
            anomalies.append({
                'id': 'sentiment_stale',
                'severity': SEVERITY['sentiment_stale'],
                'description': f'Sentiment stale for {age/60:.1f} mins',
                'value': age
            })

        if abs(float(score)) > 100:
            anomalies.append({
                'id': 'sentiment_score_insane',
                'severity': SEVERITY['sentiment_impossible'],
                'description': f'Sentiment score out of range: {score}',
                'value': float(score)
            })

        if not (0 <= int(fg) <= 100):
            anomalies.append({
                'id': 'sentiment_fg_insane',
                'severity': SEVERITY['sentiment_impossible'],
                'description': f'Fear/Greed out of range: {fg}',
                'value': float(fg)
            })

    except Exception as e:
        anomalies.append({
            'id': 'sentiment_db_error',
            'severity': 8,
            'description': f'sentiment_latest DB read failed: {e}',
            'value': 0
        })
    return anomalies

def check_world_state():
    """Check world_state for staleness."""
    anomalies = []
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT updated_at FROM world_state ORDER BY updated_at DESC LIMIT 1")
        row = cur.fetchone(); cur.close(); conn.close()

        if not row:
            anomalies.append({
                'id': 'world_state_missing',
                'severity': 5,
                'description': 'world_state table is empty',
                'value': 0
            })
            return anomalies

        age = (datetime.utcnow() - row[0].replace(tzinfo=None)).total_seconds()
        if age > THRESHOLDS['world_state']:
            anomalies.append({
                'id': 'world_state_stale',
                'severity': SEVERITY['world_stale'],
                'description': f'World state stale for {age/60:.1f} mins',
                'value': age
            })

    except Exception as e:
        anomalies.append({
            'id': 'world_state_db_error',
            'severity': 3,
            'description': f'world_state DB read failed: {e}',
            'value': 0
        })
    return anomalies

def check_open_positions():
    """Check for ghost positions — EXECUTED orders with no entry_price."""
    anomalies = []
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT symbol, entry_price, created_at
            FROM orders_outbox
            WHERE status='EXECUTED' AND (entry_price IS NULL OR entry_price = 0)
        """)
        rows = cur.fetchall(); cur.close(); conn.close()
        for row in rows:
            anomalies.append({
                'id': f'ghost_position_{row[0]}',
                'severity': 7,
                'description': f'{row[0]} has EXECUTED order with no entry_price — ghost position',
                'value': 0
            })
    except Exception as e:
        log.warning(f"Position check failed: {e}")
    return anomalies

def compute_mode(anomalies):
    """
    Compute system mode from active anomalies.
    SAFE     → any anomaly severity >= 9 (critical feed down)
    DEGRADED → any anomaly severity >= 5
    NORMAL   → all anomalies severity < 5
    """
    if not anomalies:
        return 'NORMAL', 100

    max_severity = max(a['severity'] for a in anomalies)
    total_score  = sum(a['severity'] for a in anomalies)
    health_score = max(0, 100 - total_score)

    if max_severity >= 9:
        return 'SAFE', health_score
    elif max_severity >= 5:
        return 'DEGRADED', health_score
    else:
        return 'NORMAL', health_score

def write_health(mode, score, anomalies):
    """Write current system health to DB."""
    try:
        conn = get_db(); cur = conn.cursor()

        # Write to system_health
        cur.execute("""
            INSERT INTO system_health (mode, score, anomaly_count, details, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, [mode, score, len(anomalies), json.dumps(anomalies)])

        # Write to aria_config for agent loop to read
        cur.execute("""
            INSERT INTO aria_config (key, value, updated_at)
            VALUES ('system_mode', %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
        """, [json.dumps({'mode': mode, 'score': score, 'anomaly_count': len(anomalies)})])

        # Mark old anomalies as resolved if they no longer exist
        active_ids = [a['id'] for a in anomalies]
        if active_ids:
            cur.execute("""
                UPDATE system_anomalies
                SET resolved=TRUE, resolved_at=NOW()
                WHERE resolved=FALSE
                AND anomaly_id NOT IN %s
            """, [tuple(active_ids)])
        else:
            cur.execute("""
                UPDATE system_anomalies
                SET resolved=TRUE, resolved_at=NOW()
                WHERE resolved=FALSE
            """)

        # Insert new anomalies
        for a in anomalies:
            cur.execute("""
                INSERT INTO system_anomalies (anomaly_id, severity, description, value)
                SELECT %s, %s, %s, %s
                WHERE NOT EXISTS (
                    SELECT 1 FROM system_anomalies
                    WHERE anomaly_id=%s AND resolved=FALSE
                )
            """, [a['id'], a['severity'], a['description'], a['value'], a['id']])

        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.error(f"write_health failed: {e}")

def main():
    log.info("="*60)
    log.info("ARIA Anomaly Detector — Safety Spine")
    log.info("Monitors: market feeds, sentiment, world state, positions")
    log.info("="*60)

    ensure_tables()
    cycle = 0

    while True:
        cycle += 1
        try:
            all_anomalies = []
            all_anomalies += check_market_state()
            all_anomalies += check_sentiment()
            all_anomalies += check_world_state()
            all_anomalies += check_open_positions()

            mode, score = compute_mode(all_anomalies)
            write_health(mode, score, all_anomalies)

            if all_anomalies:
                log.warning(f"[Cycle {cycle}] Mode:{mode} Score:{score} Anomalies:{len(all_anomalies)}")
                for a in all_anomalies:
                    log.warning(f"  [{a['severity']:2}] {a['id']}: {a['description']}")
            else:
                log.info(f"[Cycle {cycle}] Mode:{mode} Score:{score} — all feeds healthy")

        except Exception as e:
            log.error(f"Anomaly detector cycle {cycle} error: {e}")
            import traceback; traceback.print_exc()

        time.sleep(60)

if __name__ == '__main__':
    main()
