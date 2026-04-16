#!/usr/bin/env python3
"""ARIA Layer 5 — Meta-Controller: Brain Above The Brain"""
import time, json, logging, psycopg2
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [META] %(message)s')
log = logging.getLogger()
DB = {'host':'localhost','port':5432,'dbname':'aria_db','user':'postgres','password':'aria_secure_2026'}

def get_db(): return psycopg2.connect(**DB)

def get_sentiment():
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("SELECT score,regime,fear_greed,velocity FROM sentiment_latest ORDER BY updated_at DESC LIMIT 1")
        row=cur.fetchone(); cur.close(); conn.close()
        if row: return {'score':float(row[0]),'regime':str(row[1]),'fear_greed':int(row[2]),'velocity':float(row[3])}
    except: pass
    return {'score':0.0,'regime':'NORMAL','fear_greed':50,'velocity':0.0}

def get_pattern_performance():
    """Read pattern library — what's working in current regime"""
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("""SELECT symbol, action_taken, outcome, pnl, confidence, regime
                      FROM pattern_library ORDER BY updated_at DESC LIMIT 50""")
        rows=cur.fetchall(); cur.close(); conn.close()
        performance={}
        for row in rows:
            symbol=row[0]
            if symbol not in performance:
                performance[symbol]={'wins':0,'losses':0,'total':0,'avg_pnl':0}
            performance[symbol]['total']+=1
            if row[2]=='WIN': performance[symbol]['wins']+=1
            else: performance[symbol]['losses']+=1
            performance[symbol]['avg_pnl']+=float(row[3] or 0)
        for sym in performance:
            t=performance[sym]['total']
            performance[sym]['win_rate']=performance[sym]['wins']/t if t>0 else 0.5
            performance[sym]['avg_pnl']=performance[sym]['avg_pnl']/t if t>0 else 0
        return performance
    except: return {}

def calculate_weights(sentiment, performance):
    regime=sentiment.get('regime','NORMAL')
    score=sentiment.get('score',0)
    velocity=sentiment.get('velocity',0)
    fg=sentiment.get('fear_greed',50)

    # Base weights by regime
    if regime=='CRISIS':
        w={'GLD':0.35,'BTC':0.18,'ETH':0.15,'NVDA':0.12,'AAPL':0.12,'TSLA':0.08}
    elif regime=='FOMC_DAY':
        w={'GLD':0.30,'BTC':0.18,'ETH':0.14,'NVDA':0.14,'AAPL':0.14,'TSLA':0.10}
    else:
        w={'BTC':0.22,'ETH':0.18,'NVDA':0.18,'AAPL':0.17,'GLD':0.15,'TSLA':0.10}

    # Adjust based on pattern library performance
    for symbol, perf in performance.items():
        if symbol in w and perf['total']>=3:
            if perf['win_rate']>0.6:
                w[symbol]=min(0.50,w[symbol]*1.2)
                log.info(f"  BOOST {symbol}: win_rate={perf['win_rate']:.0%}")
            elif perf['win_rate']<0.4:
                w[symbol]=max(0.02,w[symbol]*0.6)
                log.info(f"  KILL {symbol}: win_rate={perf['win_rate']:.0%}")

    # Sentiment adjustments
    if score<-30: w['GLD']=min(0.50,w['GLD']*1.4); w['BTC']*=0.7
    elif score>30: w['BTC']=min(0.28,w['BTC']*1.3); w['GLD']*=0.7
    if velocity<-5: w['GLD']=min(0.55,w['GLD']*1.2)

    total=sum(w.values())
    return {k:round(v/total,4) for k,v in w.items()}

def write_config(weights, sentiment, cycle):
    conn=get_db(); cur=conn.cursor()
    for key,val in [('capital_weights',json.dumps(weights)),
                    ('meta_regime',sentiment['regime']),
                    ('meta_cycle',str(cycle))]:
        cur.execute("""INSERT INTO aria_config (key,value,updated_at) VALUES (%s,%s,NOW())
            ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()""",[key,val])
    top=max(weights,key=weights.get)
    cur.execute("""INSERT INTO meta_log (cycle,regime,sentiment,top_symbol,weights,reasoning)
        VALUES (%s,%s,%s,%s,%s,%s)""",
        [cycle,sentiment['regime'],sentiment['score'],top,json.dumps(weights),
         f"Regime:{sentiment['regime']} Score:{sentiment['score']:.1f} Top:{top}"])
    conn.commit(); cur.close(); conn.close()

def main():
    log.info("="*60)
    log.info("ARIA Layer 5 — Meta-Controller V1")
    log.info("Reads pattern library → allocates capital → kills weak signals")
    log.info("="*60)
    cycle=0
    while True:
        cycle+=1
        try:
            sentiment=get_sentiment()
            performance=get_pattern_performance()
            weights=calculate_weights(sentiment,performance)
            write_config(weights,sentiment,cycle)
            regime=sentiment['regime']; score=sentiment['score']; fg=sentiment['fear_greed']
            log.info(f"[Cycle {cycle}] Regime:{regime} Score:{score:+.1f} F&G:{fg}")
            log.info("Capital allocation:")
            for sym,w in sorted(weights.items(),key=lambda x:x[1],reverse=True):
                log.info(f"  {sym:5} {'█'*int(w*30):30} {w*100:.1f}%")
            top=max(weights,key=weights.get)
            log.info(f"Top signal: {top} ({weights[top]*100:.1f}%)")
        except Exception as e:
            log.error(f"Meta error: {e}")
        time.sleep(300)

if __name__=='__main__':
    main()
