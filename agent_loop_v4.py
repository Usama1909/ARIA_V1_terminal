#!/usr/bin/env python3
"""
ARIA AUTONOMOUS SWARM INTELLIGENCE v4
======================================
- 20 evolutionary agents across 4 layers
- Pattern memory engine (learns & stores market fingerprints)
- Storm Protocol (crash detection & safe haven)
- Black Box Resurrection (survives any wipe)
- Binance Testnet execution (BTC, ETH)
- ARIA DB paper trading (AAPL, NVDA, TSLA, GLD)
- Zero human input after deployment
- Self-evolving: nightly mutation of underperforming agents
"""

import requests, time, json, numpy as np, hashlib, hmac
from datetime import datetime, timedelta
from urllib.parse import urlencode
import psycopg2, psycopg2.extras
import random, math

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
ARIA_URL        = "https://web-production-548c0.up.railway.app"
LOOP_INTERVAL   = 60
PAPER_USER      = "aria-agent-system"

# Binance Testnet
BINANCE_API_KEY    = "AMMWwf7NYmSh02xjGbLu5nZv7CaW9B6IyG8Ghx2NNv4AwDIA5eSPpM2wzSjvgcif"
BINANCE_SECRET_KEY = "ATp5pNBYTPD8w84q8Dss0eAS7UVBSWxmK7jZ0w7pH5IPx5Cb2VEVE8lLf0WGTqTf"
BINANCE_TESTNET    = "https://testnet.binance.vision/api"

# PostgreSQL (Hetzner)
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'dbname': 'aria_db',
    'user': 'postgres',
    'password': 'aria_secure_2026'
}

# Trading config
CRYPTO_SYMBOLS  = ['BTC', 'ETH']
STOCK_SYMBOLS   = ['AAPL', 'NVDA', 'TSLA', 'GLD']
ALL_SYMBOLS     = CRYPTO_SYMBOLS + STOCK_SYMBOLS
TRADE_AMOUNT    = 100.0
MAX_OPEN_TRADES = 5
MIN_CONFIDENCE  = 0.52
MAX_DRAWDOWN    = 0.15
MIN_HOLD_CYCLES = 60   # 60 mins minimum hold

# Storm Protocol thresholds
STORM_VIX           = 35
STORM_DRAWDOWN      = 0.12
STORM_SENTIMENT_DROP = -10   # points per hour
STORM_ASSETS_DOWN   = 4      # assets dropping > 3% simultaneously

# Pattern matching
PATTERN_MATCH_THRESHOLD = 0.80   # 80% similarity = known territory
PATTERN_FAMILIAR        = 0.60   # 60% = familiar territory

# ─────────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────────
def get_db():
    return psycopg2.connect(**DB_CONFIG)

def init_db():
    """Create all v4 tables if they don't exist"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS swarm_blackbox (
            id SERIAL PRIMARY KEY,
            snapshot JSONB NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS pattern_library (
            id SERIAL PRIMARY KEY,
            fingerprint JSONB NOT NULL,
            action_taken VARCHAR(20),
            outcome VARCHAR(10),
            pnl FLOAT DEFAULT 0,
            confidence FLOAT,
            symbol VARCHAR(10),
            regime VARCHAR(20),
            hold_hours FLOAT,
            times_matched INT DEFAULT 0,
            win_count INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS agent_fitness (
            agent_id VARCHAR(50) PRIMARY KEY,
            agent_type VARCHAR(30),
            personality VARCHAR(50),
            total_trades INT DEFAULT 0,
            win_count INT DEFAULT 0,
            total_pnl FLOAT DEFAULT 0,
            avg_hold_hours FLOAT DEFAULT 0,
            generation INT DEFAULT 1,
            params JSONB DEFAULT '{}',
            status VARCHAR(20) DEFAULT 'ACTIVE',
            last_mutated TIMESTAMP DEFAULT NOW(),
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS swarm_trades (
            id SERIAL PRIMARY KEY,
            trade_id VARCHAR(100) UNIQUE,
            agent_id VARCHAR(50),
            symbol VARCHAR(10),
            direction VARCHAR(10),
            exchange VARCHAR(20),
            entry_price FLOAT,
            exit_price FLOAT,
            amount_usd FLOAT,
            pnl FLOAT,
            signal_used VARCHAR(100),
            pattern_matched BOOLEAN DEFAULT FALSE,
            pattern_similarity FLOAT,
            opened_at TIMESTAMP DEFAULT NOW(),
            closed_at TIMESTAMP,
            status VARCHAR(20) DEFAULT 'OPEN'
        );

        CREATE TABLE IF NOT EXISTS signal_log (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT NOW(),
            signal_name VARCHAR(100),
            signal_value FLOAT,
            symbol VARCHAR(10),
            triggered_action VARCHAR(20),
            outcome VARCHAR(10)
        );
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("  [DB] Tables ready")

# ─────────────────────────────────────────────
# BLACK BOX — RESURRECTION SYSTEM
# ─────────────────────────────────────────────
def save_blackbox(state):
    """Save complete system state every 15 minutes"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO swarm_blackbox (snapshot) VALUES (%s)",
            [json.dumps(state)]
        )
        # Keep only last 100 snapshots
        cur.execute("""
            DELETE FROM swarm_blackbox
            WHERE id NOT IN (
                SELECT id FROM swarm_blackbox
                ORDER BY created_at DESC LIMIT 100
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"  [BLACKBOX] Save failed: {e}")

def load_blackbox():
    """Resurrect from last known state on startup"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT snapshot, created_at FROM swarm_blackbox ORDER BY created_at DESC LIMIT 1"
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            snapshot, ts = row
            age_mins = (datetime.utcnow() - ts).total_seconds() / 60
            print(f"  [BLACKBOX] Resurrecting from snapshot {age_mins:.0f} mins ago")
            return snapshot
    except Exception as e:
        print(f"  [BLACKBOX] Load failed: {e}")
    return None

# ─────────────────────────────────────────────
# PATTERN MEMORY ENGINE
# ─────────────────────────────────────────────
def build_fingerprint(signal_bus):
    """Build a 12-point market fingerprint"""
    return {
        'vix':               round(float(signal_bus.get('vix', 20)), 1),
        'funding_btc':       round(float(signal_bus.get('funding_btc', 0)), 4),
        'funding_eth':       round(float(signal_bus.get('funding_eth', 0)), 4),
        'sentiment':         round(float(signal_bus.get('sentiment', 50)), 0),
        'sentiment_velocity':round(float(signal_bus.get('sentiment_velocity', 0)), 1),
        'regime':            signal_bus.get('regime', 'SIDEWAYS'),
        'macro_signal':      signal_bus.get('macro_signal', 'NEUTRAL'),
        'btc_change_24h':    round(float(signal_bus.get('btc_change', 0)), 1),
        'eth_change_24h':    round(float(signal_bus.get('eth_change', 0)), 1),
        'volume_spike':      bool(signal_bus.get('volume_spike', False)),
        'cross_asset_div':   bool(signal_bus.get('cross_asset_divergence', False)),
        'storm_active':      bool(signal_bus.get('storm_active', False)),
    }

def fingerprint_similarity(fp1, fp2):
    """Calculate cosine-like similarity between two fingerprints (0-1)"""
    score = 0
    total = 0

    # Numeric fields
    numeric = ['vix', 'funding_btc', 'funding_eth', 'sentiment',
               'sentiment_velocity', 'btc_change_24h', 'eth_change_24h']
    for key in numeric:
        v1 = float(fp1.get(key, 0))
        v2 = float(fp2.get(key, 0))
        max_val = max(abs(v1), abs(v2), 0.001)
        diff = abs(v1 - v2) / max_val
        score += max(0, 1 - diff)
        total += 1

    # Categorical fields
    categorical = ['regime', 'macro_signal']
    for key in categorical:
        score += 1 if fp1.get(key) == fp2.get(key) else 0
        total += 1

    # Boolean fields
    boolean = ['volume_spike', 'cross_asset_div', 'storm_active']
    for key in boolean:
        score += 1 if fp1.get(key) == fp2.get(key) else 0.5
        total += 1

    return score / total if total > 0 else 0

def search_patterns(fingerprint, symbol=None, limit=5):
    """Find similar patterns from memory"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if symbol:
            cur.execute(
                "SELECT * FROM pattern_library WHERE symbol=%s ORDER BY updated_at DESC LIMIT 200",
                [symbol]
            )
        else:
            cur.execute("SELECT * FROM pattern_library ORDER BY updated_at DESC LIMIT 500")
        rows = cur.fetchall()
        cur.close()
        conn.close()

        matches = []
        for row in rows:
            stored_fp = row['fingerprint']
            sim = fingerprint_similarity(fingerprint, stored_fp)
            if sim >= PATTERN_FAMILIAR:
                matches.append({
                    'similarity': sim,
                    'action': row['action_taken'],
                    'outcome': row['outcome'],
                    'pnl': row['pnl'],
                    'win_count': row['win_count'],
                    'times_matched': row['times_matched'],
                    'id': row['id']
                })

        matches.sort(key=lambda x: x['similarity'], reverse=True)
        return matches[:limit]
    except Exception as e:
        print(f"  [PATTERN] Search failed: {e}")
        return []

def store_pattern(fingerprint, action, symbol, outcome, pnl, confidence, hold_hours, regime):
    """Store a new pattern or update existing"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO pattern_library
            (fingerprint, action_taken, symbol, outcome, pnl, confidence, hold_hours, regime)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, [
            json.dumps(fingerprint), action, symbol,
            outcome, pnl, confidence, hold_hours, regime
        ])
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"  [PATTERN] Store failed: {e}")

