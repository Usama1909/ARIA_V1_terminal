#!/usr/bin/env python3
"""
ARIA SWARM INTELLIGENCE v5
===========================
Clean DB-only architecture — zero HTTP in hot loop.
Problems A+B+C fully integrated.
PATCH 1: Fixed trade close pipeline — writes to closed_trades on SL/TP.
PATCH 2: world_state wired into signal generation and risk sizing.
PATCH 3: XGBoost+RF ensemble wired into generate_signal via aria_model_inference.
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
STALE_WORLD     = 1800

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

def read_world_state():
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("""SELECT narrative, macro_phase, risk_appetite, liquidity_state,
                              dominant_driver, confidence, updated_at
                       FROM world_state ORDER BY updated_at DESC LIMIT 1""")
        row=cur.fetchone(); cur.close(); conn.close()
        if row:
            age=(datetime.utcnow()-row[6].replace(tzinfo=None)).total_seconds()
            return {
                'narrative':       str(row[0]),
                'macro_phase':     str(row[1]),
                'risk_appetite':   str(row[2]),
                'liquidity_state': str(row[3]),
                'dominant_driver': str(row[4]),
                'confidence':      float(row[5]),
                'age_seconds':     age,
                'stale':           age > STALE_WORLD
            }
    except Exception as e:
        log.warning(f"World state read failed: {e}")
    return {'narrative':'UNKNOWN','macro_phase':'UNKNOWN','risk_appetite':'MODERATE',
            'liquidity_state':'NORMAL','dominant_driver':'UNKNOWN',
            'confidence':0.5,'age_seconds':9999,'stale':True}

def read_system_mode():
    """Read system mode written by anomaly detector."""
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("SELECT value FROM aria_config WHERE key='system_mode' LIMIT 1")
        row=cur.fetchone(); cur.close(); conn.close()
        if row:
            d=json.loads(row[0])
            return d.get('mode','NORMAL'), d.get('score',100)
    except: pass
    return 'NORMAL', 100

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

def get_portfolio_value():
    try:
        conn=get_db(); cur=conn.cursor()
        base = 10000.0
        cur.execute("SELECT COALESCE(SUM(pnl_usd),0) FROM closed_trades")
        realized = float(cur.fetchone()[0])
        cur.close(); conn.close()
        return max(100.0, base + realized)
    except:
        return 10000.0

def world_state_multiplier(world):
    if world.get('stale'): return 1.0
    mult = 1.0
    risk_appetite = world.get('risk_appetite','MODERATE')
    liquidity     = world.get('liquidity_state','NORMAL')
    narrative     = world.get('narrative','UNKNOWN')
    if risk_appetite == 'CRISIS':       mult *= 0.4
    elif risk_appetite == 'LOW':        mult *= 0.7
    if liquidity == 'FROZEN':           mult *= 0.3
    elif liquidity == 'FRAGILE':        mult *= 0.6
    if narrative == 'LIQUIDITY_CRUNCH': mult *= 0.5
    return round(max(0.1, mult), 3)

def close_position(symbol, pos, exit_price, exit_reason, sentiment, world, cycle):
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
        pnl_usd    = size_usd * pnl_pct
        outcome    = 'WIN' if pnl_usd > 0 else 'LOSS'
        hold_hours = round(hold_cycles * (LOOP_INTERVAL / 3600), 2)
        regime     = sentiment.get('regime', 'UNKNOWN')
        narrative  = world.get('narrative', 'UNKNOWN')
        conn = get_db(); cur = conn.cursor()
        cur.execute("""INSERT INTO closed_trades
                (symbol, direction, entry_price, exit_price, entry_time, exit_time,
                 pnl_usd, pnl_pct, size_usd, regime_at_entry, sentiment_at_entry,
                 fear_greed_at_entry, velocity_at_entry, outcome, hold_cycles, signal_id)
            VALUES (%s,%s,%s,%s,%s,NOW(),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [symbol, direction, entry_price, exit_price, entry_time,
             round(pnl_usd,2), round(pnl_pct,6), size_usd, regime,
             sentiment.get('score',0), sentiment.get('fear_greed',50),
             sentiment.get('velocity',0), outcome, hold_cycles, f"v5_{cycle}_{symbol}"])
        fingerprint = json.dumps({
            'symbol': symbol, 'direction': direction, 'regime': regime,
            'exit_reason': exit_reason, 'world_narrative': narrative,
            'liquidity': world.get('liquidity_state','UNKNOWN'),
            'macro_phase': world.get('macro_phase','UNKNOWN')
        })
        cur.execute("""INSERT INTO pattern_library
                (fingerprint, symbol, action_taken, outcome, pnl, confidence, regime, hold_hours, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
            [fingerprint, symbol, 'BUY' if direction=='LONG' else 'SELL',
             outcome, round(pnl_usd,2), pos.get('confidence',0.5), regime, hold_hours])
        cur.execute("""UPDATE orders_outbox SET status='CLOSED', executed_at=COALESCE(executed_at,NOW())
            WHERE symbol=%s AND status='EXECUTED'""", [symbol])
        cur.execute("""INSERT INTO signal_log (signal_name,signal_value,symbol,triggered_action)
            VALUES (%s,%s,%s,%s)""",
            [exit_reason, round(pnl_pct*100,2), symbol,
             f"{outcome} pnl:{pnl_usd:+.2f} entry:{entry_price:.4f} exit:{exit_price:.4f} world:{narrative}"])
        cur.execute("UPDATE positions_live SET status='CLOSED', updated_at=NOW() WHERE symbol=%s", [symbol])
        # Write to episodic memory with full context
        try:
            from aria_nlp_service import get_nlp_sentiment
            nlp = get_nlp_sentiment(symbol) if hasattr(__builtins__, '__import__') else {'label':'NEUTRAL','fomc':'NEUTRAL'}
        except:
            nlp = {'label':'NEUTRAL','fomc':'NEUTRAL'}
        fg_bucket = 'EXTREME_FEAR' if sentiment.get('fear_greed',50)<25 else 'FEAR' if sentiment.get('fear_greed',50)<45 else 'NEUTRAL' if sentiment.get('fear_greed',50)<55 else 'GREED' if sentiment.get('fear_greed',50)<75 else 'EXTREME_GREED'
        cur.execute("""INSERT INTO episodic_memory (symbol, direction, regime, fear_greed_bucket, nlp_label, fomc_signal, outcome, pnl_pct)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            [symbol, direction, regime, fg_bucket, nlp.get('label','NEUTRAL'), nlp.get('fomc','NEUTRAL'), outcome, round(pnl_pct,6)])
        conn.commit(); cur.close(); conn.close()
        log.info(f"  CLOSED {symbol} | {exit_reason} | {outcome} | PnL: ${pnl_usd:+.2f} ({pnl_pct*100:+.1f}%) | held:{hold_hours:.1f}h | world:{narrative}")
        return True
    except Exception as e:
        log.error(f"close_position failed for {symbol}: {e}")
        import traceback; traceback.print_exc()
        return False

