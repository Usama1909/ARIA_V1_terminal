# ARIA v5 - Fix 3: GAN Validation Suite
# MMD test, KS test per marginal, uniqueness ratio, cluster diversity

import numpy as np
import psycopg2
import yfinance as yf
from scipy.stats import ks_2samp
from sklearn.neighbors import NearestNeighbors
from sklearn.cluster import KMeans
import json
import warnings
warnings.filterwarnings('ignore')

HETZNER_DB = {
    'host': '65.108.217.183', 'port': 5432,
    'dbname': 'aria_db', 'user': 'postgres',
    'password': 'aria_secure_2026'
}

SYMBOLS = ['BTC','ETH','AAPL','NVDA','TSLA','GLD']

def get_gan_scenarios():
    conn = psycopg2.connect(**HETZNER_DB)
    cur = conn.cursor()
    cur.execute("SELECT assets_affected FROM black_swan_scenarios ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    scenarios = []
    for row in rows:
        assets = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        vec = [assets.get(s, 0)/100 for s in SYMBOLS]
        scenarios.append(vec)
    return np.array(scenarios)

def compute_mmd(X, Y, gamma=1.0):
    """Maximum Mean Discrepancy between two distributions"""
    def rbf_kernel(A, B):
        diff = A[:, None, :] - B[None, :, :]
        return np.exp(-gamma * np.sum(diff**2, axis=-1))
    n, m = len(X), len(Y)
    Kxx = rbf_kernel(X, X)
    Kyy = rbf_kernel(Y, Y)
    Kxy = rbf_kernel(X, Y)
    mmd = (np.sum(Kxx) - np.trace(Kxx))/(n*(n-1)) + \
          (np.sum(Kyy) - np.trace(Kyy))/(m*(m-1)) - \
          2*np.mean(Kxy)
    return float(mmd)

def compute_uniqueness_ratio(generated, training, threshold=1e-6):
    """Fraction of generated samples not identical to any training sample"""
    nn = NearestNeighbors(n_neighbors=1).fit(training)
    distances, _ = nn.kneighbors(generated)
    unique = np.mean(distances.flatten() > threshold)
    return float(unique)

def compute_diversity(scenarios, n_clusters=8):
    """Effective number of clusters = exp(entropy of cluster distribution)"""
    if len(scenarios) < n_clusters:
        return 0.0
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(scenarios)
    counts = np.bincount(labels)
    probs = counts / counts.sum()
    entropy = -np.sum(probs * np.log(probs + 1e-10))
    return float(np.exp(entropy))

def fetch_real_crisis_data():
    data = {}
    for sym, ticker in zip(SYMBOLS, ['BTC-USD','ETH-USD','AAPL','NVDA','TSLA','GLD']):
        df = yf.Ticker(ticker).history(period='2y', interval='1d')
        returns = df['Close'].pct_change().dropna().values
        data[sym] = returns
    min_len = min(len(v) for v in data.values())
    matrix = np.column_stack([data[s][:min_len] for s in SYMBOLS])
    avg = matrix.mean(axis=1)
    threshold = np.percentile(avg, 10)
    return matrix[avg < threshold]

def save_validation_to_db(results):
    conn = psycopg2.connect(**HETZNER_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gan_validation (
            id SERIAL PRIMARY KEY,
            mmd_score FLOAT,
            uniqueness_ratio FLOAT,
            diversity_score FLOAT,
            ks_results JSONB,
            uniqueness_pass BOOLEAN,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        INSERT INTO gan_validation
        (mmd_score, uniqueness_ratio, diversity_score, ks_results, uniqueness_pass)
        VALUES (%s,%s,%s,%s,%s)
    """, (results['mmd'], results['uniqueness'], results['diversity'],
          json.dumps(results['ks']), results['uniqueness'] >= 0.85))
    conn.commit()
    cur.close()
    conn.close()

print("="*60)
print("ARIA v5 - GAN VALIDATION SUITE")
print("="*60)

# Load data
print("\nLoading GAN scenarios and real crisis data...")
gan_scenarios = get_gan_scenarios()
real_crisis = fetch_real_crisis_data()
print(f"  GAN scenarios: {len(gan_scenarios)}")
print(f"  Real crisis days: {len(real_crisis)}")

# Use subset for speed
gan_sample = gan_scenarios[np.random.choice(len(gan_scenarios), min(500, len(gan_scenarios)), replace=False)]
real_sample = real_crisis[:min(200, len(real_crisis))]

# MMD test
print("\n1. MMD Two-Sample Test...")
mmd = compute_mmd(gan_sample[:100], real_sample[:100])
print(f"  MMD score: {mmd:.6f} (lower = more similar to real crises)")

# KS test per marginal
print("\n2. KS Test per Marginal...")
ks_results = {}
for i, sym in enumerate(SYMBOLS):
    stat, pval = ks_2samp(gan_sample[:, i], real_sample[:, i])
    status = "✅ PASS" if pval > 0.05 else "⚠️ FAIL"
    ks_results[sym] = {'statistic': round(float(stat),4), 'pvalue': round(float(pval),4)}
    print(f"  {sym}: KS={stat:.4f} p={pval:.4f} {status}")

# Uniqueness ratio
print("\n3. Uniqueness Ratio...")
uniqueness = compute_uniqueness_ratio(gan_sample, real_sample)
status = "✅ PASS" if uniqueness >= 0.85 else "⚠️ BELOW TARGET"
print(f"  Uniqueness ratio: {uniqueness:.4f} (target ≥0.85) {status}")

# Diversity
print("\n4. Scenario Diversity...")
diversity = compute_diversity(gan_scenarios)
print(f"  Effective clusters: {diversity:.2f} (target: high, max=8)")

# Save
results = {
    'mmd': mmd,
    'uniqueness': uniqueness,
    'diversity': diversity,
    'ks': ks_results
}
save_validation_to_db(results)

print("\n" + "="*60)
print("GAN VALIDATION COMPLETE")
print(f"  MMD: {mmd:.6f}")
print(f"  Uniqueness: {uniqueness:.4f} {'✅' if uniqueness>=0.85 else '⚠️'}")
print(f"  Diversity: {diversity:.2f}")
print("="*60)
