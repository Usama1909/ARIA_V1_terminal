import psycopg2
import time
from datetime import datetime

DB = {"host":"localhost","dbname":"aria_db","user":"aria","password":"aria_secure_2026"}

THRESHOLDS = {"BTC":2,"ETH":2,"AAPL":5,"NVDA":5,"TSLA":5,"GLD":5,"VIX":90,"DXY":90}

def check_health():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute("SELECT symbol, COUNT(*) as records, ROUND(EXTRACT(EPOCH FROM (NOW() - MAX(timestamp)))/60, 1) as mins_ago FROM price_data GROUP BY symbol ORDER BY symbol")
    rows = cur.fetchall()
    conn.close()
    print(f"\n{'='*50}", flush=True)
    print(f"DB HEALTH — {datetime.now().strftime('%H:%M:%S')}", flush=True)
    print(f"{'='*50}", flush=True)
    all_ok = True
    for symbol, records, mins_ago in rows:
        threshold = THRESHOLDS.get(symbol, 10)
        status = "OK" if mins_ago <= threshold else "STALE!"
        if mins_ago > threshold:
            all_ok = False
        print(f"{symbol:6} | {records:>10,} | {mins_ago:>6} mins | {status}", flush=True)
    print(f"STATUS: {'ALL HEALTHY' if all_ok else 'ISSUES DETECTED'}", flush=True)

while True:
    check_health()
    time.sleep(300)