def kelly_size(symbol, confidence, sentiment, risk, world, portfolio_value):
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
    world_mult=world_state_multiplier(world)
    # OOD check — reduce size if conditions are unusual
    ood_mult = 1.0
    try:
        from aria_ood_detector import detect_ood
        from aria_model_inference import build_feature_vector
        features = build_feature_vector(symbol)
        ood = detect_ood(symbol, features)
        ood_mult = ood['size_multiplier']
        if ood_mult < 1.0:
            log.info(f"  {symbol} OOD: {ood['reason']} size_mult:{ood_mult}")
    except Exception as e:
        pass
    max_pct={'BTC':0.15,'ETH':0.12,'GLD':0.15,'NVDA':0.10,'AAPL':0.10,'TSLA':0.08}.get(symbol,0.10)
    adjusted=kelly*regime_mult*fg_mult*vol_mult*vel_mult*world_mult*ood_mult
    final=min(adjusted,max_pct,0.50)
    size_usd=round(portfolio_value*final,2)
    reasoning=f"Kelly:{kelly*100:.1f}% adj:{final*100:.1f}% regime:{regime_mult}x fg:{fg_mult}x vol:{vol_mult:.2f}x world:{world_mult}x VaR:{var*100:.1f}%"
    return max(100.0, size_usd), final, reasoning


