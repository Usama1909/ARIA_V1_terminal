# agent_loop.py - ARIA Autonomous Trading Agents v3
# All agents trade all assets simultaneously
# LONG and SHORT positions directly
# 4 hour minimum hold time

import requests
import time
import json
import numpy as np
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────
ARIA_URL        = "https://web-production-548c0.up.railway.app"
LOOP_INTERVAL   = 60     # seconds between decisions
PAPER_USER      = "aria-agent-system"
MIN_HOLD_CYCLES = 240    # hold for 4 hours minimum
TRADE_AMOUNT    = 100.0  # $100 per trade

# ── HARD RISK RULES ───────────────────────────────────────
MAX_DRAWDOWN    = 0.15   # 15% total drawdown = stop all
MIN_CONFIDENCE  = 0.55   # minimum confidence to trade
MAX_OPEN_TRADES = 3      # max 3 open positions at once

# ── POSITION TRACKING ─────────────────────────────────────
open_positions = {}  # {symbol: {'direction': 'LONG'/'SHORT', 'cycle': N}}

# ── AGENT DEFINITIONS ─────────────────────────────────────
AGENTS = [
    {'id': 'agent_btc',       'type': 'SPECIALIST', 'symbol': 'BTC',  'role': 'BTC trader'},
    {'id': 'agent_eth',       'type': 'SPECIALIST', 'symbol': 'ETH',  'role': 'ETH trader'},
    {'id': 'agent_tech',      'type': 'SPECIALIST', 'symbol': 'NVDA', 'role': 'Tech trader'},
    {'id': 'agent_gold',      'type': 'SPECIALIST', 'symbol': 'GLD',  'role': 'Gold trader'},
    {'id': 'agent_aapl',      'type': 'SPECIALIST', 'symbol': 'AAPL', 'role': 'AAPL trader'},
    {'id': 'agent_tsla',      'type': 'SPECIALIST', 'symbol': 'TSLA', 'role': 'TSLA trader'},
    {'id': 'agent_macro',     'type': 'MACRO',      'symbol': None,   'role': 'Macro analyst'},
    {'id': 'agent_sentiment', 'type': 'SENTIMENT',  'symbol': None,   'role': 'Sentiment analyst'},
    {'id': 'agent_regime',    'type': 'REGIME',     'symbol': None,   'role': 'Regime detector'},
    {'id': 'agent_risk',      'type': 'RISK',       'symbol': None,   'role': 'Risk manager'},
]

# ── FETCH ARIA STATE ───────────────────────────────────────
def fetch_state():
    try:
        r = requests.get(f"{ARIA_URL}/agent/state", timeout=10)
        return r.json()
    except Exception as e:
        print(f"  State fetch error: {e}")
        return None

# ── REPORT TO ARIA ─────────────────────────────────────────
def report_to_aria(agent_id, agent_type, symbol, action, confidence, reasoning):
    try:
        requests.post(f"{ARIA_URL}/agent/report", json={
            'agent_id':   agent_id,
            'agent_type': agent_type,
            'symbol':     symbol,
            'action':     action,
            'confidence': confidence,
            'reasoning':  reasoning,
            'pnl_today':  0.0
        }, timeout=5)
    except:
        pass

# ── MACRO AGENT ────────────────────────────────────────────
def macro_agent(state):
    macro       = state.get('macro', {})
    crisis      = macro.get('crisis_score', 0)
    vix         = macro.get('vix', 20)
    yield_curve = macro.get('yield_curve', 'NORMAL')

    if crisis >= 75 or vix > 40:
        signal    = 'CRISIS'
        reasoning = f"CRISIS: score={crisis} vix={vix}"
    elif crisis >= 50 or vix > 30:
        signal    = 'RISK_OFF'
        reasoning = f"Risk off: score={crisis} vix={vix}"
    elif yield_curve == 'INVERTED' and vix > 25:
        signal    = 'RISK_OFF'
        reasoning = f"Yield curve inverted + VIX {vix}"
    elif crisis < 25 and vix < 18:
        signal    = 'RISK_ON'
        reasoning = f"Risk on: score={crisis} vix={vix}"
    else:
        signal    = 'NEUTRAL'
        reasoning = f"Neutral macro: score={crisis} vix={vix}"

    report_to_aria('agent_macro', 'MACRO', None, signal, 0.75, reasoning)
    return signal

# ── SENTIMENT AGENT ────────────────────────────────────────
def sentiment_agent(state):
    fg   = state.get('fear_greed', 50)
    news = state.get('news', [])
    war_count = sum(1 for n in news if n.get('tag') == 'war')

    if fg < 20:
        signal    = 'EXTREME_FEAR'
        reasoning = f"F&G={fg} extreme fear"
    elif fg < 40:
        signal    = 'FEAR'
        reasoning = f"F&G={fg} fear"
    elif fg > 80:
        signal    = 'EXTREME_GREED'
        reasoning = f"F&G={fg} extreme greed"
    elif fg > 60:
        signal    = 'GREED'
        reasoning = f"F&G={fg} greed"
    else:
        signal    = 'NEUTRAL'
        reasoning = f"F&G={fg} neutral"

    report_to_aria('agent_sentiment', 'SENTIMENT', None, signal, 0.65, reasoning)
    return signal, fg

