import psycopg2
import os
import time
import logging
import requests
from dotenv import load_dotenv
load_dotenv("/root/.env")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [SYNC] %(message)s")
log = logging.getLogger()
HETZNER_DB = {"host":"localhost","port":5432,"dbname":"aria_db","user":"postgres","password":"aria_secure_2026"}
RAILWAY_URL = os.getenv("RAILWAY_DATABASE_URL", "")
RAILWAY_APP_URL = 'https://web-production-548c0.up.railway.app'
SYNC_INTERVAL = 60

def get_hetzner():
    return psycopg2.connect(**HETZNER_DB)

def get_railway():
    return psycopg2.connect(RAILWAY_URL)

def ensure_railway_tables(rcur):
    rcur.execute("""
        CREATE TABLE IF NOT EXISTS positions_live (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) UNIQUE,
            direction VARCHAR(10),
            entry_price FLOAT,
            size_usd FLOAT,
            status VARCHAR(20) DEFAULT 'OPEN',
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    rcur.execute("""
        CREATE TABLE IF NOT EXISTS system_state_sync (
            id INTEGER PRIMARY KEY DEFAULT 1,
            sys_mode VARCHAR(20),
            regime VARCHAR(20),
            sentiment FLOAT,
            fear_greed INTEGER,
            narrative VARCHAR(50),
            liquidity VARCHAR(20),
            wmult FLOAT,
            portfolio_value FLOAT,
            cycle INTEGER,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    rcur.execute("""
        CREATE TABLE IF NOT EXISTS closed_trades_sync (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10),
            direction VARCHAR(10),
            entry_price FLOAT,
            exit_price FLOAT,
            pnl_usd FLOAT,
            pnl_pct FLOAT,
            size_usd FLOAT,
            outcome VARCHAR(10),
            exit_time TIMESTAMP DEFAULT NOW()
        )
    """)

def sync_positions(hcur, rcur):
    hcur.execute("SELECT symbol, direction, entry_price, size_usd, status FROM positions_live")
    positions = hcur.fetchall()
    for p in positions:
        rcur.execute("INSERT INTO positions_live (symbol, direction, entry_price, size_usd, status, updated_at) VALUES (%s, %s, %s, %s, %s, NOW()) ON CONFLICT (symbol) DO UPDATE SET direction=EXCLUDED.direction, entry_price=EXCLUDED.entry_price, size_usd=EXCLUDED.size_usd, status=EXCLUDED.status, updated_at=NOW()", p)
    log.info("Synced " + str(len(positions)) + " positions to Railway")

def sync_system_state(hcur, rcur):
    try:
        hcur.execute("SELECT mode, score FROM system_health ORDER BY id DESC LIMIT 1")
        row = hcur.fetchone()
        if row:
            rcur.execute("INSERT INTO system_state_sync (id, sys_mode, regime, updated_at) VALUES (1,%s,%s,NOW()) ON CONFLICT (id) DO UPDATE SET sys_mode=EXCLUDED.sys_mode, regime=EXCLUDED.regime, updated_at=NOW()", (row[0], row[0]))
            log.info("Synced system state")
    except Exception as e:
        log.warning("system state sync skipped: " + str(e))

def sync_closed_trades(hcur, rcur):
    try:
        hcur.execute("SELECT symbol, direction, entry_price, exit_price, pnl_usd, pnl_pct, size_usd, outcome, exit_time FROM closed_trades ORDER BY id DESC LIMIT 500")
        trades = hcur.fetchall()
        rcur.execute("DELETE FROM closed_trades_sync")
        for t in trades:
            rcur.execute("INSERT INTO closed_trades_sync (symbol, direction, entry_price, exit_price, pnl_usd, pnl_pct, size_usd, outcome, exit_time) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", t)
        log.info("Synced " + str(len(trades)) + " closed trades to Railway")
    except Exception as e:
        log.warning("closed trades sync skipped: " + str(e))

def post_agent_reports(reports):
    try:
        payload = {'reports': reports}
        resp = requests.post(RAILWAY_APP_URL + '/agent/reports/sync', json=payload, timeout=10)
        log.info('Posted ' + str(len(reports)) + ' agent reports to frontend: ' + str(resp.status_code))
    except Exception as e:
        log.error('Agent reports POST failed: ' + str(e))

def sync_agent_decisions(hcur):
    try:
        hcur.execute("""
            SELECT agent_id, symbol, action, confidence, reasoning, timestamp
            FROM agent_decisions
            ORDER BY timestamp DESC LIMIT 100
        """)
        rows = hcur.fetchall()
        reports = [{'agent_id': r[0], 'symbol': r[1], 'action': r[2],
                    'confidence': float(r[3]) if r[3] else 0.5,
                    'reasoning': r[4], 'timestamp': r[5].isoformat(),
                    'agent_type': 'SPECIALIST'} for r in rows]
        post_agent_reports(reports)
        log.info('Synced ' + str(len(reports)) + ' agent decisions')
    except Exception as e:
        log.warning('Agent decisions sync skipped: ' + str(e))

def post_positions_to_frontend(positions):
    try:
        payload = {'positions': [{'symbol': p[0], 'direction': p[1], 'entry_price': p[2], 'size': p[3], 'exchange': 'ARIA Paper'} for p in positions]}
        resp = requests.post(RAILWAY_APP_URL + '/positions/update', json=payload, timeout=10)
        log.info('Posted ' + str(len(positions)) + ' positions to frontend: ' + str(resp.status_code))
    except Exception as e:
        log.error('Frontend POST failed: ' + str(e))

def run():
    log.info("DB Sync Bridge starting...")
    if not RAILWAY_URL:
        log.error("RAILWAY_DATABASE_URL not set")
        return
    while True:
        try:
            hconn = get_hetzner()
            rconn = get_railway()
            hcur = hconn.cursor()
            rcur = rconn.cursor()
            ensure_railway_tables(rcur)
            sync_positions(hcur, rcur)
            sync_system_state(hcur, rcur)
            sync_closed_trades(hcur, rcur)
            sync_agent_decisions(hcur)
            rconn.commit()
            hcur.execute("SELECT symbol, direction, entry_price, size_usd, status FROM positions_live WHERE status='OPEN'")
            positions = hcur.fetchall()
            post_positions_to_frontend(positions)
            hcur.close(); hconn.close()
            rcur.close(); rconn.close()
            log.info("Sync complete. Next in " + str(SYNC_INTERVAL) + "s")
        except Exception as e:
            log.error("Sync error: " + str(e))
        time.sleep(SYNC_INTERVAL)

if __name__ == "__main__":
    run()
