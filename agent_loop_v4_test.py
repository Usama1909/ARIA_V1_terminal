# agent_loop.py - ARIA Autonomous Trading Agents v4
# 18 agents - multiple strategies per asset
# LONG and SHORT positions directly
# 4 hour minimum hold time

import requests
import time
import json
import numpy as np
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────
ARIA_URL        = "https://web-production-548c0.up.railway.app"
LOOP_INTERVAL   = 60
PAPER_USER      = "aria-test-v4"
MIN_HOLD_CYCLES = 240
TRADE_AMOUNT    = 100.0
MAX_DRAWDOWN    = 0.15
MIN_CONFIDENCE  = 0.55
MAX_OPEN_TRADES = 3

# ── POSITION TRACKING ─────────────────────────────────────
open_positions = {}

# ── AGENT DEFINITIONS ─────────────────────────────────────
AGENTS = [
    # BTC - 3 strategies
    {'id': 'agent_btc_momentum',  'type': 'SPECIALIST', 'symbol': 'BTC',  'strategy': 'momentum'},
    {'id': 'agent_btc_reversion', 'type': 'SPECIALIST', 'symbol': 'BTC',  'strategy': 'reversion'},
    {'id': 'agent_btc_volume',    'type': 'SPECIALIST', 'symbol': 'BTC',  'strategy': 'volume'},
    # ETH - 3 strategies
    {'id': 'agent_eth_momentum',  'type': 'SPECIALIST', 'symbol': 'ETH',  'strategy': 'momentum'},
    {'id': 'agent_eth_reversion', 'type': 'SPECIALIST', 'symbol': 'ETH',  'strategy': 'reversion'},
    {'id': 'agent_eth_volume',    'type': 'SPECIALIST', 'symbol': 'ETH',  'strategy': 'volume'},
    # TSLA - 3 strategies
    {'id': 'agent_tsla_tech',     'type': 'SPECIALIST', 'symbol': 'TSLA', 'strategy': 'technical'},
    {'id': 'agent_tsla_momentum', 'type': 'SPECIALIST', 'symbol': 'TSLA', 'strategy': 'momentum'},
    {'id': 'agent_tsla_sentiment','type': 'SPECIALIST', 'symbol': 'TSLA', 'strategy': 'sentiment'},
    # GLD - 3 strategies
    {'id': 'agent_gold_fear',     'type': 'SPECIALIST', 'symbol': 'GLD',  'strategy': 'fear'},
    {'id': 'agent_gold_dxy',      'type': 'SPECIALIST', 'symbol': 'GLD',  'strategy': 'dxy'},
    {'id': 'agent_gold_macro',    'type': 'SPECIALIST', 'symbol': 'GLD',  'strategy': 'macro'},
    # Single agents
    {'id': 'agent_aapl',          'type': 'SPECIALIST', 'symbol': 'AAPL', 'strategy': 'technical'},
    {'id': 'agent_tech',          'type': 'SPECIALIST', 'symbol': 'NVDA', 'strategy': 'technical'},
    # Analytical agents
    {'id': 'agent_macro',         'type': 'MACRO',      'symbol': None,   'strategy': 'macro'},
    {'id': 'agent_sentiment',     'type': 'SENTIMENT',  'symbol': None,   'strategy': 'sentiment'},
    {'id': 'agent_regime',        'type': 'REGIME',     'symbol': None,   'strategy': 'regime'},
    {'id': 'agent_risk',          'type': 'RISK',       'symbol': None,   'strategy': 'risk'},
]

# ── REPORT TO ARIA ─────────────────────────────────────────
def report_to_aria(agent_id, agent_type, symbol, action, confidence, reasoning):
    try:
        requests.post(f"{ARIA_URL}/agent/report", json={
            'agent_id': agent_id, 'agent_type': agent_type,
            'symbol': symbol, 'action': action,
            'confidence': confidence, 'reasoning': reasoning,
            'timestamp': datetime.utcnow().isoformat()
        }, timeout=5)
    except:
        pass