def get_pattern_confidence(matches, action):
    """Calculate confidence boost from pattern matches"""
    if not matches:
        return 0, 'UNKNOWN'

    best = matches[0]
    sim = best['similarity']

    if sim >= PATTERN_MATCH_THRESHOLD:
        territory = 'KNOWN'
        # Win rate of matching patterns
        total = sum(m['times_matched'] + 1 for m in matches)
        wins = sum(m['win_count'] for m in matches)
        win_rate = wins / total if total > 0 else 0.5
        boost = (win_rate - 0.5) * 0.3  # max ±15% confidence adjustment
        return boost, territory
    elif sim >= PATTERN_FAMILIAR:
        return 0.05, 'FAMILIAR'
    else:
        return -0.1, 'UNKNOWN'

# ─────────────────────────────────────────────
# BINANCE TESTNET EXECUTION
# ─────────────────────────────────────────────
def binance_sign(params):
    query = urlencode(params)
    signature = hmac.new(
        BINANCE_SECRET_KEY.encode(), query.encode(), hashlib.sha256
    ).hexdigest()
    return query + f"&signature={signature}"

def binance_request(method, endpoint, params=None):
    if params is None:
        params = {}
    params['timestamp'] = int(time.time() * 1000)
    headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
    signed = binance_sign(params)
    url = f"{BINANCE_TESTNET}{endpoint}?{signed}"
    try:
        if method == 'GET':
            r = requests.get(url, headers=headers, timeout=10)
        elif method == 'POST':
            r = requests.post(url, headers=headers, timeout=10)
        elif method == 'DELETE':
            r = requests.delete(url, headers=headers, timeout=10)
        return r.json()
    except Exception as e:
        print(f"  [BINANCE] Request failed: {e}")
        return {}

def get_binance_price(symbol):
    """Get current price from Binance testnet"""
    pair = f"{symbol}USDT"
    try:
        r = requests.get(
            f"{BINANCE_TESTNET}/v3/ticker/price",
            params={'symbol': pair}, timeout=5
        )
        return float(r.json().get('price', 0))
    except:
        return 0

def get_binance_funding_rate(symbol):
    """Get funding rate from Binance (uses real endpoint - public data)"""
    try:
        pair = f"{symbol}USDT"
        r = requests.get(
            "https://fapi.binance.com/fapi/v1/premiumIndex",
            params={'symbol': pair}, timeout=5
        )
        data = r.json()
        return float(data.get('lastFundingRate', 0))
    except:
        return 0

