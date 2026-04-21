#!/usr/bin/env python3
"""ARIA Sentiment Service — Problem B standalone"""
import sys, time, psycopg2, logging
sys.path.insert(0, '/root/ARIA_SentimentEngine_v1')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [SENTIMENT] %(message)s')
log = logging.getLogger()
DB = {'host':'localhost','port':5432,'dbname':'aria_db','user':'postgres','password':'aria_secure_2026'}

def write_to_db(signal):
    conn = psycopg2.connect(**DB); cur = conn.cursor()
    for name, val, sym, action in [
        ('live_sentiment', float(signal['score']), 'ALL', signal['stance']),
        ('sentiment_velocity', float(signal.get('velocity_1h',0)), 'ALL', signal.get('velocity_signal','NEUTRAL')),
        ('market_regime', float(signal.get('fear_greed_raw',50)), 'ALL', signal.get('regime','NORMAL')),
    ]:
        cur.execute("INSERT INTO signal_log (signal_name,signal_value,symbol,triggered_action) VALUES (%s,%s,%s,%s)",
                   [name, val, sym, action])
    conn.commit(); cur.close(); conn.close()

def write_latest(signal):
    conn = psycopg2.connect(**DB); cur = conn.cursor()
    cur.execute("DELETE FROM sentiment_latest")
    cur.execute("INSERT INTO sentiment_latest (score,stance,velocity,regime,fear_greed,updated_at) VALUES (%s,%s,%s,%s,%s,NOW())",
        [float(signal['score']), signal['stance'], float(signal.get('velocity_1h',0)),
         signal.get('regime','NORMAL'), int(signal.get('fear_greed_raw',50))])
    conn.commit(); cur.close(); conn.close()

def main():
    log.info("ARIA Sentiment Service started")
    while True:
        try:
            from sentiment_engine import get_sentiment_signal
            s = get_sentiment_signal()
            write_to_db(s)
            write_latest(s)
            log.info(f"Score:{s['score']:+.1f} ({s['stance']}) F&G:{s['fear_greed_raw']} Regime:{s['regime']}")
        except Exception as e:
            log.error(f"Failed: {e}")
        time.sleep(300)

if __name__ == '__main__':
    main()