# ── REGIME AGENT ───────────────────────────────────────────
def regime_agent(state):
    assets     = state.get('assets', {})
    regimes    = [v.get('regime', 'SIDEWAYS') for v in assets.values()]
    bear_count = regimes.count('BEAR') + regimes.count('CRISIS')
    bull_count = regimes.count('BULL') + regimes.count('EUPHORIA')

    if bear_count >= 4:
        regime = 'BEAR'
    elif bull_count >= 4:
        regime = 'BULL'
    else:
        regime = 'SIDEWAYS'

    reasoning = f"Regime={regime} bear={bear_count} bull={bull_count}"
    report_to_aria('agent_regime', 'REGIME', None, regime, 0.75, reasoning)
    return regime

# ── SPECIALIST AGENT ───────────────────────────────────────
def specialist_agent(agent, state, macro_signal, sentiment_signal, fg, regime, cycle):
    symbol = agent['symbol']
    assets = state.get('assets', {})

    if symbol not in assets:
        return 'HOLD', 0.5, None

    asset      = assets[symbol]
    xgb_signal = asset.get('signal', 'HOLD')
    confidence = asset.get('confidence', 0.5)
    rsi        = asset.get('rsi', 50)
    regime_now = asset.get('regime', 'SIDEWAYS')

    # Check minimum hold time
    if symbol in open_positions:
        pos         = open_positions[symbol]
        cycles_held = cycle - pos['cycle']
        if cycles_held < MIN_HOLD_CYCLES:
            action    = 'HOLD'
            reasoning = f"Holding {pos['direction']} {symbol} - {cycles_held}/{MIN_HOLD_CYCLES} cycles"
            report_to_aria(agent['id'], agent['type'], symbol, action, confidence, reasoning)
            return action, confidence, None

    # Crisis override
    if macro_signal == 'CRISIS':
        if symbol == 'GLD':
            action    = 'BUY'
            direction = 'LONG'
            reasoning = f"CRISIS - buying safe haven GLD"
        elif symbol in open_positions:
            action    = 'CLOSE'
            direction = None
            reasoning = f"CRISIS - closing {symbol}"
        else:
            action    = 'HOLD'
            direction = None
            reasoning = f"CRISIS - staying out of {symbol}"
        report_to_aria(agent['id'], agent['type'], symbol, action, confidence, reasoning)
        return action, confidence, direction

    # Determine direction from XGBoost signal
    if xgb_signal == 'TAKE_PROFIT':
        direction = 'LONG'
    else:
        direction = 'SHORT'

    # RSI confirmation
    if rsi < 30:
        direction = 'LONG'    # oversold → buy
    elif rsi > 70:
        direction = 'SHORT'   # overbought → sell

    # Macro adjustments
    if macro_signal == 'RISK_OFF' and symbol in ['BTC', 'ETH', 'NVDA', 'TSLA']:
        direction = 'SHORT'
    if sentiment_signal == 'EXTREME_FEAR' and symbol == 'GLD':
        direction = 'LONG'

    # Confidence check
    if confidence < MIN_CONFIDENCE:
        action    = 'HOLD'
        reasoning = f"{symbol} confidence {confidence:.2f} below {MIN_CONFIDENCE}"
        report_to_aria(agent['id'], agent['type'], symbol, action, confidence, reasoning)
        return action, confidence, None

    # Position management
    if symbol in open_positions:
        current_dir = open_positions[symbol]['direction']
        if current_dir != direction:
            action    = 'REVERSE'
            reasoning = f"{symbol} reversing {current_dir}→{direction} conf={confidence:.2f}"
        else:
            action    = 'HOLD'
            reasoning = f"{symbol} holding {current_dir}"
    else:
        action    = 'BUY' if direction == 'LONG' else 'SELL'
        reasoning = f"{symbol} opening {direction} conf={confidence:.2f} RSI={rsi:.1f} regime={regime_now}"

    report_to_aria(agent['id'], agent['type'], symbol, action, confidence, reasoning)
    return action, confidence, direction

