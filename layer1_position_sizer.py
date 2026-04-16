# ARIA v5 - Layer 1: Adaptive Position Sizer
# Uses EVT Expected Shortfall for Risk Parity sizing

import psycopg2
import json

HETZNER_DB = {
    'host': '65.108.217.183', 'port': 5432,
    'dbname': 'aria_db', 'user': 'postgres',
    'password': 'aria_secure_2026'
}

REGIME_MULTIPLIER = {
    'BULL':     1.00,
    'SIDEWAYS': 0.75,
    'BEAR':     0.50,
    'CRISIS':   0.25
}

BASE_PORTFOLIO = 10000.0

def get_evt_data():
    conn = psycopg2.connect(**HETZNER_DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (symbol) symbol, var_99, expected_shortfall
        FROM evt_tail_risk
        ORDER BY symbol, created_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {row[0]: {'var_99': row[1], 'es': row[2]} for row in rows}

def calculate_risk_parity_sizes(evt_data, regime='SIDEWAYS', kelly_fraction=0.02):
    """
    Risk Parity: Position Size = (1/ES) normalized
    Then apply regime multiplier and Kelly fraction
    """
    # Step 1: Calculate inverse ES weights
    inverse_es = {}
    for symbol, data in evt_data.items():
        es = data['es'] / 100  # Convert % to decimal
        inverse_es[symbol] = 1 / es if es > 0 else 0

    # Step 2: Normalize to sum to 1
    total = sum(inverse_es.values())
    weights = {sym: inv_es / total for sym, inv_es in inverse_es.items()}

    # Step 3: Apply regime multiplier
    regime_mult = REGIME_MULTIPLIER.get(regime, 0.75)

    # Step 4: Calculate dollar position sizes
    sizes = {}
    for symbol, weight in weights.items():
        raw_size = BASE_PORTFOLIO * weight * regime_mult * kelly_fraction * 100
        sizes[symbol] = round(raw_size, 2)

    return sizes, weights

def save_sizes_to_db(sizes, weights, regime):
    conn = psycopg2.connect(**HETZNER_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS risk_parity_sizes (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10),
            position_size FLOAT,
            weight FLOAT,
            regime VARCHAR(20),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    for symbol, size in sizes.items():
        cur.execute("""
            INSERT INTO risk_parity_sizes (symbol, position_size, weight, regime)
            VALUES (%s, %s, %s, %s)
        """, (symbol, size, round(weights[symbol], 6), regime))
    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    print("="*60)
    print("ARIA v5 - LAYER 1: ADAPTIVE POSITION SIZER")
    print("="*60)

    evt_data = get_evt_data()
    print(f"\nEVT data loaded for {len(evt_data)} assets")

    for regime in ['BULL', 'SIDEWAYS', 'BEAR', 'CRISIS']:
        sizes, weights = calculate_risk_parity_sizes(evt_data, regime)
        print(f"\n{regime} Regime:")
        for sym in sorted(sizes.keys()):
            es = evt_data[sym]['es']
            print(f"  {sym:6}: weight={weights[sym]:.3f} size=${sizes[sym]:6.2f} (ES={es:.2f}%)")

    # Save current SIDEWAYS sizes
    sizes, weights = calculate_risk_parity_sizes(evt_data, 'SIDEWAYS')
    save_sizes_to_db(sizes, weights, 'SIDEWAYS')
    print("\nSaved to PostgreSQL")
    print("="*60)
    print("LAYER 1 COMPLETE")
    print("="*60)