def binance_open_trade(symbol, direction, amount_usd):
    """Open a trade on Binance testnet"""
    pair = f"{symbol}USDT"
    price = get_binance_price(symbol)
    if price == 0:
        return False, None

    quantity = round(amount_usd / price, 6)
    if symbol == 'BTC':
        quantity = round(quantity, 5)
    elif symbol == 'ETH':
        quantity = round(quantity, 4)

    side = 'BUY' if direction == 'LONG' else 'SELL'

    # For testnet SHORT we use a BUY of opposite (simplified paper short)
    result = binance_request('POST', '/v3/order', {
        'symbol': pair,
        'side': side,
        'type': 'MARKET',
        'quantity': quantity
    })

    if result.get('orderId'):
        return True, {
            'order_id': result['orderId'],
            'price': price,
            'quantity': quantity,
            'symbol': symbol,
            'direction': direction
        }
    return False, None

def binance_close_trade(symbol, direction, quantity):
    """Close a Binance testnet position"""
    pair = f"{symbol}USDT"
    # Close = opposite side
    side = 'SELL' if direction == 'LONG' else 'BUY'
    result = binance_request('POST', '/v3/order', {
        'symbol': pair,
        'side': side,
        'type': 'MARKET',
        'quantity': quantity
    })
    return bool(result.get('orderId'))

# ─────────────────────────────────────────────
# ARIA PAPER TRADING (stocks)
# ─────────────────────────────────────────────
def aria_open_trade(symbol, direction):
    try:
        r = requests.post(f"{ARIA_URL}/paper/trade", json={
            'user_id': PAPER_USER, 'symbol': symbol,
            'direction': direction, 'amount_usd': TRADE_AMOUNT
        }, timeout=10)
        return r.json().get('success', False)
    except:
        return False

def aria_close_trade(symbol):
    try:
        port = requests.get(f"{ARIA_URL}/paper/portfolio/{PAPER_USER}", timeout=10).json()
        for t in port.get('open_trades', []):
            if t['symbol'] == symbol:
                requests.post(f"{ARIA_URL}/paper/close", json={
                    'user_id': PAPER_USER, 'trade_id': t['trade_id']
                }, timeout=10)
                return True
    except:
        pass
    return False

def aria_report(agent_id, agent_type, symbol, action, confidence, reasoning):
    try:
        requests.post(f"{ARIA_URL}/agent/report", json={
            'agent_id': agent_id, 'agent_type': agent_type,
            'symbol': symbol, 'action': action,
            'confidence': float(confidence), 'reasoning': reasoning,
            'timestamp': datetime.utcnow().isoformat()
        }, timeout=5)
    except:
        pass

# ─────────────────────────────────────────────
# SIGNAL BUS — shared intelligence layer
# ─────────────────────────────────────────────
def build_signal_bus(state):
    """Collect all signals into shared bus"""
    bus = {}
    macro = state.get('macro', {})
    assets = state.get('assets', {})

    # Macro signals
    bus['vix']          = float(macro.get('vix', 20) or 20)
    bus['crisis_score'] = float(macro.get('crisis_score', 0) or 0)
    bus['dxy']          = float(macro.get('dxy', 100) or 100)

    # Funding rates (real public data)
    bus['funding_btc'] = get_binance_funding_rate('BTC')
    bus['funding_eth'] = get_binance_funding_rate('ETH')

    # Sentiment
    fgs = [float(a.get('fear_greed', 50) or 50) for a in assets.values() if a]
    bus['sentiment'] = np.mean(fgs) if fgs else 50

    # Sentiment velocity (change vs last hour — stored in bus history)
    bus['sentiment_velocity'] = 0  # updated by SentimentVelocityAgent

    # Asset changes
    btc = assets.get('BTC', {}) or {}
    eth = assets.get('ETH', {}) or {}
    bus['btc_change']  = float(btc.get('change_24h', 0) or 0)
    bus['eth_change']  = float(eth.get('change_24h', 0) or 0)
    bus['btc_eth_spread'] = abs(bus['btc_change'] - bus['eth_change'])

    # Volume spike detection
    changes = [abs(float(a.get('change_24h', 0) or 0)) for a in assets.values() if a]
    bus['volume_spike'] = any(c > 5 for c in changes)

    # Cross asset divergence
    nvda = assets.get('NVDA', {}) or {}
    nvda_change = float(nvda.get('change_24h', 0) or 0)
    bus['cross_asset_divergence'] = (nvda_change > 2 and bus['vix'] > 25)

    # Count assets in distress
    down_count = sum(1 for a in assets.values() if a and float(a.get('change_24h', 0) or 0) < -3)
    bus['assets_down_count'] = down_count

    # Regime
    avg_change = np.mean([float(a.get('change_24h', 0) or 0) for a in assets.values() if a]) if assets else 0
    bus['regime'] = 'BULL' if avg_change > 3 else 'BEAR' if avg_change < -3 else 'SIDEWAYS'

    # Macro signal
    if bus['crisis_score'] > 75 or bus['vix'] > 35:
        bus['macro_signal'] = 'CRISIS'
    elif bus['vix'] > 25:
        bus['macro_signal'] = 'RISK_OFF'
    else:
        bus['macro_signal'] = 'RISK_ON'

    bus['storm_active'] = False  # set by StormProtocol
    bus['assets'] = assets
    return bus

# ─────────────────────────────────────────────
# STORM PROTOCOL
# ─────────────────────────────────────────────
def check_storm(bus, balance, start_balance=10000):
    """Detect market crash conditions"""
    triggers = []
    drawdown = (start_balance - balance) / start_balance

    if bus['vix'] > STORM_VIX:
        triggers.append(f"VIX={bus['vix']:.0f}")
    if bus['funding_btc'] < -0.05:
        triggers.append(f"FundingBTC={bus['funding_btc']:.4f}")
    if bus['sentiment_velocity'] < STORM_SENTIMENT_DROP:
        triggers.append(f"SentVelocity={bus['sentiment_velocity']:.1f}")
    if bus['assets_down_count'] >= STORM_ASSETS_DOWN:
        triggers.append(f"{bus['assets_down_count']} assets crashing")
    if drawdown > STORM_DRAWDOWN:
        triggers.append(f"Drawdown={drawdown*100:.1f}%")

    if triggers:
        return True, triggers
    return False, []

def storm_all_clear(bus):
    """Check if market is safe to re-enter"""
    return (
        bus['vix'] < 25 and
        bus['sentiment'] > 35 and
        bus['sentiment_velocity'] > -3 and
        bus['macro_signal'] != 'CRISIS' and
        bus['assets_down_count'] < 2
    )