# ── MACRO AGENT ────────────────────────────────────────────
def run_macro_agent(state):
    macro = state.get('macro', {})
    vix   = float(macro.get('vix', 20) or 20)
    yield_curve = float(macro.get('yield_curve', 0) or 0) if not isinstance(macro.get('yield_curve',''), str) else 0.0
    crisis = float(macro.get('crisis_score', 0) or 0)
    if crisis > 75 or vix > 35:
        signal, reasoning = 'CRISIS', f"Crisis score {crisis}, VIX {vix:.1f}"
    elif vix > 25 or yield_curve < 0:
        signal, reasoning = 'RISK_OFF', f"VIX {vix:.1f}, yield curve {yield_curve:.3f}"
    else:
        signal, reasoning = 'RISK_ON', f"VIX {vix:.1f} normal, yield curve {yield_curve:.3f}"
    report_to_aria('agent_macro', 'MACRO', None, signal, 0.75, reasoning)
    return signal

# ── SENTIMENT AGENT ────────────────────────────────────────
def run_sentiment_agent(state):
    assets = state.get('assets', {})
    fg_values = [float(a.get('fear_greed', 50) or 50) for a in assets.values() if a]
    avg_fg = np.mean(fg_values) if fg_values else 50
    if avg_fg < 20:
        signal, reasoning = 'EXTREME_FEAR', f"F&G {avg_fg:.0f}"
    elif avg_fg < 40:
        signal, reasoning = 'FEAR', f"F&G {avg_fg:.0f}"
    elif avg_fg > 75:
        signal, reasoning = 'GREED', f"F&G {avg_fg:.0f}"
    else:
        signal, reasoning = 'NEUTRAL', f"F&G {avg_fg:.0f}"
    report_to_aria('agent_sentiment', 'SENTIMENT', None, signal, 0.65, reasoning)
    return signal

# ── REGIME AGENT ───────────────────────────────────────────
def run_regime_agent(state):
    assets = state.get('assets', {})
    changes = [float(a.get('change_24h', 0) or 0) for a in assets.values() if a]
    avg_change = np.mean(changes) if changes else 0
    if avg_change > 3:
        regime = 'BULL'
    elif avg_change < -3:
        regime = 'BEAR'
    else:
        regime = 'SIDEWAYS'
    report_to_aria('agent_regime', 'REGIME', None, regime, 0.75, f"Avg 24h change: {avg_change:.2f}%")
    return regime

# ── MOMENTUM STRATEGY ──────────────────────────────────────
def momentum_signal(asset):
    rsi        = asset.get('rsi', 50)
    change_24h = asset.get('change_24h', 0)
    confidence = asset.get('confidence', 0.5)
    # Momentum: ride the trend
    if change_24h > 2 and rsi > 50 and rsi < 70:
        return 'LONG', min(confidence + 0.1, 0.95), f"Momentum UP chg={change_24h:.1f}% RSI={rsi:.0f}"
    elif change_24h < -2 and rsi < 50 and rsi > 30:
        return 'SHORT', min(confidence + 0.1, 0.95), f"Momentum DOWN chg={change_24h:.1f}% RSI={rsi:.0f}"
    return None, confidence, "No momentum signal"

# ── MEAN REVERSION STRATEGY ────────────────────────────────
def reversion_signal(asset):
    rsi        = asset.get('rsi', 50)
    confidence = asset.get('confidence', 0.5)
    # Mean reversion: fade extremes
    if rsi < 25:
        return 'LONG', 0.80, f"Oversold RSI={rsi:.0f} - expect bounce"
    elif rsi > 75:
        return 'SHORT', 0.80, f"Overbought RSI={rsi:.0f} - expect pullback"
    return None, confidence, "No reversion signal"

# ── VOLUME STRATEGY ────────────────────────────────────────
def volume_signal(asset):
    signal     = asset.get('signal', {})
    xgb        = signal if isinstance(signal, str) else signal.get('signal', 'HOLD') if signal else 'HOLD'
    confidence = asset.get('confidence', 0.5)
    vpin       = asset.get('vpin', 0.5)
    # Volume: follow informed traders
    if vpin > 0.7 and xgb == 'TAKE_PROFIT':
        return 'LONG', min(confidence + 0.15, 0.95), f"High VPIN={vpin:.2f} bullish"
    elif vpin > 0.7 and xgb == 'STOP_LOSS':
        return 'SHORT', min(confidence + 0.15, 0.95), f"High VPIN={vpin:.2f} bearish"
    return None, confidence, "No volume signal"