def get_episodic_modifier(symbol, direction, regime, fear_greed):
    """Query episodic memory for historical win rate in similar conditions."""
    try:
        from aria_episodic_memory import recall
        result = recall(symbol, direction, regime, fear_greed)
        if result['sample_size'] >= 3:
            log.info(f"  {symbol} EPISODIC: wr:{result['win_rate']:.0%} n:{result['sample_size']} modifier:{result['confidence_modifier']:+.2f}")
        return result['confidence_modifier']
    except Exception as e:
        log.warning(f"Episodic memory failed: {e}")
        return 0.0

def get_nlp_sentiment(symbol):
    """Read latest NLP sentiment score from DB for this symbol."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT score, label, fomc_signal 
            FROM nlp_sentiment 
            WHERE symbol=%s 
            ORDER BY timestamp DESC LIMIT 1
        """, (symbol,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            return {'score': float(row[0]), 'label': row[1], 'fomc': row[2]}
    except Exception as e:
        pass
    return {'score': 0.0, 'label': 'NEUTRAL', 'fomc': 'NEUTRAL'}

def generate_signal(symbol, market_data, sentiment, risk, world):
    """
    Signal generation with XGBoost+RF ensemble + rules fusion.
    Logic:
      - Model LONG + rules LONG  → strong LONG, boost confidence
      - Model SHORT + rules SHORT → strong SHORT, boost confidence
      - Model only (rules neutral) → use model at model confidence
      - Rules only (model unavailable) → use rules at base confidence
      - Model vs rules disagree → skip (return HOLD)
    """
    if symbol not in market_data:
        return 'HOLD', 0.5, None

    change     = market_data[symbol].get('change_24h', 0)
    sent_score = sentiment.get('score', 0)
    regime     = sentiment.get('regime', 'NORMAL')
    velocity   = sentiment.get('velocity', 0)
    fg         = sentiment.get('fear_greed', 50)
    var        = risk.get('var_95', 0.05)
    narrative  = world.get('narrative', 'UNKNOWN')
    risk_app   = world.get('risk_appetite', 'MODERATE')
    liquidity  = world.get('liquidity_state', 'NORMAL')
    macro      = world.get('macro_phase', 'UNKNOWN')

    # Hard gate: frozen liquidity = no new trades except GLD
    if liquidity == 'FROZEN' and symbol != 'GLD':
        return 'HOLD', 0.5, None

    # ── Step 1: Get model signal ──────────────────────────
    try:
        from aria_model_inference import get_model_signal
        model_dir, model_conf, model_reason = get_model_signal(symbol)
    except Exception as e:
        log.warning(f"Model inference import failed: {e}")
        model_dir, model_conf, model_reason = None, 0.52, "import_error"

    # ── Step 2: Get rules signal ──────────────────────────
    rules_dir  = None
    rules_conf = 0.52

    # World state adjustments to base confidence
    base_conf = 0.60 if model_dir is not None else 0.52
    if narrative == 'SAFE_HAVEN_DEMAND' and symbol == 'GLD':
        base_conf = min(0.90, base_conf + 0.15)
    elif narrative == 'AI_OPTIMISM' and symbol == 'NVDA':
        base_conf = min(0.85, base_conf + 0.10)
    elif narrative == 'INFLATION_FEAR' and symbol == 'GLD':
        base_conf = min(0.88, base_conf + 0.12)
    elif narrative == 'CRYPTO_FEAR' and symbol in ['BTC','ETH']:
        base_conf = max(0.40, base_conf - 0.10)
    elif narrative == 'LIQUIDITY_CRUNCH':
        base_conf = max(0.40, base_conf - 0.15)
    elif risk_app == 'CRISIS' and symbol != 'GLD':
        base_conf = max(0.40, base_conf - 0.08)
    if macro == 'LATE_CYCLE_STRESS' and symbol in ['NVDA','TSLA','ETH','BTC']:
        base_conf = max(0.40, base_conf - 0.07)

    if regime == 'CRISIS':
        if symbol == 'GLD':
            rules_dir = 'LONG';  rules_conf = min(0.82, base_conf + 0.20)
        elif symbol == 'BTC' and sent_score < -25 and change < -1:
            rules_dir = 'SHORT'; rules_conf = min(0.75, base_conf + 0.12)
        elif symbol == 'ETH' and sent_score < -25 and change < -1:
            rules_dir = 'SHORT'; rules_conf = min(0.73, base_conf + 0.10)
        elif symbol == 'NVDA' and change < -2 and sent_score < -20:
            rules_dir = 'SHORT'; rules_conf = min(0.70, base_conf + 0.08)
        elif symbol == 'TSLA' and change < -2 and sent_score < -20:
            rules_dir = 'SHORT'; rules_conf = min(0.68, base_conf + 0.06)
        elif symbol == 'AAPL' and change < -3 and sent_score < -30:
            rules_dir = 'SHORT'; rules_conf = min(0.68, base_conf + 0.06)
    elif regime == 'NORMAL':
        if change > 2 and sent_score > 10 and velocity > 0:
            rules_dir = 'LONG';  rules_conf = min(0.78, base_conf + 0.10)
        elif change < -2 and sent_score < -10 and velocity < 0:
            rules_dir = 'SHORT'; rules_conf = min(0.78, base_conf + 0.10)
        if symbol == 'GLD' and fg < 30:
            rules_dir = 'LONG';  rules_conf = min(0.80, base_conf + 0.15)
        elif symbol == 'BTC' and fg > 70 and change > 3:
            rules_dir = 'LONG';  rules_conf = min(0.75, base_conf + 0.10)
        elif symbol == 'NVDA' and change > 3 and sent_score > 5:
            rules_dir = 'LONG';  rules_conf = min(0.74, base_conf + 0.10)
    elif regime == 'FOMC_DAY':
        if symbol == 'GLD':
            rules_dir = 'LONG';  rules_conf = min(0.72, base_conf + 0.10)
        elif symbol in ['BTC','ETH'] and sent_score < -20:
            rules_dir = 'SHORT'; rules_conf = min(0.65, base_conf + 0.05)

    if var > 0.08:        rules_conf *= 0.85
    if abs(velocity) > 10: rules_conf = min(0.85, rules_conf + 0.05)
    if symbol == 'GLD' and fg < 20: rules_conf = min(0.88, rules_conf + 0.05)

    # ── Step 3: Fuse model + rules ────────────────────────
    if model_dir is not None and rules_dir is not None:
        if model_dir == rules_dir:
            # Agreement — boost confidence
            final_dir  = model_dir
            final_conf = min(0.92, (model_conf * 0.6 + rules_conf * 0.4) + 0.05)
            log.info(f"  {symbol} MODEL+RULES AGREE: {final_dir} conf:{final_conf:.3f}")
        else:
            # Disagreement — skip, log it
            log.info(f"  {symbol} MODEL({model_dir} {model_conf:.2f}) vs RULES({rules_dir} {rules_conf:.2f}) — SKIP")
            return 'HOLD', 0.5, None

    elif model_dir is not None and rules_dir is None:
        # Model only — use it if conviction high enough
        final_dir  = model_dir
        final_conf = model_conf
        log.info(f"  {symbol} MODEL ONLY: {final_dir} conf:{final_conf:.3f}")

    elif model_dir is None and rules_dir is not None:
        # Rules only — use rules
        final_dir  = rules_dir
        final_conf = rules_conf
        log.info(f"  {symbol} RULES ONLY: {final_dir} conf:{final_conf:.3f}")

    else:
        # Neither has conviction
        return 'HOLD', 0.5, None

    if final_dir is None:
        return 'HOLD', final_conf, None

    # ── Step 4: NLP sentiment modifier ───────────────────
    try:
        nlp = get_nlp_sentiment(symbol)
        nlp_score = nlp['score']
        nlp_label = nlp['label']
        fomc      = nlp['fomc']

        # NLP agrees with direction → boost confidence
        if final_dir == 'LONG' and nlp_score > 0.1:
            final_conf = min(0.92, final_conf + 0.05)
            log.info(f"  {symbol} NLP BOOST: {nlp_label} ({nlp_score:+.3f}) → conf:{final_conf:.3f}")
        elif final_dir == 'SHORT' and nlp_score < -0.1:
            final_conf = min(0.92, final_conf + 0.05)
            log.info(f"  {symbol} NLP BOOST: {nlp_label} ({nlp_score:+.3f}) → conf:{final_conf:.3f}")
        # NLP disagrees → reduce confidence
        elif final_dir == 'LONG' and nlp_score < -0.15:
            final_conf = max(0.45, final_conf - 0.03)
            log.info(f"  {symbol} NLP DRAG: {nlp_label} ({nlp_score:+.3f}) → conf:{final_conf:.3f}")
        elif final_dir == 'SHORT' and nlp_score > 0.15:
            final_conf = max(0.45, final_conf - 0.03)
            log.info(f"  {symbol} NLP DRAG: {nlp_label} ({nlp_score:+.3f}) → conf:{final_conf:.3f}")

        # FOMC hawkish → risk-off, reduce confidence on risky assets
        if fomc == 'HAWKISH' and symbol in ['BTC','ETH','NVDA','TSLA']:
            final_conf = max(0.45, final_conf - 0.05)
            log.info(f"  {symbol} FOMC HAWKISH penalty → conf:{final_conf:.3f}")
        elif fomc == 'DOVISH' and symbol == 'GLD':
            final_conf = max(0.45, final_conf - 0.03)
            log.info(f"  {symbol} FOMC DOVISH GLD drag → conf:{final_conf:.3f}")
    except Exception as e:
        log.warning(f"NLP modifier failed for {symbol}: {e}")

    # ── Step 9: Hypothesis engine ───────────────────────────
    try:
        from aria_hypothesis import apply_hypothesis
        hyp_mod, hyp_reason = apply_hypothesis(symbol, final_dir, regime)
        if hyp_mod > 0:
            final_conf = min(0.92, final_conf + hyp_mod)
            log.info(f"  {symbol} HYPOTHESIS BOOST: {hyp_reason} conf:{final_conf:.3f}")
    except Exception as e:
        log.warning(f"Hypothesis engine failed: {e}")

    # ── Step 8: Adversarial self-test ───────────────────────
    try:
        from aria_adversarial import adversarial_check
        adv_penalty, adv_reason = adversarial_check(symbol, final_dir, regime, fg)
        if adv_penalty < 0:
            final_conf = max(0.45, final_conf + adv_penalty)
            log.info(f"  {symbol} ADVERSARIAL PENALTY: {adv_reason} → conf:{final_conf:.3f}")
    except Exception as e:
        log.warning(f"Adversarial check failed: {e}")

    # ── Step 7: Cross-asset chain modifier ──────────────────
    try:
        from aria_cross_asset import evaluate as cross_eval
        cross = cross_eval(symbol, market_data)
        cross_mod = cross['modifier']
        if abs(cross_mod) > 0.01:
            if (final_dir == 'LONG' and cross_mod > 0) or (final_dir == 'SHORT' and cross_mod < 0):
                final_conf = min(0.92, final_conf + abs(cross_mod))
                log.info(f"  {symbol} CROSS-ASSET BOOST: {cross['active']} → conf:{final_conf:.3f}")
            else:
                final_conf = max(0.45, final_conf - abs(cross_mod))
                log.info(f"  {symbol} CROSS-ASSET DRAG: {cross['active']} → conf:{final_conf:.3f}")
    except Exception as e:
        log.warning(f"Cross-asset modifier failed: {e}")

    # ── Step 6: Causal graph modifier ───────────────────────
    try:
        from aria_causal_graph import evaluate as causal_evaluate
        nlp_data = get_nlp_sentiment(symbol)
        causal = causal_evaluate(symbol, fomc_signal=nlp_data.get('fomc','NEUTRAL'), fear_greed=fg, regime=regime)
        net = causal['net_modifier']
        if abs(net) > 0.02:
            if (final_dir == 'LONG' and net > 0) or (final_dir == 'SHORT' and net < 0):
                final_conf = min(0.92, final_conf + abs(net))
                log.info(f"  {symbol} CAUSAL BOOST: {causal['active_chains']} → conf:{final_conf:.3f}")
            elif (final_dir == 'LONG' and net < 0) or (final_dir == 'SHORT' and net > 0):
                final_conf = max(0.45, final_conf - abs(net))
                log.info(f"  {symbol} CAUSAL DRAG: {causal['active_chains']} → conf:{final_conf:.3f}")
    except Exception as e:
        log.warning(f"Causal graph modifier failed: {e}")

    # ── Step 5: Episodic memory modifier ─────────────────
    try:
        ep_modifier = get_episodic_modifier(symbol, final_dir, regime, fg)
        final_conf = min(0.92, max(0.45, final_conf + ep_modifier))
    except Exception as e:
        log.warning(f"Episodic modifier failed: {e}")

    return ('BUY' if final_dir == 'LONG' else 'SELL'), final_conf, final_dir

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

def log_cycle(cycle, sentiment, world):
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("INSERT INTO signal_log (signal_name,signal_value,symbol,triggered_action) VALUES (%s,%s,%s,%s)",
            ['v5_cycle', float(cycle), 'ALL',
             f"sent:{sentiment['score']:.1f} world:{world.get('narrative','?')} liq:{world.get('liquidity_state','?')}"])
        conn.commit(); cur.close(); conn.close()
    except: pass

def main():
    log.info("="*60)
    log.info("ARIA SWARM INTELLIGENCE v5 — DB-only, A+B+C integrated")
    log.info("PATCH 1: Trade close pipeline fixed")
    log.info("PATCH 2: world_state wired into signal + sizing")
    log.info("PATCH 3: XGBoost+RF ensemble live in generate_signal")
    log.info("="*60)
    cycle=0

    # Pre-load all models at startup
    log.info("Pre-loading models...")
    try:
        from aria_model_inference import load_model
        for sym in SYMBOLS:
            load_model(sym)
    except Exception as e:
        log.warning(f"Model pre-load failed: {e}")

    open_positions={}
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("""SELECT symbol, side, direction, size_usd, confidence, entry_price, created_at
            FROM orders_outbox WHERE status='EXECUTED' ORDER BY created_at DESC""")
        rows=cur.fetchall(); cur.close(); conn.close()
        for row in rows:
            if row[0] not in open_positions:
                open_positions[row[0]]={
                    'side': row[1], 'direction': row[2],
                    'size_usd': float(row[3]), 'confidence': float(row[4]),
                    'entry_price': float(row[5]) if row[5] else 0.0,
                    'entry_time': row[6], 'hold_cycles': 0
                }
        log.info(f"Restored {len(open_positions)} open positions: {list(open_positions.keys())}")
    except Exception as e:
        log.warning(f"Could not restore positions: {e}")

    while True:
        cycle+=1
        try:
            sentiment       = read_sentiment()
            market          = read_market()
            world           = read_world_state()
            portfolio_value = get_portfolio_value()

            # ── Exit logic ───────────────────────────────
            for symbol in list(open_positions.keys()):
                if symbol not in market: continue
                pos     = open_positions[symbol]
                entry   = pos.get('entry_price', 0)
                current = market[symbol].get('price', 0)
                if entry <= 0 or current <= 0: continue
                direction = pos.get('direction', 'LONG')
                pnl_pct = (current-entry)/entry if direction=='LONG' else (entry-current)/entry
                open_positions[symbol]['hold_cycles'] = pos.get('hold_cycles', 0) + 1
                if pnl_pct <= -0.05:
                    log.info(f"STOP LOSS triggered: {symbol} pnl:{pnl_pct*100:.1f}%")
                    if close_position(symbol, open_positions[symbol], current, 'STOP_LOSS', sentiment, world, cycle):
                        del open_positions[symbol]
                elif pnl_pct >= 0.08:
                    log.info(f"TAKE PROFIT triggered: {symbol} pnl:{pnl_pct*100:.1f}%")
                    if close_position(symbol, open_positions[symbol], current, 'TAKE_PROFIT', sentiment, world, cycle):
                        del open_positions[symbol]
                else:
                    # Time stop: close if open 48h+ and PnL between -2% and +2%
                    entry_time = pos.get('entry_time')
                    if entry_time:
                        hours_open = (datetime.utcnow() - entry_time.replace(tzinfo=None)).total_seconds() / 3600
                        if hours_open >= 48 and abs(pnl_pct) < 0.02:
                            log.info(f"TIME STOP: {symbol} open {hours_open:.1f}h pnl:{pnl_pct*100:.1f}% — closing flat")
                            if close_position(symbol, open_positions[symbol], current, 'TIME_STOP', sentiment, world, cycle):
                                del open_positions[symbol]

            sys_mode, sys_score = read_system_mode()
            safe_mode = sentiment['stale'] or not market or sys_mode == 'SAFE'
            regime    = sentiment.get('regime','NORMAL')
            score     = sentiment.get('score',0)
            vel       = sentiment.get('velocity',0)
            fg        = sentiment.get('fear_greed',50)
            stance    = sentiment.get('stance','NEUTRAL')
            narrative = world.get('narrative','?')
            liq       = world.get('liquidity_state','?')
            w_mult    = world_state_multiplier(world)

            log.info(f"[Cycle {cycle}] SysMode:{sys_mode}({sys_score}) Regime:{regime} Sent:{score:+.1f}({stance}) F&G:{fg} | World:{narrative} Liq:{liq} Wmult:{w_mult}x | Portfolio:${portfolio_value:.0f} Safe:{'ON' if safe_mode else 'OFF'} Open:{list(open_positions.keys())}")

            if safe_mode:
                log.info("Safe mode — no new trades this cycle")
                time.sleep(LOOP_INTERVAL); continue

            decisions=[]
            for symbol in SYMBOLS:
                if len(open_positions) >= MAX_OPEN_TRADES: break
                if symbol in open_positions: continue
                risk = read_risk(symbol)
                action, confidence, direction = generate_signal(symbol, market, sentiment, risk, world)
                if action == 'HOLD' or confidence < MIN_CONFIDENCE:
                    continue
                size_usd, kelly_frac, kelly_reasoning = kelly_size(symbol, confidence, sentiment, risk, world, portfolio_value)
                if size_usd < 50: continue
                # Cap 6: Multi-agent debate
                try:
                    from aria_debate import debate
                    from aria_episodic_memory import recall
                    from aria_causal_graph import evaluate as causal_eval
                    nlp_data = get_nlp_sentiment(symbol)
                    causal_data = causal_eval(symbol, fomc_signal=nlp_data.get('fomc','NEUTRAL'), fear_greed=sentiment.get('fear_greed',50), regime=sentiment.get('regime','NORMAL'))
                    ep_data = recall(symbol, direction, sentiment.get('regime','NORMAL'), sentiment.get('fear_greed',50))
                    verdict = debate(symbol, action, confidence, market, sentiment, nlp_data, causal_data, ep_data)
                    if verdict['verdict'] == 'REJECT':
                        log.info(f"  {symbol} DEBATE REJECTED — skipping")
                        continue
                    elif verdict['verdict'] == 'REDUCE':
                        size_usd = size_usd * 0.5
                        log.info(f"  {symbol} DEBATE REDUCED size to ${size_usd:.0f}")
                except Exception as e:
                    log.warning(f"Debate failed for {symbol}: {e}")
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
                    try:
                        conn2 = get_db()
                        cur2 = conn2.cursor()
                        cur2.execute("""
                            INSERT INTO positions_live (symbol, direction, entry_price, size_usd, regime_at_entry, sentiment_at_entry, fear_greed_at_entry, status)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, 'OPEN')
                            ON CONFLICT (symbol) DO UPDATE SET
                            direction=EXCLUDED.direction, entry_price=EXCLUDED.entry_price,
                            size_usd=EXCLUDED.size_usd, status='OPEN', updated_at=NOW()
                        """, (d['symbol'], d['direction'], d.get('entry_price', 0),
                               d['size_usd'], d.get('regime','NORMAL'),
                               d.get('sentiment_score', 0), d.get('fear_greed', 21)))
                        conn2.commit()
                        conn2.close()
                    except Exception as pe:
                        log.error(f"positions_live write failed: {pe}")
                    log.info(f"  ORDER: {d['action']} {d['symbol']} ${d['size_usd']:.0f}")

            # Cap 9: Self-improvement check every 60 cycles
            if cycle % 60 == 0:
                try:
                    from aria_self_improvement import run_improvement_check
                    results = run_improvement_check()
                    for r in results:
                        if r['action'] != 'STABLE':
                            log.warning(f"  SELF-IMPROVE {r['symbol']}: {r['action']} recent:{r['recent']:.0%} baseline:{r['baseline']:.0%}")
                except Exception as e:
                    log.warning(f"Self-improvement check failed: {e}")
            log_cycle(cycle, sentiment, world)
            log.info(f"  Decisions:{len(decisions)} | Open:{len(open_positions)} | Portfolio:${portfolio_value:.0f}")

        except Exception as e:
            log.error(f"Cycle {cycle} error: {e}")
            import traceback; traceback.print_exc()
            time.sleep(10)
        time.sleep(LOOP_INTERVAL)

if __name__=='__main__':
    main()
