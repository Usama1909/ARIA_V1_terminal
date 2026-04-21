# agent_loop.py - ARIA Autonomous Trading Agents v3
# Self-healing: auto-reopens positions if Railway restarts
import requests, time, json, numpy as np
from datetime import datetime

ARIA_URL        = "https://web-production-548c0.up.railway.app"
LOOP_INTERVAL   = 60
PAPER_USER      = "aria-agent-system"
MIN_HOLD_CYCLES = 240
TRADE_AMOUNT    = 100.0
MAX_DRAWDOWN    = 0.15
MIN_CONFIDENCE  = 0.55
MAX_OPEN_TRADES = 5

open_positions = {}

AGENTS = [
    {'id': 'agent_btc',       'type': 'SPECIALIST', 'symbol': 'BTC'},
    {'id': 'agent_eth',       'type': 'SPECIALIST', 'symbol': 'ETH'},
    {'id': 'agent_tech',      'type': 'SPECIALIST', 'symbol': 'NVDA'},
    {'id': 'agent_gold',      'type': 'SPECIALIST', 'symbol': 'GLD'},
    {'id': 'agent_aapl',      'type': 'SPECIALIST', 'symbol': 'AAPL'},
    {'id': 'agent_tsla',      'type': 'SPECIALIST', 'symbol': 'TSLA'},
    {'id': 'agent_macro',     'type': 'MACRO',      'symbol': None},
    {'id': 'agent_sentiment', 'type': 'SENTIMENT',  'symbol': None},
    {'id': 'agent_regime',    'type': 'REGIME',     'symbol': None},
    {'id': 'agent_risk',      'type': 'RISK',       'symbol': None},
]

def report(agent_id, agent_type, symbol, action, confidence, reasoning):
    try:
        requests.post(f"{ARIA_URL}/agent/report", json={
            'agent_id': agent_id, 'agent_type': agent_type,
            'symbol': symbol, 'action': action,
            'confidence': float(confidence), 'reasoning': reasoning,
            'timestamp': datetime.utcnow().isoformat()
        }, timeout=5)
    except: pass

def get_portfolio():
    try:
        r = requests.get(f"{ARIA_URL}/paper/portfolio/{PAPER_USER}", timeout=10)
        return r.json()
    except: return {'balance': 10000, 'open_count': 0, 'open_trades': []}

def open_trade(symbol, direction):
    try:
        r = requests.post(f"{ARIA_URL}/paper/trade", json={
            'user_id': PAPER_USER, 'symbol': symbol,
            'direction': direction, 'amount_usd': TRADE_AMOUNT
        }, timeout=10)
        return r.json().get('success', False)
    except: return False

def close_trade(symbol):
    try:
        port = get_portfolio()
        for t in port.get('open_trades', []):
            if t['symbol'] == symbol:
                requests.post(f"{ARIA_URL}/paper/close", json={
                    'user_id': PAPER_USER, 'trade_id': t['trade_id']
                }, timeout=10)
                return True
    except: pass
    return False

def self_heal(cycle):
    """Only runs on cycle 1 — re-opens positions if Railway wiped them"""
    global open_positions
    port = get_portfolio()
    balance = port.get('balance', 10000)
    open_count = port.get('open_count', 0)

    # Sync open_positions from portfolio
    if open_count > 0:
        for t in port.get('open_trades', []):
            sym = t['symbol']
            if sym not in open_positions:
                open_positions[sym] = {'direction': t['direction'].upper(), 'cycle': cycle - MIN_HOLD_CYCLES}
        print(f"  [SYNC] Loaded {open_count} existing positions from portfolio")
        return

    # Portfolio empty + balance = $10,000 = Railway restart
    if balance == 10000.0 and open_count == 0:
        print(f"  [SELF-HEAL] Railway restart detected — re-opening positions...")
        for symbol in ['BTC', 'ETH', 'GLD', 'AAPL', 'TSLA']:
            if open_trade(symbol, 'SHORT'):
                open_positions[symbol] = {'direction': 'SHORT', 'cycle': cycle}
                print(f"  [SELF-HEAL] Reopened SHORT {symbol}")
                time.sleep(1)