# ── RISK MANAGER ───────────────────────────────────────────
def risk_manager(decisions, state, balance):
    macro  = state.get('macro', {})
    crisis = macro.get('crisis_score', 0)

    drawdown = (10000 - balance) / 10000
    if drawdown > MAX_DRAWDOWN:
        print(f"  KILL SWITCH: Drawdown {drawdown*100:.1f}%")
        report_to_aria('agent_risk', 'RISK', None, 'KILL_SWITCH', 1.0,
                       f"Drawdown {drawdown*100:.1f}% - halted")
        return []

    current_open = len(open_positions)
    approved     = []

    for agent_id, symbol, action, confidence, direction in decisions:
        if crisis >= 75 and symbol not in ['GLD']:
            report_to_aria('agent_risk', 'RISK', symbol, 'VETO', 1.0,
                          f"Crisis {crisis} - safe havens only")
            continue

        if action in ['BUY', 'SELL'] and current_open >= MAX_OPEN_TRADES:
            report_to_aria('agent_risk', 'RISK', symbol, 'VETO', 1.0,
                          f"Max {MAX_OPEN_TRADES} open positions")
            continue

        if action != 'HOLD':
            approved.append((agent_id, symbol, action, confidence, direction))
            report_to_aria('agent_risk', 'RISK', symbol, 'APPROVED', 1.0,
                          f"Approved {action} {direction or ''} on {symbol}")

    return approved

# ── GET PORTFOLIO BALANCE ──────────────────────────────────
def get_portfolio_balance():
    try:
        r    = requests.get(f"{ARIA_URL}/paper/portfolio/{PAPER_USER}", timeout=10)
        data = r.json()
        return data.get('balance', 10000)
    except:
        return 10000

# ── CLOSE POSITION ─────────────────────────────────────────
def close_position(symbol):
    try:
        r         = requests.get(f"{ARIA_URL}/paper/portfolio/{PAPER_USER}", timeout=10)
        portfolio = r.json()
        trades    = portfolio.get('open_trades', [])
        for trade in trades:
            if trade['symbol'] == symbol:
                r2     = requests.post(f"{ARIA_URL}/paper/close", json={
                    'user_id':  PAPER_USER,
                    'trade_id': trade['trade_id']
                }, timeout=10)
                result = r2.json()
                if result.get('success'):
                    pnl = result.get('pnl_usd', 0)
                    print(f"  CLOSED: {symbol} PnL=${pnl:.2f}")
                    if symbol in open_positions:
                        del open_positions[symbol]
                    return True
    except Exception as e:
        print(f"  Close error: {e}")
    return False

# ── EXECUTE TRADE ──────────────────────────────────────────
def execute_trade(symbol, action, direction, cycle):
    try:
        if action == 'REVERSE':
            close_position(symbol)

        r = requests.post(f"{ARIA_URL}/paper/trade", json={
            'user_id':    PAPER_USER,
            'symbol':     symbol,
            'direction':  direction,
            'amount_usd': TRADE_AMOUNT
        }, timeout=10)
        result = r.json()
        if result.get('success'):
            open_positions[symbol] = {'direction': direction, 'cycle': cycle}
            price = result['trade']['entry_price']
            print(f"  EXECUTED: {direction} {symbol} @ ${price}")
            return True
        else:
            print(f"  FAILED: {result.get('detail', 'unknown')}")
            return False
    except Exception as e:
        print(f"  Execution error: {e}")
        return False

# ── MAIN LOOP ──────────────────────────────────────────────
def main():
    print("="*60)
    print("ARIA AUTONOMOUS AGENT SYSTEM v3")
    print(f"Agents:         {len(AGENTS)}")
    print(f"Interval:       {LOOP_INTERVAL}s")
    print(f"Min confidence: {MIN_CONFIDENCE}")
    print(f"Min hold:       {MIN_HOLD_CYCLES} cycles ({MIN_HOLD_CYCLES//60}h)")
    print(f"Max positions:  {MAX_OPEN_TRADES}")
    print(f"Trade size:     ${TRADE_AMOUNT}")
    print("="*60)

    cycle = 0
    while True:
        cycle += 1
        now = datetime.now().strftime('%H:%M:%S')
        print(f"\n[{now}] Cycle {cycle} | Open positions: {list(open_positions.keys())}")

        state = fetch_state()
        if not state:
            print("  No state - skipping")
            time.sleep(LOOP_INTERVAL)
            continue

        balance                  = get_portfolio_balance()
        macro_signal             = macro_agent(state)
        sentiment_signal, fg     = sentiment_agent(state)
        regime                   = regime_agent(state)
        print(f"  Macro:{macro_signal} Sentiment:{sentiment_signal} F&G:{fg} Regime:{regime} Balance:${balance:.0f}")

        decisions = []
        for agent in AGENTS:
            if agent['type'] == 'SPECIALIST':
                action, confidence, direction = specialist_agent(
                    agent, state, macro_signal, sentiment_signal, fg, regime, cycle
                )
                decisions.append((agent['id'], agent['symbol'], action, confidence, direction))
                print(f"  {agent['id']}: {action} {direction or ''} ({confidence:.2f})")

        approved = risk_manager(decisions, state, balance)
        print(f"  Approved: {len(approved)}")

        for agent_id, symbol, action, confidence, direction in approved:
            if action in ['BUY', 'SELL', 'REVERSE'] and direction:
                execute_trade(symbol, action, direction, cycle)
            elif action == 'CLOSE':
                close_position(symbol)

        time.sleep(LOOP_INTERVAL)

if __name__ == "__main__":
    main()
