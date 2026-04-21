# ARIA v5 - Layer 2: Correlation Kill Switch
# Monitors live correlations vs tail dependence thresholds

import psycopg2
import yfinance as yf
import numpy as np
import json
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

HETZNER_DB = {
    'host': '65.108.217.183', 'port': 5432,
    'dbname': 'aria_db', 'user': 'postgres',
    'password': 'aria_secure_2026'
}

SYMBOLS = {
    'BTC': 'BTC-USD', 'ETH': 'ETH-USD',
    'AAPL': 'AAPL', 'NVDA': 'NVDA',
    'TSLA': 'TSLA', 'GLD': 'GLD'
}

def get_tail_dependence():
    conn = psycopg2.connect(**HETZNER_DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (asset_a, asset_b)
            asset_a, asset_b, tail_dependence_coeff, crisis_correlation
        FROM tail_dependence
        ORDER BY asset_a, asset_b, created_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {(r[0], r[1]): {'tail_dep': r[2], 'crisis_corr': r[3]} for r in rows}

def get_live_correlations():
    print("Fetching live 30-day correlations...")
    returns = {}
    for symbol, ticker in SYMBOLS.items():
        try:
            df = yf.Ticker(ticker).history(period='30d', interval='1d')
            returns[symbol] = df['Close'].pct_change().dropna().values
        except:
            pass

    correlations = {}
    symbols = list(returns.keys())
    for i in range(len(symbols)):
        for j in range(i+1, len(symbols)):
            s1, s2 = symbols[i], symbols[j]
            r1, r2 = returns[s1], returns[s2]
            n = min(len(r1), len(r2))
            if n > 5:
                corr = float(np.corrcoef(r1[:n], r2[:n])[0,1])
                correlations[(s1, s2)] = round(corr, 4)
    return correlations

def assess_crisis_level(live_corrs, tail_deps):
    print("\nCrisis Assessment:")
    print("-"*60)
    alerts = []

    for pair, live_corr in live_corrs.items():
        if pair in tail_deps:
            tail_dep = tail_deps[pair]['tail_dep']
            crisis_corr = tail_deps[pair]['crisis_corr']

            # Alert levels
            if live_corr >= tail_dep:
                level = 'RED'
                action = 'MOVE TO GLD ONLY'
            elif live_corr >= tail_dep * 0.75:
                level = 'ORANGE'
                action = 'CUT POSITIONS 50%'
            elif live_corr >= tail_dep * 0.5:
                level = 'YELLOW'
                action = 'WARN - MONITOR'
            else:
                level = 'GREEN'
                action = 'NORMAL'

            if level != 'GREEN':
                alerts.append({
                    'pair': f"{pair[0]}/{pair[1]}",
                    'live_corr': live_corr,
                    'tail_dep': tail_dep,
                    'level': level,
                    'action': action
                })

            color = {'RED': '🔴', 'ORANGE': '🟠', 'YELLOW': '🟡', 'GREEN': '🟢'}[level]
            print(f"  {pair[0]:4}/{pair[1]:4}: live={live_corr:+.3f} "
                  f"threshold={tail_dep:.3f} {color} {level} - {action}")

    return alerts

def save_alerts(alerts, live_corrs):
    conn = psycopg2.connect(**HETZNER_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS correlation_alerts (
            id SERIAL PRIMARY KEY,
            alert_level VARCHAR(10),
            pair VARCHAR(20),
            live_correlation FLOAT,
            tail_dep_threshold FLOAT,
            action_required VARCHAR(50),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    for alert in alerts:
        cur.execute("""
            INSERT INTO correlation_alerts
            (alert_level, pair, live_correlation, tail_dep_threshold, action_required)
            VALUES (%s,%s,%s,%s,%s)
        """, (alert['level'], alert['pair'], alert['live_corr'],
              alert['tail_dep'], alert['action']))
    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    print("="*60)
    print("ARIA v5 - LAYER 2: CORRELATION KILL SWITCH")
    print("="*60)
    tail_deps = get_tail_dependence()
    live_corrs = get_live_correlations()
    alerts = assess_crisis_level(live_corrs, tail_deps)
    save_alerts(alerts, live_corrs)
    print("-"*60)
    if not alerts:
        print("✅ No crisis signals. All GREEN. Normal trading.")
    else:
        print(f"\n⚠️  {len(alerts)} ALERTS DETECTED:")
        for a in alerts:
            print(f"  {a['level']}: {a['pair']} → {a['action']}")
    print("="*60)
    print("LAYER 2 COMPLETE")
    print("="*60)