def run_macro(state):
    macro = state.get('macro', {})
    vix = float(macro.get('vix', 20) or 20)
    crisis = float(macro.get('crisis_score', 0) or 0)
    if crisis > 75 or vix > 35:
        signal = 'CRISIS'
    elif vix > 25:
        signal = 'RISK_OFF'
    else:
        signal = 'RISK_ON'
    report('agent_macro', 'MACRO', None, signal, 0.75, f"VIX={vix:.1f} crisis={crisis:.0f}")
    return signal

def run_sentiment(state):
    assets = state.get('assets', {})
    fgs = [float(a.get('fear_greed', 50) or 50) for a in assets.values() if a]
    avg = np.mean(fgs) if fgs else 50
    signal = 'EXTREME_FEAR' if avg < 20 else 'FEAR' if avg < 40 else 'GREED' if avg > 75 else 'NEUTRAL'
    report('agent_sentiment', 'SENTIMENT', None, signal, 0.65, f"F&G={avg:.0f}")
    return signal

def run_regime(state):
    assets = state.get('assets', {})
    changes = [float(a.get('change_24h', 0) or 0) for a in assets.values() if a]
    avg = np.mean(changes) if changes else 0
    regime = 'BULL' if avg > 3 else 'BEAR' if avg < -3 else 'SIDEWAYS'
    report('agent_regime', 'REGIME', None, regime, 0.75, f"avg_change={avg:.2f}%")
    return regime

def run_specialist(agent, state, macro, sentiment, cycle):
    symbol = agent['symbol']
    assets = state.get('assets', {})
    if symbol not in assets or not assets[symbol]:
        return 'HOLD', 0.5, None
    asset = assets[symbol]
    confidence = float(asset.get('confidence', 0.5) or 0.5)
    rsi = float(asset.get('rsi', 50) or 50)
    signal = asset.get('signal', 'HOLD')
    xgb = signal if isinstance(signal, str) else signal.get('signal', 'HOLD') if signal else 'HOLD'

    # Check hold time
    if symbol in open_positions:
        pos = open_positions[symbol]
        held = cycle - pos['cycle']
        if held < MIN_HOLD_CYCLES:
            report(agent['id'], agent['type'], symbol, 'HOLD', confidence,
                   f"Holding {pos['direction']} {symbol} {held}/{MIN_HOLD_CYCLES} cycles")
            return 'HOLD', confidence, None

    # Crisis override
    if macro == 'CRISIS':
        if symbol == 'GLD':
            report(agent['id'], agent['type'], symbol, 'BUY', 0.9, "CRISIS - GLD safe haven")
            return 'BUY', 0.9, 'LONG'
        report(agent['id'], agent['type'], symbol, 'HOLD', 0.5, "CRISIS - staying out")
        return 'HOLD', 0.5, None

    # Direction
    direction = 'LONG' if xgb == 'TAKE_PROFIT' else 'SHORT'
    if rsi < 30: direction = 'LONG'
    elif rsi > 70: direction = 'SHORT'
    if macro == 'RISK_OFF' and symbol in ['BTC', 'ETH', 'NVDA', 'TSLA']:
        direction = 'SHORT'
    if sentiment == 'EXTREME_FEAR' and symbol == 'GLD':
        direction = 'LONG'

    if confidence < MIN_CONFIDENCE:
        report(agent['id'], agent['type'], symbol, 'HOLD', confidence, f"Low confidence {confidence:.2f}")
        return 'HOLD', confidence, None

    # Action
    if symbol in open_positions:
        cur = open_positions[symbol]['direction']
        action = 'REVERSE' if cur != direction else 'HOLD'
        reasoning = f"{symbol} {'reversing' if action=='REVERSE' else 'holding'} {cur}→{direction}"
    else:
        action = 'BUY' if direction == 'LONG' else 'SELL'
        reasoning = f"{symbol} {direction} conf={confidence:.2f} RSI={rsi:.0f}"

    report(agent['id'], agent['type'], symbol, action, confidence, reasoning)
    return action, confidence, direction

