#!/usr/bin/env python3
"""ARIA Layer 7 — World Model — WHY markets move"""
import time, psycopg2, logging, json
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [WORLD] %(message)s')
log = logging.getLogger()
DB = {'host':'localhost','port':5432,'dbname':'aria_db','user':'postgres','password':'aria_secure_2026'}

def get_db(): return psycopg2.connect(**DB)

def init_db():
    conn=get_db(); cur=conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS world_state (
        id SERIAL PRIMARY KEY, narrative VARCHAR(50), narrative_detail TEXT,
        macro_phase VARCHAR(30), risk_appetite VARCHAR(20), liquidity_state VARCHAR(20),
        dominant_driver VARCHAR(100), yield_curve VARCHAR(20), confidence FLOAT,
        updated_at TIMESTAMP DEFAULT NOW())""")
    conn.commit(); cur.close(); conn.close()

def get_current_data():
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("SELECT score,regime,fear_greed,velocity FROM sentiment_latest LIMIT 1")
        sent=cur.fetchone()
        cur.execute("SELECT symbol,price,change_24h FROM market_state_latest")
        market={r[0]:{'price':float(r[1]),'change':float(r[2])} for r in cur.fetchall()}
        cur.close(); conn.close()
        return {'sentiment':float(sent[0]) if sent else 0,'regime':str(sent[1]) if sent else 'NORMAL',
                'fear_greed':int(sent[2]) if sent else 50,'velocity':float(sent[3]) if sent else 0,'market':market}
    except Exception as e:
        log.error(f"Data read: {e}"); return {}

def classify_narrative(data):
    sentiment=data.get('sentiment',0); regime=data.get('regime','NORMAL')
    fg=data.get('fear_greed',50); velocity=data.get('velocity',0); market=data.get('market',{})
    btc=market.get('BTC',{}).get('change',0); gold=market.get('GLD',{}).get('change',0)
    nvda=market.get('NVDA',{}).get('change',0)
    if gold>1 and sentiment<-20 and btc<0:
        n,detail,driver='INFLATION_FEAR','Gold rising as inflation hedge','Inflation concerns driving safe haven demand'
    elif nvda>2 and sentiment>10:
        n,detail,driver='AI_OPTIMISM','AI/tech stocks leading rally','AI earnings driving tech premium'
    elif sentiment<-40 and btc<-2 and gold<0:
        n,detail,driver='LIQUIDITY_CRUNCH','Broad selloff — liquidity squeeze','Forced selling across markets'
    elif btc<-3 and sentiment<-20:
        n,detail,driver='CRYPTO_FEAR','Crypto leading risk-off move','Crypto sentiment driving risk appetite'
    elif gold>0.5 and btc<0 and fg<30:
        n,detail,driver='SAFE_HAVEN_DEMAND','Flight to safety — gold outperforming','Uncertainty driving safe haven flows'
    elif sentiment>20 and btc>1 and nvda>0:
        n,detail,driver='RISK_ON','Broad risk appetite — equities and crypto rallying','Positive macro / Fed pivot expectations'
    else:
        n,detail,driver='CONSOLIDATION','Mixed signals — market searching for direction','No clear dominant theme'
    macro_phase='LATE_CYCLE_STRESS' if regime=='CRISIS' and fg<25 else('CONTRACTION' if sentiment<-20 else('EXPANSION' if sentiment>20 else 'MID_CYCLE'))
    risk_appetite='CRISIS' if fg<20 or regime=='CRISIS' else('LOW' if fg<40 or sentiment<-20 else('HIGH' if fg>70 or sentiment>30 else 'MODERATE'))
    liquidity='FROZEN' if n=='LIQUIDITY_CRUNCH' else('FRAGILE' if regime=='CRISIS' or fg<25 else 'NORMAL')
    signals_agree=sum([sentiment<-20 and fg<30, gold>0 and btc<0, regime=='CRISIS' and velocity<0])
    return {'narrative':n,'narrative_detail':detail,'macro_phase':macro_phase,
            'risk_appetite':risk_appetite,'liquidity_state':liquidity,'dominant_driver':driver,
            'yield_curve':'NORMAL','confidence':round(0.5+signals_agree*0.15,2)}

def write_world_state(state, data):
    conn=get_db(); cur=conn.cursor()
    cur.execute("""INSERT INTO world_state (narrative,narrative_detail,macro_phase,risk_appetite,
        liquidity_state,dominant_driver,yield_curve,confidence,updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
        [state['narrative'],state['narrative_detail'],state['macro_phase'],state['risk_appetite'],
         state['liquidity_state'],state['dominant_driver'],state['yield_curve'],state['confidence']])
    cur.execute("""INSERT INTO aria_config (key,value,updated_at) VALUES ('world_state',%s,NOW())
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()""",[json.dumps(state)])
    conn.commit(); cur.close(); conn.close()

def main():
    log.info("="*60)
    log.info("ARIA Layer 7 — World Model — WHY markets move")
    log.info("="*60)
    init_db(); cycle=0
    while True:
        cycle+=1
        try:
            data=get_current_data(); state=classify_narrative(data)
            write_world_state(state,data)
            log.info(f"[Cycle {cycle}] Narrative:{state['narrative']} Phase:{state['macro_phase']} Risk:{state['risk_appetite']} Liquidity:{state['liquidity_state']}")
            log.info(f"  Driver: {state['dominant_driver']} | Confidence:{state['confidence']:.0%}")
        except Exception as e:
            log.error(f"World model error: {e}")
        time.sleep(900)

if __name__=='__main__':
    main()