# ── TECHNICAL STRATEGY ─────────────────────────────────────
def technical_signal(asset):
    signal     = asset.get('signal', {})
    xgb        = signal if isinstance(signal, str) else signal.get('signal', 'HOLD') if signal else 'HOLD'
    confidence = asset.get('confidence', 0.5)
    rsi        = asset.get('rsi', 50)
    if xgb == 'TAKE_PROFIT':
        direction = 'LONG'
    else:
        direction = 'SHORT'
    if rsi < 30:
        direction = 'LONG'
    elif rsi > 70:
        direction = 'SHORT'
    return direction, confidence, f"XGB={xgb} RSI={rsi:.0f} conf={confidence:.2f}"

# ── FEAR STRATEGY (GLD) ────────────────────────────────────
def fear_signal(asset, macro_signal, sentiment_signal):
    fg = asset.get('fear_greed', 50)
    if macro_signal == 'CRISIS' or sentiment_signal == 'EXTREME_FEAR':
        return 'LONG', 0.85, f"Crisis/Fear detected - GLD safe haven F&G={fg}"
    elif fg < 30:
        return 'LONG', 0.75, f"Fear market F&G={fg} - GLD benefits"
    elif fg > 70:
        return 'SHORT', 0.65, f"Greed market F&G={fg} - GLD weakens"
    return None, 0.5, "No fear signal"

# ── DXY STRATEGY (GLD) ─────────────────────────────────────
def dxy_signal(asset, state):
    macro  = state.get('macro', {})
    dxy    = macro.get('dxy', 100)
    change = asset.get('change_24h', 0)
    # Gold moves inverse to USD
    if dxy < 99:
        return 'LONG', 0.75, f"DXY weak={dxy:.1f} - GLD should rise"
    elif dxy > 103:
        return 'SHORT', 0.70, f"DXY strong={dxy:.1f} - GLD under pressure"
    return None, 0.5, "DXY neutral"

# ── SENTIMENT STRATEGY (TSLA) ──────────────────────────────
def tsla_sentiment_signal(asset, sentiment_signal):
    change = asset.get('change_24h', 0)
    rsi    = asset.get('rsi', 50)
    if sentiment_signal in ['GREED'] and change > 1:
        return 'LONG', 0.70, f"Greed + TSLA momentum chg={change:.1f}%"
    elif sentiment_signal in ['FEAR', 'EXTREME_FEAR'] and change < -1:
        return 'SHORT', 0.70, f"Fear + TSLA selling chg={change:.1f}%"
    return None, 0.5, "No sentiment signal for TSLA"

# ── SPECIALIST AGENT ──────────────────────────────────────
def run_specialist_agent(agent, state, macro_signal, sentiment_signal, cycle):
    symbol   = agent['symbol']
    strategy = agent.get('strategy', 'technical')
    assets   = state.get('assets', {})

    if symbol not in assets or not assets[symbol]:
        return 'HOLD', 0.5, None

    asset = assets[symbol]

    # Check minimum hold time
    if symbol in open_positions:
        pos         = open_positions[symbol]
        cycles_held = cycle - pos['cycle']
        if cycles_held < MIN_HOLD_CYCLES:
            reasoning = f"Holding {pos['direction']} {symbol} - {cycles_held}/{MIN_HOLD_CYCLES} cycles"
            report_to_aria(agent['id'], agent['type'], symbol, 'HOLD',
                          asset.get('confidence', 0.5), reasoning)
            return 'HOLD', asset.get('confidence', 0.5), None

    # Crisis override
    if macro_signal == 'CRISIS':
        if symbol == 'GLD':
            report_to_aria(agent['id'], agent['type'], symbol, 'BUY', 0.9, "CRISIS - GLD safe haven")
            return 'BUY', 0.9, 'LONG'
        else:
            report_to_aria(agent['id'], agent['type'], symbol, 'HOLD', 0.5, "CRISIS - staying out")
            return 'HOLD', 0.5, None

    # Get direction from strategy
    if strategy == 'momentum':
        direction, confidence, reasoning = momentum_signal(asset)
    elif strategy == 'reversion':
        direction, confidence, reasoning = reversion_signal(asset)
    elif strategy == 'volume':
        direction, confidence, reasoning = volume_signal(asset)
    elif strategy == 'fear':
        direction, confidence, reasoning = fear_signal(asset, macro_signal, sentiment_signal)
    elif strategy == 'dxy':
        direction, confidence, reasoning = dxy_signal(asset, state)
    elif strategy == 'sentiment':
        direction, confidence, reasoning = tsla_sentiment_signal(asset, sentiment_signal)
    else:
        direction, confidence, reasoning = technical_signal(asset)

    # No signal
    if direction is None:
        report_to_aria(agent['id'], agent['type'], symbol, 'HOLD', confidence, reasoning)
        return 'HOLD', confidence, None

    # Macro filter
    if macro_signal == 'RISK_OFF' and symbol in ['BTC', 'ETH', 'NVDA', 'TSLA']:
        direction = 'SHORT'
        reasoning += ' [RISK_OFF override]'

    # Confidence check
    if confidence < MIN_CONFIDENCE:
        report_to_aria(agent['id'], agent['type'], symbol, 'HOLD', confidence,
                      f"Confidence {confidence:.2f} below {MIN_CONFIDENCE}")
        return 'HOLD', confidence, None

    # Position management
    if symbol in open_positions:
        current_dir = open_positions[symbol]['direction']
        if current_dir != direction:
            action = 'REVERSE'
            reasoning = f"{symbol} reversing {current_dir}→{direction}"
        else:
            action = 'HOLD'
            reasoning = f"{symbol} holding {current_dir}"
    else:
        action = 'BUY' if direction == 'LONG' else 'SELL'

    report_to_aria(agent['id'], agent['type'], symbol, action, confidence, reasoning)
    return action, confidence, direction