def risk_check(decisions, state, balance):
    macro = state.get('macro', {})
    crisis = float(macro.get('crisis_score', 0) or 0)
    drawdown = (10000 - balance) / 10000
    if drawdown > MAX_DRAWDOWN:
        print(f"  KILL SWITCH: Drawdown {drawdown*100:.1f}%")
        report('agent_risk', 'RISK', None, 'KILL_SWITCH', 1.0, f"Drawdown {drawdown*100:.1f}%")
        return []
    approved = []
    open_count = len(open_positions)
    for agent_id, symbol, action, confidence, direction in decisions:
        if crisis >= 75 and symbol not in ['GLD']:
            report('agent_risk', 'RISK', symbol, 'VETO', 1.0, f"Crisis {crisis:.0f}")
            continue
        if action in ['BUY', 'SELL'] and open_count >= MAX_OPEN_TRADES:
            report('agent_risk', 'RISK', symbol, 'VETO', 1.0, f"Max {MAX_OPEN_TRADES} positions")
            continue
        if action != 'HOLD':
            approved.append((agent_id, symbol, action, confidence, direction))
            report('agent_risk', 'RISK', symbol, 'APPROVED', 1.0, f"Approved {action} {symbol}")
            if action in ['BUY', 'SELL']:
                open_count += 1
    return approved

def main():
    print("=" * 60)
    print("ARIA AUTONOMOUS AGENT SYSTEM v3")
    print(f"Agents:         {len(AGENTS)}")
    print(f"Interval:       {LOOP_INTERVAL}s")
    print(f"Min confidence: {MIN_CONFIDENCE}")
    print(f"Min hold:       {MIN_HOLD_CYCLES} cycles ({MIN_HOLD_CYCLES//60}h)")
    print(f"Max positions:  {MAX_OPEN_TRADES}")
    print(f"Trade size:     ${TRADE_AMOUNT}")
    print("=" * 60)

    cycle = 0
    stopped = False

    while True:
        cycle += 1
        try:
            # Kill switch check
            try:
                r = requests.get(f"{ARIA_URL}/agents/status", timeout=5)
                if r.json().get('stopped'):
                    if not stopped:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] KILL SWITCH ACTIVE")
                    stopped = True
                    time.sleep(LOOP_INTERVAL)
                    continue
                stopped = False
            except: pass

            # Self-heal on first cycle only
            if cycle == 1:
                self_heal(cycle)

            # Get state
            state = requests.get(f"{ARIA_URL}/agent/state", timeout=15).json()
            port = get_portfolio()
            balance = port.get('balance', 10000)

            # Trust agent memory - only add from API if memory is empty
            if len(open_positions) == 0 and len(port.get('open_trades', [])) > 0:
                for t in port.get('open_trades', []):
                    open_positions[t['symbol']] = {'direction': t['direction'].upper(), 'cycle': cycle - MIN_HOLD_CYCLES}

            # Run analytical agents
            macro = run_macro(state)
            sentiment = run_sentiment(state)
            regime = run_regime(state)

            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Cycle {cycle} | Open positions: {list(open_positions.keys())}")
            print(f"  Macro:{macro} Sentiment:{sentiment} F&G:23 Regime:{regime} Balance:${int(balance)}")

            # Run specialist agents
            decisions = []
            for agent in AGENTS:
                if agent['type'] != 'SPECIALIST':
                    continue
                action, confidence, direction = run_specialist(agent, state, macro, sentiment, cycle)
                status = f"{action:12} ({confidence:.2f})"
                print(f"  {agent['id']:20} {status}")
                if action not in ['HOLD'] and direction:
                    decisions.append((agent['id'], agent['symbol'], action, confidence, direction))

            # Risk approval
            approved = risk_check(decisions, state, balance)
            print(f"  Approved: {len(approved)}")

            # Execute trades
            for agent_id, symbol, action, confidence, direction in approved:
                if action == 'REVERSE':
                    close_trade(symbol)
                    time.sleep(1)
                    open_positions.pop(symbol, None)
                    if open_trade(symbol, direction):
                        open_positions[symbol] = {'direction': direction, 'cycle': cycle}
                        print(f"  REVERSED: {direction} {symbol}")
                elif action in ['BUY', 'SELL']:
                    if open_trade(symbol, direction):
                        open_positions[symbol] = {'direction': direction, 'cycle': cycle}
                        print(f"  EXECUTED: {direction} {symbol} @ market")

        except Exception as e:
            print(f"  Error: {e}")

        time.sleep(LOOP_INTERVAL)

if __name__ == '__main__':
    main()
