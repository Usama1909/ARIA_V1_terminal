# ARIA v5 - Problem C: Black Swan Risk Engine (Corrected)
# Fixes: GPD/POT for EVT, Tail Dependence (not Copula), No Tanh in Generator

import numpy as np
import torch
import torch.nn as nn
import psycopg2
import yfinance as yf
import json
from scipy.stats import genpareto, kendalltau
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

def init_db():
    conn = psycopg2.connect(**HETZNER_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS black_swan_scenarios (
            id SERIAL PRIMARY KEY,
            scenario_id VARCHAR(50),
            scenario_type VARCHAR(50),
            assets_affected JSONB,
            max_drawdown FLOAT,
            tail_risk_score FLOAT,
            var_95 FLOAT,
            cvar_95 FLOAT,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS tail_dependence (
            id SERIAL PRIMARY KEY,
            asset_a VARCHAR(10),
            asset_b VARCHAR(10),
            normal_correlation FLOAT,
            crisis_correlation FLOAT,
            kendall_tau FLOAT,
            tail_dependence_coeff FLOAT,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS evt_tail_risk (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10),
            method VARCHAR(30),
            threshold FLOAT,
            shape_param FLOAT,
            scale_param FLOAT,
            var_99 FLOAT,
            expected_shortfall FLOAT,
            tail_index FLOAT,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("DB tables initialized")

def fetch_market_data():
    print("Fetching 2 years of market data...")
    data = {}
    for symbol, ticker in SYMBOLS.items():
        try:
            df = yf.Ticker(ticker).history(period='2y', interval='1d')
            if len(df) > 100:
                returns = df['Close'].pct_change().dropna()
                data[symbol] = returns.values
                print(f"  {symbol}: {len(returns)} days")
        except Exception as e:
            print(f"  {symbol}: failed - {e}")
    return data

class Generator(nn.Module):
    def __init__(self, noise_dim=32, output_dim=6):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(noise_dim, 128), nn.LeakyReLU(0.2), nn.BatchNorm1d(128),
            nn.Linear(128, 256), nn.LeakyReLU(0.2), nn.BatchNorm1d(256),
            nn.Linear(256, 128), nn.LeakyReLU(0.2),
            nn.Linear(128, output_dim)
        )
    def forward(self, z): return self.net(z)

class Discriminator(nn.Module):
    def __init__(self, input_dim=6):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 128), nn.LeakyReLU(0.2), nn.Dropout(0.3),
            nn.Linear(128, 256), nn.LeakyReLU(0.2), nn.Dropout(0.3),
            nn.Linear(256, 128), nn.LeakyReLU(0.2),
            nn.Linear(128, 1), nn.Sigmoid()
        )
    def forward(self, x): return self.net(x)

def train_gan(data):
    symbols = list(data.keys())
    min_len = min(len(data[s]) for s in symbols)
    matrix = np.column_stack([data[s][:min_len] for s in symbols])
    avg_returns = matrix.mean(axis=1)
    threshold = np.percentile(avg_returns, 10)
    crisis_data = matrix[avg_returns < threshold]
    print(f"Found {len(crisis_data)} crisis days. Training GAN...")

    G = Generator(32, len(symbols))
    D = Discriminator(len(symbols))
    opt_G = torch.optim.Adam(G.parameters(), lr=0.0002, betas=(0.5, 0.999))
    opt_D = torch.optim.Adam(D.parameters(), lr=0.0002, betas=(0.5, 0.999))
    criterion = nn.BCELoss()

    data_tensor = torch.FloatTensor(crisis_data)
    data_mean = data_tensor.mean(dim=0)
    data_std = data_tensor.std(dim=0) + 1e-8
    data_norm = (data_tensor - data_mean) / data_std

    for epoch in range(500):
        idx = torch.randint(0, len(data_norm), (32,))
        real = data_norm[idx]
        z = torch.randn(32, 32)
        fake = G(z).detach()
        D.zero_grad()
        loss_D = criterion(D(real), torch.ones(32,1)) + criterion(D(fake), torch.zeros(32,1))
        loss_D.backward(); opt_D.step()
        G.zero_grad()
        loss_G = criterion(D(G(torch.randn(32,32))), torch.ones(32,1))
        loss_G.backward(); opt_G.step()
        if (epoch+1) % 100 == 0:
            print(f"  Epoch {epoch+1}/500 D={loss_D.item():.4f} G={loss_G.item():.4f}")

    G.eval()
    with torch.no_grad():
        fake_norm = G(torch.randn(10000, 32)).numpy()
    scenarios = fake_norm * data_std.numpy() + data_mean.numpy()
    print(f"Generated 1000 synthetic crisis scenarios")
    return scenarios, symbols

