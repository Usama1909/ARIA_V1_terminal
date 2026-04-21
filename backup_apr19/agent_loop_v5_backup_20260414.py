#!/usr/bin/env python3
"""
ARIA SWARM INTELLIGENCE v5
===========================
Clean DB-only architecture — zero HTTP in hot loop.
Problems A+B+C fully integrated.
PATCH: Fixed trade close pipeline — writes to closed_trades on SL/TP.
"""
import time, json, logging, numpy as np
from datetime import datetime, timedelta
import psycopg2, psycopg2.extras

logging.basicConfig(level=logging.INFO, format='%(asctime)s [ARIAv5] %(message)s')
log = logging.getLogger()

LOOP_INTERVAL   = 60
MAX_OPEN_TRADES = 6
MIN_CONFIDENCE  = 0.52
STALE_SENTIMENT = 600
STALE_MARKET    = 120

REGIME_MULT = {'NORMAL': 1.0, 'CRISIS': 0.3, 'FOMC_DAY': 0.5}
DB_CONFIG = {'host':'localhost','port':5432,'dbname':'aria_db',
             'user':'postgres','password':'aria_secure_2026'}
SYMBOLS = ['BTC','ETH','AAPL','NVDA','TSLA','GLD']

def get_db(): return psycopg2.connect(**DB_CONFIG)

def read_sentiment():
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("SELECT score,stance,velocity,regime,fear_greed,updated_at FROM sentiment_latest ORDER BY updated_at DESC LIMIT 1")
        row=cur.fetchone(); cur.close(); conn.close()
        if row:
            age=(datetime.utcnow()-row[5].replace(tzinfo=None)).total_seconds()
            return {'score':float(row[0]),'stance':str(row[1]),'velocity':float(row[2]),
                    'regime':str(row[3]),'fear_greed':int(row[4]),'age_seconds':age,'stale':age>STALE_SENTIMENT}
    except Exception as e:
        log.warning(f"Sentiment read failed: {e}")
    return {'score':0.0,'stance':'NEUTRAL','velocity':0.0,'regime':'NORMAL','fear_greed':50,'age_seconds':9999,'stale':True}

def read_market():
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("SELECT symbol,price,change_24h,updated_at FROM market_state_latest")
        rows=cur.fetchall(); cur.close(); conn.close()
        market={}
        for row in rows:
            age=(datetime.utcnow()-row[3].replace(tzinfo=None)).total_seconds()
            market[row[0]]={'price':float(row[1]),'change_24h':float(row[2]),'age_seconds':age,'stale':age>STALE_MARKET}
        return market
    except Exception as e:
        log.warning(f"Market read failed: {e}")
    return {}

def read_risk(symbol):
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("SELECT var_99,expected_shortfall,shape_param FROM evt_tail_risk WHERE symbol=%s ORDER BY created_at DESC LIMIT 1",[symbol])
        row=cur.fetchone(); cur.close(); conn.close()
        if row:
            return {'var_95':float(row[0])*0.7,'var_99':float(row[0]),'es_975':float(row[1]),'xi':float(row[2]),'source':'problem_c'}
    except: pass
    fallback={'BTC':{'var_95':0.082,'es_975':0.189},'ETH':{'var_95':0.091,'es_975':0.214},
              'AAPL':{'var_95':0.022,'es_975':0.052},'NVDA':{'var_95':0.035,'es_975':0.081},
              'TSLA':{'var_95':0.048,'es_975':0.110},'GLD':{'var_95':0.018,'es_975':0.044}}
    r=fallback.get(symbol,{'var_95':0.05,'es_975':0.08})
    return {**r,'source':'fallback'}

def read_world_state():
    """Read current world state narrative from DB."""
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("SELECT value FROM aria_config WHERE key='world_state' LIMIT 1")
        row=cur.fetchone(); cur.close(); conn.close()
        if row:
            return json.loads(row[0]).get('narrative','UNKNOWN')
    except: pass
    return 'UNKNOWN'

def get_portfolio_value():
    """Dynamically compute portfolio value from DB instead of hardcoded constant."""
    try:
        conn=get_db(); cur=conn.cursor()
        base = 10000.0
        cur.execute("SELECT COALESCE(SUM(pnl_usd),0) FROM closed_trades")
        realized = float(cur.fetchone()[0])
        cur.close(); conn.close()
        return max(100.0, base + realized)
    except:
        return 10000.0

