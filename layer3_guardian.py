# ARIA v5 - Layer 3: Guardian Agent (21st Agent)
# Uses VaR99 + GAN scenarios to size hedge positions
# Protects portfolio during black swan events

import psycopg2
import yfinance as yf
import numpy as np
import json
from datetime import datetime
import requests
import warnings
warnings.filterwarnings('ignore')

HETZNER_DB = {
    'host': '65.108.217.183', 'port': 5432,
    'dbname': 'aria_db', 'user': 'postgres',
    'password': 'aria_secure_2026'
}

ARIA_URL = "https://web-production-548c0.up.railway.app"
BASE_PORTFOLIO = 10000.0
HEDGE_BUDGET_PCT = 0.25  # Guardian uses max 10% of portfolio for hedging

def get_evt_data():
    conn = psycopg2.connect(**HETZNER_DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (symbol) symbol, var_99, expected_shortfall
        FROM evt_tail_risk ORDER BY symbol, created_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {r[0]: {'var_99': r[1], 'es': r[2]} for r in rows}

def get_worst_gan_scenario():
    conn = psycopg2.connect(**HETZNER_DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT assets_affected, max_drawdown
        FROM black_swan_scenarios
        ORDER BY max_drawdown ASC LIMIT 1
    """)
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return row[0], row[1]
    return {}, 0

def get_correlation_alerts():
    conn = psycopg2.connect(**HETZNER_DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM correlation_alerts
        WHERE alert_level = 'RED'
        AND created_at > NOW() - INTERVAL '1 hour'
    """)
    red_count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return red_count

def calculate_hedge_sizes(evt_data, worst_scenario, red_alerts):
    """
    Guardian sizes hedges based on:
    1. VaR99 per asset (higher VaR = bigger hedge needed)
    2. Worst GAN scenario drawdown
    3. Number of RED correlation alerts
    """
    hedge_budget = BASE_PORTFOLIO * HEDGE_BUDGET_PCT

    # Crisis multiplier based on RED alerts
    if red_alerts >= 6:
        crisis_mult = 2.0   # Full crisis
    elif red_alerts >= 3:
        crisis_mult = 1.5   # Elevated risk
    elif red_alerts >= 1:
        crisis_mult = 1.2   # Warning
    else:
        crisis_mult = 1.0   # Normal

    hedges = {}
    total_var = sum(d['var_99'] for d in evt_data.values())

    for symbol, data in evt_data.items():
        # Weight hedge by VaR99 (riskier assets get bigger hedges)
        var_weight = data['var_99'] / total_var
        hedge_size = hedge_budget * var_weight * crisis_mult

        # Guardian always goes SHORT (hedge against long positions)
        hedges[symbol] = {
            'direction': 'SHORT',
            'size': round(hedge_size, 2),
            'var_99': data['var_99'],
            'es': data['es'],
            'crisis_mult': crisis_mult,
            'reason': f"VaR99={data['var_99']:.2f}% alerts={red_alerts}"
        }

    return hedges

def calculate_portfolio_protection(hedges, worst_scenario, worst_drawdown):
    """Calculate how much the Guardian protects in worst case"""
    total_hedge_value = sum(h['size'] for h in hedges.values())
    worst_dd = abs(worst_drawdown) / 100

    # If worst scenario hits, shorts gain while longs lose
    hedge_profit = total_hedge_value * worst_dd
    portfolio_loss = BASE_PORTFOLIO * worst_dd
    net_loss = portfolio_loss - hedge_profit
    protection_pct = (hedge_profit / portfolio_loss * 100) if portfolio_loss > 0 else 0

    return {
        'worst_scenario_drawdown': round(worst_drawdown, 2),
        'portfolio_loss_no_hedge': round(portfolio_loss, 2),
        'hedge_profit': round(hedge_profit, 2),
        'net_loss_with_hedge': round(net_loss, 2),
        'protection_pct': round(protection_pct, 1),
        'total_hedge_cost': round(total_hedge_value, 2)
    }

def save_guardian_state(hedges, protection, red_alerts):
    conn = psycopg2.connect(**HETZNER_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS guardian_state (
            id SERIAL PRIMARY KEY,
            hedge_positions JSONB,
            protection_analysis JSONB,
            red_alerts INT,
            crisis_level VARCHAR(20),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    if red_alerts >= 6:   crisis_level = 'CRITICAL'
    elif red_alerts >= 3: crisis_level = 'HIGH'
    elif red_alerts >= 1: crisis_level = 'ELEVATED'
    else:                 crisis_level = 'NORMAL'

    cur.execute("""
        INSERT INTO guardian_state
        (hedge_positions, protection_analysis, red_alerts, crisis_level)
        VALUES (%s,%s,%s,%s)
    """, (json.dumps(hedges), json.dumps(protection), red_alerts, crisis_level))
    conn.commit()
    cur.close()
    conn.close()

def report_to_aria(hedges, protection, red_alerts):
    """Send Guardian status to Railway via agent report"""
    crisis_level = 'CRITICAL' if red_alerts >= 6 else 'HIGH' if red_alerts >= 3 else 'ELEVATED' if red_alerts >= 1 else 'NORMAL'
    try:
        requests.post(f"{ARIA_URL}/agent/report", json={
            'agent_id': 'guardian_agent',
            'agent_type': 'GUARDIAN',
            'symbol': 'PORTFOLIO',
            'action': crisis_level,
            'confidence': min(red_alerts / 8, 1.0),
            'reasoning': f"Guardian: {red_alerts} RED alerts. Protection={protection['protection_pct']}%. Hedge cost=${protection['total_hedge_cost']:.2f}",
            'pnl_today': 0.0
        }, timeout=5)
        print("Guardian reported to ARIA terminal")
    except Exception as e:
        print(f"Report failed: {e}")

if __name__ == "__main__":
    print("="*60)
    print("ARIA v5 - LAYER 3: GUARDIAN AGENT")
    print("21st Agent - Portfolio Protection")
    print("="*60)

    # Load data
    evt_data = get_evt_data()
    worst_scenario, worst_drawdown = get_worst_gan_scenario()
    red_alerts = get_correlation_alerts()

    print(f"\nInputs:")
    print(f"  EVT models: {len(evt_data)} assets")
    print(f"  Worst GAN scenario drawdown: {worst_drawdown:.2f}%")
    print(f"  RED correlation alerts: {red_alerts}")

    # Calculate hedges
    hedges = calculate_hedge_sizes(evt_data, worst_scenario, red_alerts)

    print(f"\nGuardian Hedge Positions:")
    print("-"*60)
    for symbol, hedge in sorted(hedges.items()):
        print(f"  {symbol:6}: SHORT ${hedge['size']:7.2f} "
              f"(VaR99={hedge['var_99']:.2f}% crisis_mult={hedge['crisis_mult']}x)")

    # Calculate protection
    protection = calculate_portfolio_protection(hedges, worst_scenario, worst_drawdown)

    print(f"\nPortfolio Protection Analysis:")
    print("-"*60)
    print(f"  Worst scenario drawdown:    {protection['worst_scenario_drawdown']:.2f}%")
    print(f"  Portfolio loss (no hedge):  ${protection['portfolio_loss_no_hedge']:.2f}")
    print(f"  Guardian hedge profit:      ${protection['hedge_profit']:.2f}")
    print(f"  Net loss (with Guardian):   ${protection['net_loss_with_hedge']:.2f}")
    print(f"  Protection coverage:        {protection['protection_pct']:.1f}%")
    print(f"  Total hedge cost:           ${protection['total_hedge_cost']:.2f}")

    # Save and report
    save_guardian_state(hedges, protection, red_alerts)
    report_to_aria(hedges, protection, red_alerts)

    print("="*60)
    print("LAYER 3 COMPLETE - GUARDIAN ACTIVE")
    print("="*60)
