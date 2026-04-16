# ARIA v5 - Fix 4: Kupiec + Christoffersen VaR Backtest

import numpy as np
import psycopg2
import yfinance as yf
import json
from scipy import stats
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

def get_var99(symbol):
    conn = psycopg2.connect(**HETZNER_DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT var_99 FROM evt_tail_risk 
        WHERE symbol=%s ORDER BY created_at DESC LIMIT 1
    """, (symbol,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0]/100 if row else None

def kupiec_test(hits, T, alpha=0.01):
    """Kupiec unconditional coverage test"""
    x = sum(hits)
    if x == 0: x = 0.0001
    if x == T: x = T - 0.0001
    p = alpha
    p_hat = x / T
    try:
        lr = -2 * (x*np.log(p/p_hat) + (T-x)*np.log((1-p)/(1-p_hat)))
        pval = 1 - stats.chi2.cdf(lr, df=1)
        return {'lr': round(float(lr),4), 'pvalue': round(float(pval),4),
                'pass': bool(pval > 0.05), 'exceptions': int(x), 'total': T}
    except:
        return {'lr': 0, 'pvalue': 0, 'pass': False, 'exceptions': int(x), 'total': T}

def christoffersen_test(hits):
    """Christoffersen independence test"""
    hits = list(hits)
    T = len(hits)
    n00=n01=n10=n11=0
    for i in range(1, T):
        if hits[i-1]==0 and hits[i]==0: n00+=1
        elif hits[i-1]==0 and hits[i]==1: n01+=1
        elif hits[i-1]==1 and hits[i]==0: n10+=1
        elif hits[i-1]==1 and hits[i]==1: n11+=1
    try:
        p01 = n01/(n00+n01) if (n00+n01)>0 else 0.0001
        p11 = n11/(n10+n11) if (n10+n11)>0 else 0.0001
        p = (n01+n11)/(n00+n01+n10+n11)
        p = max(min(p, 0.9999), 0.0001)
        p01 = max(min(p01, 0.9999), 0.0001)
        p11 = max(min(p11, 0.9999), 0.0001)
        lr = -2*((n00+n10)*np.log(1-p)+(n01+n11)*np.log(p)) + \
              2*(n00*np.log(1-p01)+n01*np.log(p01)+n10*np.log(1-p11)+n11*np.log(p11))
        pval = 1 - stats.chi2.cdf(lr, df=1)
        return {'lr': round(float(lr),4), 'pvalue': round(float(pval),4), 'pass': bool(pval > 0.05)}
    except:
        return {'lr': 0, 'pvalue': 0, 'pass': False}

def save_backtest(symbol, kupiec, christoffersen, var99, actual_rate):
    conn = psycopg2.connect(**HETZNER_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS var_backtest (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10),
            var_99 FLOAT,
            actual_exception_rate FLOAT,
            kupiec_lr FLOAT,
            kupiec_pvalue FLOAT,
            kupiec_pass BOOLEAN,
            christoffersen_lr FLOAT,
            christoffersen_pvalue FLOAT,
            christoffersen_pass BOOLEAN,
            exceptions INT,
            total_days INT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    vals = (str(symbol), float(var99*100), float(actual_rate), float(kupiec['lr']), float(kupiec['pvalue']), bool(kupiec['pass']), float(christoffersen['lr']), float(christoffersen['pvalue']), bool(christoffersen['pass']), int(kupiec['exceptions']), int(kupiec['total']))
    cur.execute("INSERT INTO var_backtest (symbol, var_99, actual_exception_rate, kupiec_lr, kupiec_pvalue, kupiec_pass, christoffersen_lr, christoffersen_pvalue, christoffersen_pass, exceptions, total_days) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", vals)
    conn.commit()
    cur.close()
    conn.close()

print("="*60)
print("ARIA v5 - VAR BACKTEST (Kupiec + Christoffersen)")
print("="*60)

for symbol, ticker in SYMBOLS.items():
    print(f"\n{symbol}:")
    var99 = get_var99(symbol)
    if not var99:
        print("  No VaR data found"); continue

    df = yf.Ticker(ticker).history(period='2y', interval='1d')
    returns = df['Close'].pct_change().dropna().values
    losses = -returns

    hits = (losses > var99).astype(int)
    T = len(hits)
    actual_rate = hits.mean()

    kupiec = kupiec_test(hits, T)
    christoffersen = christoffersen_test(hits)

    save_backtest(symbol, kupiec, christoffersen, var99, actual_rate)

    k_status = "✅ PASS" if kupiec['pass'] else "⚠️ FAIL"
    c_status = "✅ PASS" if christoffersen['pass'] else "⚠️ FAIL"
    print(f"  VaR99: {var99*100:.2f}% | Exceptions: {kupiec['exceptions']}/{T} ({actual_rate*100:.2f}%)")
    print(f"  Kupiec:          LR={kupiec['lr']:.4f} p={kupiec['pvalue']:.4f} {k_status}")
    print(f"  Christoffersen:  LR={christoffersen['lr']:.4f} p={christoffersen['pvalue']:.4f} {c_status}")

print("\n" + "="*60)
print("VaR Backtest complete. Saved to var_backtest table.")
print("="*60)