def close_position(symbol, pos, exit_price, exit_reason, sentiment, cycle):
    """
    Properly close a position:
    1. Write to closed_trades with full context
    2. Write to pattern_library (with required fingerprint jsonb)
    3. Mark orders_outbox as CLOSED
    4. Log to signal_log
    """
    try:
        entry_price = pos.get('entry_price', 0)
        direction   = pos.get('direction', 'LONG')
        size_usd    = pos.get('size_usd', 0)
        entry_time  = pos.get('entry_time', datetime.utcnow())
        hold_cycles = pos.get('hold_cycles', 0)

        if direction == 'LONG':
            pnl_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0
        else:
            pnl_pct = (entry_price - exit_price) / entry_price if entry_price > 0 else 0

        pnl_usd     = size_usd * pnl_pct
        outcome     = 'WIN' if pnl_usd > 0 else 'LOSS'
        hold_hours  = round(hold_cycles * (LOOP_INTERVAL / 3600), 2)
        world_state = read_world_state()
        regime      = sentiment.get('regime', 'UNKNOWN')

        conn = get_db(); cur = conn.cursor()

        # 1. Write to closed_trades
        cur.execute("""
            INSERT INTO closed_trades
                (symbol, direction, entry_price, exit_price, entry_time, exit_time,
                 pnl_usd, pnl_pct, size_usd, regime_at_entry, sentiment_at_entry,
                 fear_greed_at_entry, velocity_at_entry, outcome, hold_cycles, signal_id)
            VALUES (%s,%s,%s,%s,%s,NOW(),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, [
            symbol, direction, entry_price, exit_price, entry_time,
            round(pnl_usd, 2), round(pnl_pct, 6), size_usd,
            regime,
            sentiment.get('score', 0),
            sentiment.get('fear_greed', 50),
            sentiment.get('velocity', 0),
            outcome,
            hold_cycles,
            f"v5_{cycle}_{symbol}"
        ])

        # 2. Write to pattern_library — fingerprint is required jsonb NOT NULL
        fingerprint = json.dumps({
            'symbol':      symbol,
            'direction':   direction,
            'regime':      regime,
            'exit_reason': exit_reason,
            'world_state': world_state
        })
        cur.execute("""
            INSERT INTO pattern_library
                (fingerprint, symbol, action_taken, outcome, pnl, confidence,
                 regime, hold_hours, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        """, [
            fingerprint,
            symbol,
            'BUY' if direction == 'LONG' else 'SELL',
            outcome,
            round(pnl_usd, 2),
            pos.get('confidence', 0.5),
            regime,
            hold_hours
        ])

        # 3. Mark orders_outbox as CLOSED — preserve original executed_at
        cur.execute("""
            UPDATE orders_outbox
            SET status='CLOSED', executed_at=COALESCE(executed_at, NOW())
            WHERE symbol=%s AND status='EXECUTED'
        """, [symbol])

        # 4. Log to signal_log
        cur.execute("""
            INSERT INTO signal_log (signal_name, signal_value, symbol, triggered_action)
            VALUES (%s,%s,%s,%s)
        """, [
            exit_reason,
            round(pnl_pct * 100, 2),
            symbol,
            f"{outcome} pnl:{pnl_usd:+.2f} entry:{entry_price:.4f} exit:{exit_price:.4f} world:{world_state}"
        ])

        conn.commit(); cur.close(); conn.close()

        log.info(f"  CLOSED {symbol} | {exit_reason} | {outcome} | PnL: ${pnl_usd:+.2f} ({pnl_pct*100:+.1f}%) | held:{hold_hours:.1f}h | world:{world_state}")
        return True

    except Exception as e:
        log.error(f"close_position failed for {symbol}: {e}")
        import traceback; traceback.print_exc()
        return False

def kelly_size(symbol, confidence, sentiment, risk, portfolio_value):
    p=min(0.85,max(0.45,confidence))
    var=risk.get('var_95',0.05); es=risk.get('es_975',0.08)
    b=max(0.3,var/es) if es>0 else 1.0
    kelly=max(0.0,p-(1-p)/b)*0.5
    regime=sentiment.get('regime','NORMAL')
    fg=sentiment.get('fear_greed',50)
    velocity=sentiment.get('velocity',0.0)
    regime_mult=REGIME_MULT.get(regime,1.0)
    fg_mult=0.4 if fg<=20 else (0.8 if fg<=35 else (0.7 if fg>=75 else (0.9 if fg>=55 else 1.0)))
    vol_mult=max(0.3,min(1.0,0.05/max(var,0.01)))
    vel_mult=0.6 if velocity<-10 else (0.8 if velocity<-5 else 1.0)
    max_pct={'BTC':0.15,'ETH':0.12,'GLD':0.15,'NVDA':0.10,'AAPL':0.10,'TSLA':0.08}.get(symbol,0.10)
    adjusted=kelly*regime_mult*fg_mult*vol_mult*vel_mult
    final=min(adjusted,max_pct,0.50)
    size_usd=round(portfolio_value*final,2)
    reasoning=f"Kelly:{kelly*100:.1f}% adj:{final*100:.1f}% regime:{regime_mult}x fg:{fg_mult}x vol:{vol_mult:.2f}x VaR:{var*100:.1f}%"
    return max(100.0, size_usd), final, reasoning

def generate_signal(symbol, market_data, sentiment, risk):
    if symbol not in market_data:
        return 'HOLD', 0.5, None
    change    = market_data[symbol].get('change_24h', 0)
    sent_score= sentiment.get('score', 0)
    regime    = sentiment.get('regime', 'NORMAL')
    velocity  = sentiment.get('velocity', 0)
    fg        = sentiment.get('fear_greed', 50)
    var       = risk.get('var_95', 0.05)
    try:
        import pickle
        with open(f'/root/backup_20260401/quant_engine_v3_{symbol}.pkl','rb') as f:
            pickle.load(f)
        base_conf = 0.60
    except:
        base_conf = 0.52
    direction = None
    confidence = base_conf
    if regime == 'CRISIS':
        if symbol == 'GLD':
            direction = 'LONG'; confidence = min(0.82, base_conf + 0.20)
        elif symbol == 'BTC' and sent_score < -25 and change < -1:
            direction = 'SHORT'; confidence = min(0.75, base_conf + 0.12)
        elif symbol == 'ETH' and sent_score < -25 and change < -1:
            direction = 'SHORT'; confidence = min(0.73, base_conf + 0.10)
        elif symbol == 'NVDA' and change < -2 and sent_score < -20:
            direction = 'SHORT'; confidence = min(0.70, base_conf + 0.08)
        elif symbol == 'TSLA' and change < -2 and sent_score < -20:
            direction = 'SHORT'; confidence = min(0.68, base_conf + 0.06)
        elif symbol == 'AAPL' and change < -3 and sent_score < -30:
            direction = 'SHORT'; confidence = min(0.68, base_conf + 0.06)
    elif regime == 'NORMAL':
        if change > 2 and sent_score > 10 and velocity > 0:
            direction = 'LONG'; confidence = min(0.78, base_conf + 0.10)
        elif change < -2 and sent_score < -10 and velocity < 0:
            direction = 'SHORT'; confidence = min(0.78, base_conf + 0.10)
        if symbol == 'GLD' and fg < 30:
            direction = 'LONG'; confidence = min(0.80, base_conf + 0.15)
        elif symbol == 'BTC' and fg > 70 and change > 3:
            direction = 'LONG'; confidence = min(0.75, base_conf + 0.10)
        elif symbol == 'NVDA' and change > 3 and sent_score > 5:
            direction = 'LONG'; confidence = min(0.74, base_conf + 0.10)
    elif regime == 'FOMC_DAY':
        if symbol == 'GLD':
            direction = 'LONG'; confidence = min(0.72, base_conf + 0.10)
        elif symbol in ['BTC','ETH'] and sent_score < -20:
            direction = 'SHORT'; confidence = min(0.65, base_conf + 0.05)
    if var > 0.08: confidence *= 0.85
    if abs(velocity) > 10: confidence = min(0.85, confidence + 0.05)
    if symbol == 'GLD' and fg < 20: confidence = min(0.88, confidence + 0.05)
    if direction is None:
        return 'HOLD', confidence, None
    return ('BUY' if direction == 'LONG' else 'SELL'), confidence, direction

def write_order(symbol,action,direction,size_usd,confidence,kelly_fraction,reasoning,cycle):
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("INSERT INTO orders_outbox (symbol,side,size_usd,direction,confidence,kelly_fraction,reasoning,status,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,'PENDING',NOW())",
            [symbol,action,size_usd,direction,confidence,kelly_fraction,reasoning])
        cur.execute("INSERT INTO agent_decisions (agent_id,symbol,action,confidence,reasoning) VALUES (%s,%s,%s,%s,%s)",
            [f'aria_v5_{cycle}',symbol,action,confidence,reasoning[:200]])
        conn.commit(); cur.close(); conn.close()
        return True
    except Exception as e:
        log.error(f"Write order failed: {e}")
        return False

def log_cycle(cycle,sentiment):
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("INSERT INTO signal_log (signal_name,signal_value,symbol,triggered_action) VALUES (%s,%s,%s,%s)",
            ['v5_cycle',float(cycle),'ALL',f"sent:{sentiment['score']:.1f}"])
        conn.commit(); cur.close(); conn.close()
    except: pass

def main():
    log.info("="*60)
    log.info("ARIA SWARM INTELLIGENCE v5 — DB-only, A+B+C integrated")
    log.info("PATCH: Trade close pipeline fixed — writes to closed_trades")
    log.info("="*60)
    cycle=0

    # Restore open positions — only EXECUTED (not CLOSED)
    open_positions={}
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("""
            SELECT symbol, side, direction, size_usd, confidence, entry_price, created_at
            FROM orders_outbox
            WHERE status='EXECUTED'
            ORDER BY created_at DESC
        """)
        rows=cur.fetchall(); cur.close(); conn.close()
        for row in rows:
            if row[0] not in open_positions:
                open_positions[row[0]]={
                    'side':        row[1],
                    'direction':   row[2],
                    'size_usd':    float(row[3]),
                    'confidence':  float(row[4]),
                    'entry_price': float(row[5]) if row[5] else 0.0,
                    'entry_time':  row[6],
                    'hold_cycles': 0
                }
        log.info(f"Restored {len(open_positions)} open positions: {list(open_positions.keys())}")
    except Exception as e:
        log.warning(f"Could not restore positions: {e}")

    while True:
        cycle+=1
        try:
            sentiment      = read_sentiment()
            market         = read_market()
            portfolio_value = get_portfolio_value()

            # ── Exit logic: stop loss + take profit ──────────
            for symbol in list(open_positions.keys()):
                if symbol not in market: continue
                pos     = open_positions[symbol]
                entry   = pos.get('entry_price', 0)
                current = market[symbol].get('price', 0)
                if entry <= 0 or current <= 0: continue

                direction = pos.get('direction', 'LONG')
                if direction == 'LONG':
                    pnl_pct = (current - entry) / entry
                else:
                    pnl_pct = (entry - current) / entry

                # Increment hold cycles every loop
                open_positions[symbol]['hold_cycles'] = pos.get('hold_cycles', 0) + 1

                # Stop loss: -5%
                if pnl_pct <= -0.05:
                    log.info(f"STOP LOSS triggered: {symbol} pnl:{pnl_pct*100:.1f}%")
                    if close_position(symbol, open_positions[symbol], current, 'STOP_LOSS', sentiment, cycle):
                        del open_positions[symbol]

                # Take profit: +8%
                elif pnl_pct >= 0.08:
                    log.info(f"TAKE PROFIT triggered: {symbol} pnl:{pnl_pct*100:.1f}%")
                    if close_position(symbol, open_positions[symbol], current, 'TAKE_PROFIT', sentiment, cycle):
                        del open_positions[symbol]

            safe_mode = sentiment['stale'] or not market
            regime    = sentiment.get('regime','NORMAL')
            score     = sentiment.get('score',0)
            vel       = sentiment.get('velocity',0)
            fg        = sentiment.get('fear_greed',50)
            stance    = sentiment.get('stance','NEUTRAL')
            log.info(f"[Cycle {cycle}] Regime:{regime} Sent:{score:+.1f}({stance}) Vel:{vel:+.1f} F&G:{fg} Portfolio:${portfolio_value:.0f} Safe:{'ON' if safe_mode else 'OFF'} Open:{list(open_positions.keys())}")

            if safe_mode:
                log.info("Safe mode — no new trades this cycle")
                time.sleep(LOOP_INTERVAL); continue

            decisions=[]
            for symbol in SYMBOLS:
                if len(open_positions) >= MAX_OPEN_TRADES: break
                if symbol in open_positions: continue
                risk = read_risk(symbol)
                action, confidence, direction = generate_signal(symbol, market, sentiment, risk)
                if action == 'HOLD' or confidence < MIN_CONFIDENCE:
                    continue
                size_usd, kelly_frac, kelly_reasoning = kelly_size(symbol, confidence, sentiment, risk, portfolio_value)
                if size_usd < 50: continue
                decisions.append({
                    'symbol': symbol, 'action': action, 'direction': direction,
                    'size_usd': size_usd, 'confidence': confidence,
                    'kelly_fraction': kelly_frac, 'reasoning': kelly_reasoning
                })
                log.info(f"  {symbol}: {action} {direction} conf:{confidence:.2f} size:${size_usd:.0f} kelly:{kelly_frac*100:.1f}%")

            for d in decisions:
                success = write_order(d['symbol'], d['action'], d['direction'], d['size_usd'],
                                      d['confidence'], d['kelly_fraction'], d['reasoning'], cycle)
                if success:
                    d['entry_time']  = datetime.utcnow()
                    d['hold_cycles'] = 0
                    open_positions[d['symbol']] = d
                    log.info(f"  ORDER: {d['action']} {d['symbol']} ${d['size_usd']:.0f}")

            log_cycle(cycle, sentiment)
            log.info(f"  Decisions:{len(decisions)} | Open:{len(open_positions)} | Portfolio:${portfolio_value:.0f}")

        except Exception as e:
            log.error(f"Cycle {cycle} error: {e}")
            import traceback; traceback.print_exc()
            time.sleep(10)
        time.sleep(LOOP_INTERVAL)

if __name__=='__main__':
    main()