# ── RISK MANAGER ──────────────────────────────────────────
def risk_manager(decisions, state, balance):
    macro    = state.get('macro', {})
    crisis   = macro.get('crisis_score', 0)
    drawdown = (10000 - balance) / 10000

    if drawdown > MAX_DRAWDOWN:
        print(f"  KILL SWITCH: Drawdown {drawdown*100:.1f}%")
        report_to_aria('agent_risk', 'RISK', None, 'KILL_SWITCH', 1.0,
                      f"Drawdown {drawdown*100:.1f}% - halted")
        return []

    # Per-symbol consensus — require 2/3 agents to agree
    symbol_votes = {}
    for agent_id, symbol, action, confidence, direction in decisions:
        if symbol not in symbol_votes:
            symbol_votes[symbol] = []
        symbol_votes[symbol].append((agent_id, action, confidence, direction))

    approved  = []
    current_open = len(open_positions)

    for symbol, votes in symbol_votes.items():
        # Count direction votes
        long_votes  = [(a,c,d) for a,ac,c,d in votes if d == 'LONG']
        short_votes = [(a,c,d) for a,ac,c,d in votes if d == 'SHORT']
        action_votes = [(a,ac,c,d) for a,ac,c,d in votes if ac not in ['HOLD']]

        if not action_votes:
            continue

        # Consensus: majority must agree
        total = len(votes)
        long_count  = len(long_votes)
        short_count = len(short_votes)

        if long_count > short_count and long_count >= max(1, total//2):
            consensus_dir = 'LONG'
            avg_conf = np.mean([c for _,c,_ in long_votes])
        elif short_count > long_count and short_count >= max(1, total//2):
            consensus_dir = 'SHORT'
            avg_conf = np.mean([c for _,c,_ in short_votes])
        else:
            report_to_aria('agent_risk', 'RISK', symbol, 'VETO', 1.0,
                          f"No consensus for {symbol}")
            continue

        # Risk checks
        if crisis >= 75 and symbol not in ['GLD']:
            report_to_aria('agent_risk', 'RISK', symbol, 'VETO', 1.0,
                          f"Crisis {crisis} - safe havens only")
            continue

        if symbol not in open_positions and current_open >= MAX_OPEN_TRADES:
            report_to_aria('agent_risk', 'RISK', symbol, 'VETO', 1.0,
                          f"Max {MAX_OPEN_TRADES} positions reached")
            continue

        action = 'BUY' if consensus_dir == 'LONG' else 'SELL'
        if symbol in open_positions:
            if open_positions[symbol]['direction'] != consensus_dir:
                action = 'REVERSE'
            else:
                continue

        best_agent = action_votes[0][0]
        approved.append((best_agent, symbol, action, avg_conf, consensus_dir))
        report_to_aria('agent_risk', 'RISK', symbol, 'APPROVED', avg_conf,
                      f"Consensus {consensus_dir} ({long_count}L/{short_count}S) on {symbol}")

    return approved

# ── PORTFOLIO ─────────────────────────────────────────────
def get_portfolio_balance():
    try:
        r = requests.get(f"{ARIA_URL}/paper/portfolio/{PAPER_USER}", timeout=10)
        return r.json().get('balance', 10000)
    except:
        return 10000

def close_position(symbol):
    try:
        r = requests.get(f"{ARIA_URL}/paper/portfolio/{PAPER_USER}", timeout=10)
        trades = r.json().get('open_trades', [])
        for t in trades:
            if t['symbol'] == symbol:
                requests.post(f"{ARIA_URL}/paper/close", json={
                    'user_id': PAPER_USER, 'trade_id': t['trade_id']
                }, timeout=10)
                return True
    except:
        pass
    return False

def execute_trade(symbol, direction, amount=TRADE_AMOUNT):
    try:
        r = requests.post(f"{ARIA_URL}/paper/trade", json={
            'user_id': PAPER_USER, 'symbol': symbol,
            'direction': direction, 'amount_usd': amount
        }, timeout=10)
        return r.json().get('success', False)
    except:
        return False

# ── MAIN LOOP ─────────────────────────────────────────────
def main():
    print("="*60)
    print("ARIA AUTONOMOUS AGENT SYSTEM v4")
    print(f"Agents:         {len(AGENTS)}")
    print(f"Interval:       {LOOP_INTERVAL}s")
    print(f"Min confidence: {MIN_CONFIDENCE}")
    print(f"Min hold:       {MIN_HOLD_CYCLES} cycles ({MIN_HOLD_CYCLES//60}h)")
    print(f"Max positions:  {MAX_OPEN_TRADES}")
    print(f"Trade size:     ${TRADE_AMOUNT}")
    print("="*60)

    cycle = 0
    stopped = False

    while True:
        cycle += 1
        try:
            # Check kill switch
            try:
                r = requests.get(f"{ARIA_URL}/agents/status", timeout=5)
                if r.json().get('stopped'):
                    if not stopped:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] KILL SWITCH ACTIVE")
                    stopped = True
                    time.sleep(LOOP_INTERVAL)
                    continue
                stopped = False
            except:
                pass

            # Get market state
            state = requests.get(f"{ARIA_URL}/agent/state", timeout=15).json()
            balance = get_portfolio_balance()

            # Sync open positions
            try:
                port = requests.get(f"{ARIA_URL}/paper/portfolio/{PAPER_USER}", timeout=10).json()
                synced = {t['symbol']: {'direction': t['direction'].upper(), 'cycle': cycle - MIN_HOLD_CYCLES}
                         for t in port.get('open_trades', [])}
                for sym in list(open_positions.keys()):
                    if sym not in synced:
                        del open_positions[sym]
                for sym, data in synced.items():
                    if sym not in open_positions:
                        open_positions[sym] = data
            except:
                pass

            # Run analytical agents
            macro_signal     = run_macro_agent(state)
            sentiment_signal = run_sentiment_agent(state)
            regime           = run_regime_agent(state)

            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Cycle {cycle} | Open: {list(open_positions.keys())}")
            print(f"  Macro:{macro_signal} Sentiment:{sentiment_signal} Regime:{regime} Balance:$" + str(int(balance)) + "")

            # Run specialist agents
            decisions = []
            for agent in AGENTS:
                if agent['type'] != 'SPECIALIST':
                    continue
                action, confidence, direction = run_specialist_agent(
                    agent, state, macro_signal, sentiment_signal, cycle)
                print(f"  {agent['id']:30} {action:8} ({confidence:.2f})")
                if action not in ['HOLD'] and direction:
                    decisions.append((agent['id'], agent['symbol'], action, confidence, direction))

            # Risk approval with consensus
            approved = risk_manager(decisions, state, balance)
            print(f"  Approved: {len(approved)}")

            # Execute trades
            for agent_id, symbol, action, confidence, direction in approved:
                if action == 'REVERSE':
                    close_position(symbol)
                    time.sleep(1)
                    if open_positions.get(symbol):
                        del open_positions[symbol]
                    success = execute_trade(symbol, direction)
                    if success:
                        open_positions[symbol] = {'direction': direction, 'cycle': cycle}
                        print(f"  REVERSED: {direction} {symbol}")
                elif action in ['BUY', 'SELL']:
                    success = execute_trade(symbol, direction)
                    if success:
                        open_positions[symbol] = {'direction': direction, 'cycle': cycle}
                        print(f"  EXECUTED: {direction} {symbol}")

        except Exception as e:
            print(f"  Error: {e}")

        time.sleep(LOOP_INTERVAL)

if __name__ == '__main__':
    main()