# ─────────────────────────────────────────────
# AGENT FITNESS SYSTEM
# ─────────────────────────────────────────────
def init_agent_fitness(agents):
    """Initialize agent fitness records"""
    try:
        conn = get_db()
        cur = conn.cursor()
        for agent in agents:
            cur.execute("""
                INSERT INTO agent_fitness (agent_id, agent_type, personality, params)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (agent_id) DO NOTHING
            """, [agent['id'], agent['type'], agent['personality'], json.dumps(agent['params'])])
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"  [FITNESS] Init failed: {e}")

def update_agent_fitness(agent_id, won, pnl, hold_hours):
    """Update agent performance after trade closes"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE agent_fitness SET
                total_trades = total_trades + 1,
                win_count = win_count + %s,
                total_pnl = total_pnl + %s,
                avg_hold_hours = (avg_hold_hours + %s) / 2
            WHERE agent_id = %s
        """, [1 if won else 0, pnl, hold_hours, agent_id])
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"  [FITNESS] Update failed: {e}")

def get_agent_rankings():
    """Get all agents ranked by P&L"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT agent_id, total_trades, win_count, total_pnl, generation, status
            FROM agent_fitness ORDER BY total_pnl DESC
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except:
        return []

# ─────────────────────────────────────────────
# MUTATION ENGINE
# ─────────────────────────────────────────────
def run_mutation_engine(agents):
    """Nightly: kill bottom agents, mutate parameters"""
    rankings = get_agent_rankings()
    if len(rankings) < 5:
        return agents

    # Only mutate agents with enough trades
    qualified = [r for r in rankings if r['total_trades'] >= 3]
    if len(qualified) < 4:
        return agents

    bottom_ids = [r['agent_id'] for r in qualified[-3:]]

    print(f"\n  [MUTATION] Generation upgrade starting...")
    print(f"  [MUTATION] Retiring: {bottom_ids}")

    try:
        conn = get_db()
        cur = conn.cursor()
        for agent in agents:
            if agent['id'] in bottom_ids:
                # Mutate parameters
                new_params = {
                    'confidence_threshold': round(random.uniform(0.50, 0.75), 2),
                    'rsi_oversold':         random.randint(25, 40),
                    'rsi_overbought':       random.randint(60, 80),
                    'funding_threshold':    round(random.uniform(0.02, 0.10), 3),
                    'hold_multiplier':      round(random.uniform(0.5, 2.0), 1),
                }
                agent['params'] = new_params

                cur.execute("""
                    UPDATE agent_fitness SET
                        generation = generation + 1,
                        params = %s,
                        total_trades = 0,
                        win_count = 0,
                        total_pnl = 0,
                        last_mutated = NOW(),
                        status = 'MUTATED'
                    WHERE agent_id = %s
                """, [json.dumps(new_params), agent['id']])
                print(f"  [MUTATION] {agent['id']} → new params: {new_params}")

        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"  [MUTATION] Failed: {e}")

    return agents

# ─────────────────────────────────────────────
# AGENT DEFINITIONS — 20 agents, 4 layers
# ─────────────────────────────────────────────
def build_agents():
    return [
        # ── LAYER 1: DATA AGENTS ──────────────────
        {'id': 'funding_collector',    'type': 'DATA',     'personality': 'FundingRate',
         'layer': 1, 'symbol': None,
         'params': {'threshold': 0.05}},

        {'id': 'sentiment_velocity',   'type': 'DATA',     'personality': 'SentimentVelocity',
         'layer': 1, 'symbol': None,
         'params': {'window_hours': 1}},

        {'id': 'macro_collector',      'type': 'DATA',     'personality': 'MacroWatcher',
         'layer': 1, 'symbol': None,
         'params': {'vix_threshold': 25}},

        {'id': 'volume_detector',      'type': 'DATA',     'personality': 'VolumeScanner',
         'layer': 1, 'symbol': None,
         'params': {'spike_threshold': 5}},

        # ── LAYER 2: ANALYSIS AGENTS ──────────────
        {'id': 'whale_agent',          'type': 'ANALYSIS', 'personality': 'WhaleTracker',
         'layer': 2, 'symbol': None,
         'params': {'vpin_threshold': 0.7}},

        {'id': 'regime_agent',         'type': 'ANALYSIS', 'personality': 'RegimeDetector',
         'layer': 2, 'symbol': None,
         'params': {'bull_threshold': 3, 'bear_threshold': -3}},

        {'id': 'correlation_agent',    'type': 'ANALYSIS', 'personality': 'CorrelationWatcher',
         'layer': 2, 'symbol': None,
         'params': {'spread_std': 2.0}},

        {'id': 'liquidation_agent',    'type': 'ANALYSIS', 'personality': 'LiquidationHunter',
         'layer': 2, 'symbol': None,
         'params': {'funding_danger': 0.08}},

        # ── LAYER 3: STRATEGY AGENTS ──────────────
        {'id': 'momentum_agent',       'type': 'STRATEGY', 'personality': 'MomentumMo',
         'layer': 3, 'symbol': None,
         'params': {'confidence_threshold': 0.60, 'rsi_oversold': 35, 'rsi_overbought': 65,
                    'funding_threshold': 0.05, 'hold_multiplier': 1.0}},

        {'id': 'contrarian_agent',     'type': 'STRATEGY', 'personality': 'ContrarianCarl',
         'layer': 3, 'symbol': None,
         'params': {'confidence_threshold': 0.65, 'rsi_oversold': 25, 'rsi_overbought': 75,
                    'funding_threshold': 0.08, 'hold_multiplier': 1.5}},

        {'id': 'quant_agent',          'type': 'STRATEGY', 'personality': 'QuantQuinn',
         'layer': 3, 'symbol': None,
         'params': {'confidence_threshold': 0.70, 'rsi_oversold': 30, 'rsi_overbought': 70,
                    'funding_threshold': 0.06, 'hold_multiplier': 1.0}},

        {'id': 'macro_trader',         'type': 'STRATEGY', 'personality': 'MacroMike',
         'layer': 3, 'symbol': None,
         'params': {'confidence_threshold': 0.55, 'rsi_oversold': 40, 'rsi_overbought': 60,
                    'funding_threshold': 0.04, 'hold_multiplier': 2.0}},

        {'id': 'panic_fader',          'type': 'STRATEGY', 'personality': 'PanicFader',
         'layer': 3, 'symbol': None,
         'params': {'confidence_threshold': 0.58, 'rsi_oversold': 28, 'rsi_overbought': 72,
                    'funding_threshold': 0.07, 'hold_multiplier': 0.8}},

        {'id': 'arbitrage_agent',      'type': 'STRATEGY', 'personality': 'ArbitrageAlex',
         'layer': 3, 'symbol': None,
         'params': {'confidence_threshold': 0.62, 'spread_threshold': 3.0,
                    'funding_threshold': 0.05, 'hold_multiplier': 0.5}},

        # ── SPECIALIST AGENTS (one per asset) ─────
        {'id': 'specialist_btc',       'type': 'SPECIALIST', 'personality': 'BTCSpecialist',
         'layer': 3, 'symbol': 'BTC',
         'params': {'confidence_threshold': 0.55, 'rsi_oversold': 35, 'rsi_overbought': 65,
                    'funding_threshold': 0.05, 'hold_multiplier': 1.0}},

        {'id': 'specialist_eth',       'type': 'SPECIALIST', 'personality': 'ETHSpecialist',
         'layer': 3, 'symbol': 'ETH',
         'params': {'confidence_threshold': 0.55, 'rsi_oversold': 35, 'rsi_overbought': 65,
                    'funding_threshold': 0.05, 'hold_multiplier': 1.0}},

        {'id': 'specialist_aapl',      'type': 'SPECIALIST', 'personality': 'AAPLSpecialist',
         'layer': 3, 'symbol': 'AAPL',
         'params': {'confidence_threshold': 0.58, 'rsi_oversold': 35, 'rsi_overbought': 65,
                    'funding_threshold': 0.0, 'hold_multiplier': 1.0}},

        {'id': 'specialist_nvda',      'type': 'SPECIALIST', 'personality': 'NVDASpecialist',
         'layer': 3, 'symbol': 'NVDA',
         'params': {'confidence_threshold': 0.58, 'rsi_oversold': 35, 'rsi_overbought': 65,
                    'funding_threshold': 0.0, 'hold_multiplier': 1.0}},

        {'id': 'specialist_tsla',      'type': 'SPECIALIST', 'personality': 'TSLASpecialist',
         'layer': 3, 'symbol': 'TSLA',
         'params': {'confidence_threshold': 0.58, 'rsi_oversold': 35, 'rsi_overbought': 65,
                    'funding_threshold': 0.0, 'hold_multiplier': 1.0}},

        {'id': 'specialist_gld',       'type': 'SPECIALIST', 'personality': 'GLDSpecialist',
         'layer': 3, 'symbol': 'GLD',
         'params': {'confidence_threshold': 0.55, 'rsi_oversold': 40, 'rsi_overbought': 60,
                    'funding_threshold': 0.0, 'hold_multiplier': 1.5}},
    ]

# ─────────────────────────────────────────────
# LAYER 1 — DATA AGENTS
# ─────────────────────────────────────────────
def run_data_agents(bus, sentiment_history):
    """Layer 1: collect and enrich signal bus"""

    # Funding rate agent
    funding_signal = 'NEUTRAL'
    if bus['funding_btc'] > 0.08:
        funding_signal = 'OVERLEVERAGED_LONG'  # squeeze incoming
    elif bus['funding_btc'] < -0.05:
        funding_signal = 'OVERLEVERAGED_SHORT'
    bus['funding_signal'] = funding_signal
    aria_report('funding_collector', 'DATA', 'BTC', funding_signal,
                0.8, f"BTC funding={bus['funding_btc']:.4f} ETH={bus['funding_eth']:.4f}")

    # Sentiment velocity agent
    sentiment_history.append({'time': datetime.utcnow(), 'value': bus['sentiment']})
    # Keep 2 hours of history
    cutoff = datetime.utcnow() - timedelta(hours=2)
    sentiment_history[:] = [s for s in sentiment_history if s['time'] > cutoff]

    if len(sentiment_history) >= 2:
        old = sentiment_history[0]['value']
        new = sentiment_history[-1]['value']
        bus['sentiment_velocity'] = new - old
    aria_report('sentiment_velocity', 'DATA', None, 'VELOCITY',
                0.7, f"Sentiment velocity={bus['sentiment_velocity']:.1f}/hr")

    # Volume detector
    vol_signal = 'SPIKE' if bus['volume_spike'] else 'NORMAL'
    aria_report('volume_detector', 'DATA', None, vol_signal,
                0.75, f"Assets_down={bus['assets_down_count']} Spike={bus['volume_spike']}")

    return bus

# ─────────────────────────────────────────────
# LAYER 2 — ANALYSIS AGENTS
# ─────────────────────────────────────────────
def run_analysis_agents(bus):
    """Layer 2: analyse signals, produce meta-signals"""

    # Whale agent — detects institutional moves via funding + volume
    whale_detected = (
        abs(bus['funding_btc']) > 0.07 or
        bus['volume_spike'] and abs(bus['btc_change']) > 4
    )
    bus['whale_detected'] = whale_detected
    aria_report('whale_agent', 'ANALYSIS', None,
                'WHALE_DETECTED' if whale_detected else 'NO_WHALE',
                0.75, f"Funding={bus['funding_btc']:.4f} Vol_spike={bus['volume_spike']}")

    # Liquidation agent — estimates if liquidation cascade is near
    liq_risk = bus['funding_btc'] > 0.08 and bus['sentiment'] < 35
    bus['liquidation_risk'] = liq_risk
    aria_report('liquidation_agent', 'ANALYSIS', None,
                'LIQ_RISK' if liq_risk else 'SAFE',
                0.80, f"Liq_risk={liq_risk}")

    # Correlation agent — BTC/ETH spread stat arb signal
    spread = bus['btc_eth_spread']
    arb_signal = spread > 4.0  # significant divergence
    bus['arb_opportunity'] = arb_signal
    aria_report('correlation_agent', 'ANALYSIS', None,
                'ARB_OPPORTUNITY' if arb_signal else 'CORRELATED',
                0.70, f"BTC/ETH spread={spread:.2f}%")

    # Regime agent
    aria_report('regime_agent', 'ANALYSIS', None, bus['regime'],
                0.80, f"Regime={bus['regime']} avg_change implied")

    return bus

# ─────────────────────────────────────────────
# LAYER 3 — STRATEGY AGENTS
# ─────────────────────────────────────────────
def run_strategy_agent(agent, bus, fingerprint, open_positions, cycle):
    """Run a single strategy agent — reads full signal bus"""
    params = agent['params']
    symbol = agent.get('symbol')
    personality = agent['personality']
    assets = bus.get('assets', {})

    # Get asset data if specialist
    asset = assets.get(symbol, {}) if symbol else {}
    confidence = float((asset or {}).get('confidence', 0.5) or 0.5)
    rsi = float((asset or {}).get('rsi', 50) or 50)
    xgb_signal = (asset or {}).get('signal', 'HOLD') if asset else 'HOLD'
    if isinstance(xgb_signal, dict):
        xgb_signal = xgb_signal.get('signal', 'HOLD')

    # Pattern memory lookup
    patterns = search_patterns(fingerprint, symbol)
    pattern_boost, territory = get_pattern_confidence(patterns, xgb_signal)
    adjusted_confidence = min(0.95, max(0.1, confidence + pattern_boost))

    # Position sizing based on territory
    size_multiplier = 1.0
    if territory == 'KNOWN':
        size_multiplier = 1.0
    elif territory == 'FAMILIAR':
        size_multiplier = 0.7
    else:
        size_multiplier = 0.4  # Unknown territory = small size

    # Check hold time
    if symbol and symbol in open_positions:
        held = cycle - open_positions[symbol]['cycle']
        min_hold = int(MIN_HOLD_CYCLES * params.get('hold_multiplier', 1.0))
        if held < min_hold:
            return 'HOLD', adjusted_confidence, None, size_multiplier, territory

    # ── PERSONALITY LOGIC ────────────────────

    direction = None

    if personality == 'MomentumMo':
        # Chase confirmed trends
        if bus['regime'] == 'BULL' and adjusted_confidence > params['confidence_threshold']:
            direction = 'LONG'
        elif bus['regime'] == 'BEAR' and adjusted_confidence > params['confidence_threshold']:
            direction = 'SHORT'

    elif personality == 'ContrarianCarl':
        # Fade extremes
        if bus['sentiment'] < 20 and bus['funding_btc'] < -0.03:
            direction = 'LONG'  # Extreme fear = buy
        elif bus['sentiment'] > 80 and bus['funding_btc'] > 0.07:
            direction = 'SHORT'  # Extreme greed = sell

    elif personality == 'QuantQuinn':
        # Pure model signal
        if adjusted_confidence >= params['confidence_threshold']:
            direction = 'LONG' if xgb_signal == 'TAKE_PROFIT' else 'SHORT'

    elif personality == 'MacroMike':
        # Only trades on macro divergence
        if bus['cross_asset_divergence'] and bus['macro_signal'] == 'RISK_OFF':
            direction = 'SHORT'
        elif bus['macro_signal'] == 'RISK_ON' and bus['vix'] < 18:
            direction = 'LONG'

    elif personality == 'PanicFader':
        # Buy panic, sell euphoria
        if bus['sentiment'] < 25 and bus['sentiment_velocity'] < -5:
            direction = 'LONG'  # Panic bottom incoming
        elif bus['sentiment'] > 78 and bus['sentiment_velocity'] > 5:
            direction = 'SHORT'

    elif personality == 'ArbitrageAlex':
        # BTC/ETH stat arb
        if bus['arb_opportunity']:
            if bus['btc_change'] > bus['eth_change']:
                direction = 'SHORT'  # BTC overextended vs ETH
            else:
                direction = 'LONG'

    elif personality in ['BTCSpecialist', 'ETHSpecialist',
                          'AAPLSpecialist', 'NVDASpecialist',
                          'TSLASpecialist', 'GLDSpecialist']:
        # Specialist: combines XGBoost + RSI + macro + funding
        if adjusted_confidence < params['confidence_threshold']:
            return 'HOLD', adjusted_confidence, None, size_multiplier, territory

        direction = 'LONG' if xgb_signal == 'TAKE_PROFIT' else 'SHORT'

        # RSI override
        if rsi < params['rsi_oversold']:
            direction = 'LONG'
        elif rsi > params['rsi_overbought']:
            direction = 'SHORT'

        # Macro override
        if bus['macro_signal'] == 'CRISIS':
            if symbol == 'GLD':
                direction = 'LONG'
            else:
                return 'HOLD', 0.5, None, size_multiplier, territory

        # Funding override for crypto
        if symbol in ['BTC', 'ETH']:
            if bus['funding_btc'] > params['funding_threshold'] and direction == 'LONG':
                direction = 'SHORT'  # Overleveraged longs = fade
            if bus['liquidation_risk'] and symbol == 'BTC':
                direction = 'SHORT'

    if direction is None:
        return 'HOLD', adjusted_confidence, None, size_multiplier, territory

    # Determine action
    if symbol and symbol in open_positions:
        cur_dir = open_positions[symbol]['direction']
        action = 'REVERSE' if cur_dir != direction else 'HOLD'
    else:
        action = 'BUY' if direction == 'LONG' else 'SELL'

    reasoning = (f"{personality} {direction} {symbol or 'MULTI'} "
                 f"conf={adjusted_confidence:.2f} territory={territory} "
                 f"funding={bus['funding_btc']:.4f} regime={bus['regime']}")
    aria_report(agent['id'], agent['type'], symbol, action, adjusted_confidence, reasoning)

    return action, adjusted_confidence, direction, size_multiplier, territory

# ─────────────────────────────────────────────
# META AGENT — Layer 4
# ─────────────────────────────────────────────
def run_meta_agent(decisions, bus):
    """Fades consensus when ALL agents agree — crowded trade detector"""
    if not decisions:
        return decisions

    longs = sum(1 for d in decisions if d['direction'] == 'LONG')
    shorts = sum(1 for d in decisions if d['direction'] == 'SHORT')
    total = len(decisions)

    consensus_ratio = max(longs, shorts) / total if total > 0 else 0
    bus['agent_consensus'] = consensus_ratio

    if consensus_ratio >= 0.85 and total >= 6:
        # DANGEROUS: 85%+ agreement = crowded trade
        # Meta agent fades this with a warning
        dominant = 'LONG' if longs > shorts else 'SHORT'
        fade = 'SHORT' if dominant == 'LONG' else 'LONG'

        aria_report('meta_agent', 'META', None, 'FADE_CONSENSUS', 0.75,
                    f"Consensus={consensus_ratio:.0%} all {dominant} — fading to {fade}")
        print(f"  [META] ⚠️  Dangerous consensus {consensus_ratio:.0%} — fade signal: {fade}")

        # Reduce confidence of all decisions by 15%
        for d in decisions:
            d['confidence'] *= 0.85

    return decisions

# ─────────────────────────────────────────────
# RISK AGENT — final approval
# ─────────────────────────────────────────────
def run_risk_agent(decisions, bus, balance, open_positions):
    """Kelly-sized, correlation-filtered final approval"""
    drawdown = (10000 - balance) / 10000
    approved = []
    open_count = len(open_positions)

    # Kill switch
    if drawdown > MAX_DRAWDOWN:
        aria_report('risk_agent', 'RISK', None, 'KILL_SWITCH', 1.0,
                    f"Drawdown {drawdown*100:.1f}% > {MAX_DRAWDOWN*100:.0f}%")
        print(f"  [RISK] 🚨 KILL SWITCH: Drawdown {drawdown*100:.1f}%")
        return []

    # Crisis: only GLD allowed
    if bus['macro_signal'] == 'CRISIS':
        decisions = [d for d in decisions
                     if d.get('symbol') == 'GLD' or d.get('symbol') is None]

    # Correlation filter: don't hold BTC + ETH same direction simultaneously
    btc_dir = open_positions.get('BTC', {}).get('direction')
    eth_dir = open_positions.get('ETH', {}).get('direction')

    for d in decisions:
        symbol = d.get('symbol')
        action = d.get('action')
        direction = d.get('direction')
        confidence = d.get('confidence', 0.5)

        # Max positions check
        if action in ['BUY', 'SELL'] and open_count >= MAX_OPEN_TRADES:
            aria_report('risk_agent', 'RISK', symbol, 'VETO', 1.0, f"Max positions {MAX_OPEN_TRADES}")
            continue

        # Correlation filter
        if symbol == 'ETH' and direction == btc_dir and btc_dir is not None:
            aria_report('risk_agent', 'RISK', symbol, 'VETO', 1.0,
                        f"Correlation: BTC+ETH both {btc_dir}")
            continue

        # Kelly position sizing
        win_rate = max(0.4, min(0.8, confidence))
        kelly = win_rate - (1 - win_rate)  # simplified Kelly
        size = max(50, min(200, TRADE_AMOUNT * kelly * d.get('size_multiplier', 1.0)))

        d['approved_size'] = round(size, 2)
        approved.append(d)

        if action in ['BUY', 'SELL']:
            open_count += 1

        aria_report('risk_agent', 'RISK', symbol, 'APPROVED', 1.0,
                    f"Approved {action} {symbol} size=${size:.0f} Kelly={kelly:.2f}")

    return approved

# ─────────────────────────────────────────────
# TRADE EXECUTION
# ─────────────────────────────────────────────
def execute_trade(decision, open_positions, cycle):
    symbol = decision.get('symbol')
    action = decision['action']
    direction = decision['direction']
    size = decision.get('approved_size', TRADE_AMOUNT)

    if symbol is None:
        return False

    # Close existing if reversing
    if action == 'REVERSE' and symbol in open_positions:
        close_position(symbol, open_positions)
        time.sleep(1)

    # Open new position
    if symbol in CRYPTO_SYMBOLS:
        success, order = binance_open_trade(symbol, direction, size)
        if success:
            open_positions[symbol] = {
                'direction': direction,
                'cycle': cycle,
                'exchange': 'binance_testnet',
                'entry_price': order['price'],
                'quantity': order['quantity'],
                'size': size,
                'fingerprint_at_entry': None,
                'agent_id': decision.get('agent_id')
            }
            print(f"  [EXEC] ✅ Binance {direction} {symbol} @ ${order['price']:.2f}")
            return True
    else:
        success = aria_open_trade(symbol, direction)
        if success:
            open_positions[symbol] = {
                'direction': direction,
                'cycle': cycle,
                'exchange': 'aria_paper',
                'size': size,
                'agent_id': decision.get('agent_id')
            }
            print(f"  [EXEC] ✅ ARIA paper {direction} {symbol}")
            return True

    return False

def close_position(symbol, open_positions):
    """Close a position on the right exchange"""
    if symbol not in open_positions:
        return False

    pos = open_positions[symbol]
    exchange = pos.get('exchange', 'aria_paper')

    if exchange == 'binance_testnet':
        success = binance_close_trade(symbol, pos['direction'], pos.get('quantity', 0))
    else:
        success = aria_close_trade(symbol)

    if success:
        del open_positions[symbol]
        print(f"  [EXEC] 🔴 Closed {symbol} on {exchange}")
    return success

# ─────────────────────────────────────────────
# MAIN SWARM LOOP
# ─────────────────────────────────────────────
def main():
    print("=" * 65)
    print("  ARIA SWARM INTELLIGENCE v4 — EVOLUTIONARY TRADING SYSTEM")
    print("=" * 65)
    print(f"  Agents:          20 across 4 layers")
    print(f"  Crypto:          Binance Testnet (BTC, ETH)")
    print(f"  Stocks:          ARIA Paper (AAPL, NVDA, TSLA, GLD)")
    print(f"  Pattern Memory:  PostgreSQL (grows with every trade)")
    print(f"  Black Box:       Saves every 15 mins — survives any wipe")
    print(f"  Storm Protocol:  Auto safe-haven on crash detection")
    print(f"  Mutation Engine: Nightly — kills weak agents")
    print("=" * 65)

    # Init
    init_db()
    agents = build_agents()
    init_agent_fitness(agents)

    # Black Box resurrection
    open_positions = {}
    blackbox = load_blackbox()
    if blackbox:
        open_positions = blackbox.get('open_positions', {})
        print(f"  [RESURRECTION] Restored {len(open_positions)} positions")
        for sym, pos in open_positions.items():
            print(f"    → {sym}: {pos.get('direction')} on {pos.get('exchange')}")

    sentiment_history = []
    cycle = 0
    storm_active = False
    last_blackbox_save = datetime.utcnow()
    last_mutation = datetime.utcnow()
    last_cycle_hour = datetime.utcnow().hour
    stopped = False

    while True:
        cycle += 1
        now = datetime.utcnow()

        try:
            # ── Kill switch check ─────────────────
            try:
                r = requests.get(f"{ARIA_URL}/agents/status", timeout=5)
                if r.json().get('stopped'):
                    if not stopped:
                        print(f"[{now.strftime('%H:%M:%S')}] KILL SWITCH ACTIVE")
                    stopped = True
                    continue
                stopped = False
            except:
                pass

            # ── Get market state ──────────────────
            try:
                state = requests.get(f"{ARIA_URL}/agent/state", timeout=15).json()
                port = requests.get(f"{ARIA_URL}/paper/portfolio/{PAPER_USER}", timeout=10).json()
                balance = float(port.get('balance', 10000))
            except Exception as e:
                print(f"  [STATE] Failed to get state: {e}")
                time.sleep(LOOP_INTERVAL)
                continue

            # ── Build signal bus ──────────────────
            bus = build_signal_bus(state)

            # ── Layer 1: Data agents ──────────────
            bus = run_data_agents(bus, sentiment_history)

            # ── Layer 2: Analysis agents ──────────
            bus = run_analysis_agents(bus)

            # ── Storm Protocol ────────────────────
            is_storm, triggers = check_storm(bus, balance)
            bus['storm_active'] = is_storm

            if is_storm and not storm_active:
                storm_active = True
                print(f"\n  [STORM] 🌩️  STORM PROTOCOL ACTIVATED: {triggers}")
                print(f"  [STORM] Closing risky positions, moving to safe haven...")
                for sym in list(open_positions.keys()):
                    if sym != 'GLD':
                        close_position(sym, open_positions)
                        time.sleep(0.5)
                # Open GLD long as safe haven
                if 'GLD' not in open_positions:
                    if aria_open_trade('GLD', 'LONG'):
                        open_positions['GLD'] = {
                            'direction': 'LONG', 'cycle': cycle,
                            'exchange': 'aria_paper', 'size': TRADE_AMOUNT
                        }
                        print(f"  [STORM] 🥇 Safe haven: GLD LONG opened")

            elif storm_active and storm_all_clear(bus):
                storm_active = False
                print(f"  [STORM] ✅ All clear — resuming normal operations")

            # ── Build market fingerprint ──────────
            fingerprint = build_fingerprint(bus)

            # Print cycle header
            print(f"\n[{now.strftime('%H:%M:%S')}] Cycle {cycle} | "
                  f"Regime:{bus['regime']} Macro:{bus['macro_signal']} "
                  f"Sentiment:{bus['sentiment']:.0f} VelX:{bus['sentiment_velocity']:+.1f} "
                  f"Funding:{bus['funding_btc']:+.4f} Storm:{'🌩️' if storm_active else '☀️'}")
            print(f"  Open: {list(open_positions.keys())} | Balance: ${balance:.0f}")

            if storm_active:
                print(f"  [STORM] Waiting for all-clear...")
                time.sleep(LOOP_INTERVAL)
                continue

            # ── Layer 3: Strategy agents ──────────
            raw_decisions = []
            for agent in agents:
                if agent['layer'] != 3:
                    continue
                symbol = agent.get('symbol')

                result = run_strategy_agent(agent, bus, fingerprint, open_positions, cycle)
                action, conf, direction, size_mult, territory = result

                if action not in ['HOLD'] and direction:
                    raw_decisions.append({
                        'agent_id': agent['id'],
                        'symbol': symbol,
                        'action': action,
                        'confidence': conf,
                        'direction': direction,
                        'size_multiplier': size_mult,
                        'territory': territory
                    })

                status = f"{action:8} {direction or '----':5} ({conf:.2f}) [{territory[:3]}]"
                print(f"  {agent['id']:22} {status}")

            # ── Layer 4: Meta agent ───────────────
            raw_decisions = run_meta_agent(raw_decisions, bus)

            # ── Risk agent ────────────────────────
            approved = run_risk_agent(raw_decisions, bus, balance, open_positions)
            print(f"  Approved: {len(approved)}/{len(raw_decisions)} decisions")
            for sym, pos in open_positions.items():
                aria_report('position_tracker', 'POSITION', sym, 'OPEN', 0.99,
                            f"{pos.get('direction','LONG')} exchange={pos.get('exchange','aria_paper')} entry={pos.get('entry_price',0)}")

            # ── Execute ───────────────────────────
            for decision in approved:
                execute_trade(decision, open_positions, cycle)

            # ── Black Box save every 15 mins ──────
            if (now - last_blackbox_save).seconds >= 900:
                snapshot = {
                    'open_positions': open_positions,
                    'cycle': cycle,
                    'balance': balance,
                    'regime': bus['regime'],
                    'storm_active': storm_active,
                    'timestamp': now.isoformat()
                }
                save_blackbox(snapshot)
                last_blackbox_save = now
                print(f"  [BLACKBOX] 💾 Snapshot saved")

            # ── Nightly mutation (2 AM) ───────────
            current_hour = now.hour
            if current_hour == 2 and last_cycle_hour != 2:
                print(f"\n  [MUTATION] 🧬 Nightly mutation engine running...")
                agents = run_mutation_engine(agents)
            last_cycle_hour = current_hour

        except Exception as e:
            print(f"  [ERROR] {e}")
            import traceback
            traceback.print_exc()

        # Push positions to Railway every cycle
        try:
            pos_data = []
            for sym, pos in open_positions.items():
                pos_data.append({
                    'symbol': sym,
                    'direction': pos.get('direction', 'LONG'),
                    'exchange': pos.get('exchange', 'aria_paper'),
                    'size': pos.get('size', 100)
                })
            requests.post(f"{ARIA_URL}/positions/update",
                json={'positions': pos_data}, timeout=5)
        except: pass
        time.sleep(LOOP_INTERVAL)

if __name__ == '__main__':
    main()
