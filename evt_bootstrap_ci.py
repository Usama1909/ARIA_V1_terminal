# ARIA v5 - Fix 2: EVT Bootstrap Confidence Intervals
# Resamples exceedances 10,000 times, reports 95% CI for VaR/ES

import numpy as np
import psycopg2
import yfinance as yf
from scipy.stats import genpareto
import warnings
warnings.filterwarnings('ignore')

HETZNER_DB = {
    'host': '65.108.217.183', 'port': 5432,
    'dbname': 'aria_db', 'user': 'postgres',
    'password': 'aria_secure_2026'
}

SYMBOLS = {
    'BTC':'BTC-USD','ETH':'ETH-USD','AAPL':'AAPL',
    'NVDA':'NVDA','TSLA':'TSLA','GLD':'GLD'
}

def bootstrap_evt_ci(losses, n_bootstrap=10000, alpha=0.99):
    threshold = np.percentile(losses, 90)
    exceedances = losses[losses > threshold] - threshold
    n = len(losses)
    nu = len(exceedances)

    if nu < 20:
        return None

    var_boot = []
    es_boot = []

    for _ in range(n_bootstrap):
        sample = np.random.choice(exceedances, size=nu, replace=True)
        try:
            shape, loc, scale = genpareto.fit(sample, floc=0)
            if shape != 0:
                var = threshold + (scale/shape)*((n/nu*(1-alpha))**(-shape)-1)
            else:
                var = threshold - scale*np.log(n/nu*(1-alpha))
            es = (var/(1-shape)) + ((scale-shape*threshold)/(1-shape)) if shape < 1 else var*1.5
            var_boot.append(var*100)
            es_boot.append(es*100)
        except:
            continue

    if len(var_boot) < 100:
        return None

    return {
        'var_99_point': float(np.mean(var_boot)),
        'var_99_ci_low': float(np.percentile(var_boot, 2.5)),
        'var_99_ci_high': float(np.percentile(var_boot, 97.5)),
        'es_99_point': float(np.mean(es_boot)),
        'es_99_ci_low': float(np.percentile(es_boot, 2.5)),
        'es_99_ci_high': float(np.percentile(es_boot, 97.5)),
        'ci_width_var': float(np.percentile(var_boot,97.5)-np.percentile(var_boot,2.5)),
        'ci_width_es': float(np.percentile(es_boot,97.5)-np.percentile(es_boot,2.5))
    }

def save_ci_to_db(symbol, ci):
    conn = psycopg2.connect(**HETZNER_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS evt_bootstrap_ci (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10),
            var_99_point FLOAT,
            var_99_ci_low FLOAT,
            var_99_ci_high FLOAT,
            es_99_point FLOAT,
            es_99_ci_low FLOAT,
            es_99_ci_high FLOAT,
            ci_width_var FLOAT,
            ci_width_es FLOAT,
            n_bootstrap INT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        INSERT INTO evt_bootstrap_ci
        (symbol, var_99_point, var_99_ci_low, var_99_ci_high,
         es_99_point, es_99_ci_low, es_99_ci_high,
         ci_width_var, ci_width_es, n_bootstrap)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (symbol, ci['var_99_point'], ci['var_99_ci_low'], ci['var_99_ci_high'],
          ci['es_99_point'], ci['es_99_ci_low'], ci['es_99_ci_high'],
          ci['ci_width_var'], ci['ci_width_es'], 10000))
    conn.commit()
    cur.close()
    conn.close()

print("="*60)
print("ARIA v5 - EVT BOOTSTRAP CI (10,000 resamples)")
print("="*60)

for symbol, ticker in SYMBOLS.items():
    print(f"\n{symbol}:")
    df = yf.Ticker(ticker).history(period='2y', interval='1d')
    returns = df['Close'].pct_change().dropna().values
    losses = -returns
    ci = bootstrap_evt_ci(losses)
    if ci:
        save_ci_to_db(symbol, ci)
        width_pct = (ci['ci_width_var']/ci['var_99_point'])*100
        status = "✅ PASS" if width_pct <= 30 else "⚠️ WIDE"
        print(f"  VaR99: {ci['var_99_point']:.2f}% [{ci['var_99_ci_low']:.2f}%, {ci['var_99_ci_high']:.2f}%]")
        print(f"  ES99:  {ci['es_99_point']:.2f}% [{ci['es_99_ci_low']:.2f}%, {ci['es_99_ci_high']:.2f}%]")
        print(f"  CI width: {width_pct:.1f}% of point estimate {status}")
    else:
        print("  Not enough data")

print("\n" + "="*60)
print("Bootstrap CI complete. Saved to evt_bootstrap_ci table.")
print("="*60)