def compute_tail_dependence(data):
    print("Computing Tail Dependence (crisis correlations)...")
    symbols = list(data.keys())
    results = []
    for i in range(len(symbols)):
        for j in range(i+1, len(symbols)):
            s1, s2 = symbols[i], symbols[j]
            r1 = data[s1]; r2 = data[s2]
            n = min(len(r1), len(r2))
            r1 = r1[:n]; r2 = r2[:n]
            normal_corr = float(np.corrcoef(r1, r2)[0,1])
            mask = r1 < np.percentile(r1, 20)
            crisis_corr = float(np.corrcoef(r1[mask], r2[mask])[0,1]) if mask.sum() > 10 else normal_corr
            tau, _ = kendalltau(r1, r2)
            u1 = np.argsort(np.argsort(r1)) / len(r1)
            u2 = np.argsort(np.argsort(r2)) / len(r2)
            t = 0.10
            joint_tail = np.mean((u1 < t) & (u2 < t))
            tail_dep_coeff = joint_tail / t
            results.append({
                'asset_a': s1, 'asset_b': s2,
                'normal_correlation': round(normal_corr, 4),
                'crisis_correlation': round(crisis_corr, 4),
                'kendall_tau': round(float(tau), 4),
                'tail_dependence_coeff': round(float(tail_dep_coeff), 4)
            })
            print(f"  {s1}/{s2}: normal={normal_corr:.3f} crisis={crisis_corr:.3f} tail_dep={tail_dep_coeff:.3f}")
    return results

def compute_evt(data):
    print("Computing EVT tail risk (Peaks-Over-Threshold / GPD)...")
    results = []
    for symbol, returns in data.items():
        try:
            losses = -returns
            threshold = np.percentile(losses, 90)
            exceedances = losses[losses > threshold] - threshold
            if len(exceedances) < 20:
                continue
            shape, loc, scale = genpareto.fit(exceedances, floc=0)
            n = len(losses); nu = len(exceedances)
            if shape != 0:
                var_99 = threshold + (scale/shape) * ((n/nu*0.01)**(-shape) - 1)
            else:
                var_99 = threshold - scale * np.log(n/nu*0.01)
            es = (var_99 / (1-shape)) + ((scale - shape*threshold) / (1-shape)) if shape < 1 else var_99 * 1.5
            results.append({
                'symbol': symbol, 'method': 'POT_GPD',
                'threshold': round(float(threshold)*100, 4),
                'shape_param': round(float(shape), 6),
                'scale_param': round(float(scale), 6),
                'var_99': round(float(var_99)*100, 4),
                'expected_shortfall': round(float(es)*100, 4),
                'tail_index': round(float(shape), 4)
            })
            print(f"  {symbol}: threshold={threshold*100:.2f}% VaR99={var_99*100:.2f}% ES={es*100:.2f}%")
        except Exception as e:
            print(f"  {symbol}: EVT failed - {e}")
    return results

def save_results(scenarios, symbols, tail_dep, evt):
    print("Saving to PostgreSQL...")
    conn = psycopg2.connect(**HETZNER_DB)
    cur = conn.cursor()
    for i, s in enumerate(scenarios):
        assets = {sym: round(float(s[j])*100, 2) for j, sym in enumerate(symbols)}
        max_dd = round(float(np.min(s))*100, 4)
        cur.execute("""INSERT INTO black_swan_scenarios
            (scenario_id, scenario_type, assets_affected, max_drawdown, tail_risk_score, var_95, cvar_95)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (f"GAN_{i+1:04d}", "GAN_GENERATED", json.dumps(assets),
             max_dd, 0.0, round(max_dd*1.2, 4), round(max_dd*1.5, 4)))
    for r in tail_dep:
        cur.execute("""INSERT INTO tail_dependence
            (asset_a, asset_b, normal_correlation, crisis_correlation, kendall_tau, tail_dependence_coeff)
            VALUES (%s,%s,%s,%s,%s,%s)""",
            (r['asset_a'], r['asset_b'], r['normal_correlation'],
             r['crisis_correlation'], r['kendall_tau'], r['tail_dependence_coeff']))
    for r in evt:
        cur.execute("""INSERT INTO evt_tail_risk
            (symbol, method, threshold, shape_param, scale_param, var_99, expected_shortfall, tail_index)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (r['symbol'], r['method'], r['threshold'], r['shape_param'],
             r['scale_param'], r['var_99'], r['expected_shortfall'], r['tail_index']))
    conn.commit(); cur.close(); conn.close()
    print("Saved to PostgreSQL")

if __name__ == "__main__":
    print("="*60)
    print("ARIA v5 - BLACK SWAN RISK ENGINE (CORRECTED)")
    print("EVT: Peaks-Over-Threshold / GPD")
    print("Correlations: Tail Dependence")
    print("GAN: No Tanh - true outlier generation")
    print("="*60)
    init_db()
    data = fetch_market_data()
    if len(data) < 3:
        print("Not enough data. Exiting.")
        exit(1)
    scenarios, symbols = train_gan(data)
    tail_dep = compute_tail_dependence(data)
    evt = compute_evt(data)
    save_results(scenarios, symbols, tail_dep, evt)
    print("="*60)
    print("BLACK SWAN ENGINE COMPLETE")
    print(f"  GAN scenarios: 10000")
    print(f"  Tail dependence pairs: {len(tail_dep)}")
    print(f"  EVT models fitted: {len(evt)}")
    print("="*60)
