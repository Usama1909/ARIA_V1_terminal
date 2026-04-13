#!/usr/bin/env python3
"""
ARIA Layer 6 — Learning Loop
Runs every Sunday 03:00 UTC — retrains models from closed_trades.
Also runs on-demand when pattern library has enough new data.
This is what makes ARIA smarter every week.

PATCH: Feed promoted signals back into meta-controller via aria_config.
PATCH: Update pattern_library win_count and times_matched after evaluation.
"""
import time, psycopg2, logging, json, numpy as np
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s [LEARN] %(message)s')
log = logging.getLogger()
DB = {'host':'localhost','port':5432,'dbname':'aria_db','user':'postgres','password':'aria_secure_2026'}

def get_db(): return psycopg2.connect(**DB)

def get_training_data():
    """Get closed trades for training."""
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("""SELECT symbol, direction, pnl_pct, regime_at_entry,
                      sentiment_at_entry, fear_greed_at_entry, outcome
                      FROM closed_trades ORDER BY exit_time DESC LIMIT 1000""")
        rows=cur.fetchall(); cur.close(); conn.close()
        return rows
    except Exception as e:
        log.error(f"Training data fetch: {e}"); return []

def evaluate_signal_performance():
    """Evaluate each signal's performance and update pattern library."""
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("""SELECT symbol, regime_at_entry, direction,
            COUNT(*) as trades,
            SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) as wins,
            AVG(pnl_pct) as avg_pnl,
            STDDEV(pnl_pct) as std_pnl
            FROM closed_trades
            WHERE exit_time > NOW() - INTERVAL '30 days'
            GROUP BY symbol, regime_at_entry, direction
            HAVING COUNT(*) >= 3""")
        rows=cur.fetchall()
        results=[]
        for row in rows:
            symbol,regime,direction,trades,wins,avg_pnl,std_pnl=row
            win_rate=float(wins)/float(trades)
            sharpe=float(avg_pnl or 0)/float(std_pnl or 1) if std_pnl else 0
            # Promotion policy: must beat 55% win rate and positive Sharpe
            promoted=win_rate>0.55 and sharpe>0
            results.append({
                'symbol':symbol,'regime':regime,'direction':direction,
                'trades':trades,'win_rate':win_rate,'avg_pnl':float(avg_pnl or 0),
                'sharpe':sharpe,'promoted':promoted
            })
            log.info(f"  {symbol} {regime} {direction}: WR={win_rate:.0%} Sharpe={sharpe:.2f} {'✅ PROMOTED' if promoted else '❌ REJECTED'}")
        cur.close(); conn.close()
        return results
    except Exception as e:
        log.error(f"Evaluation: {e}"); return []

def update_pattern_library(results):
    """
    Update pattern_library win_count, times_matched from evaluation results.
    This is what makes the meta-controller BOOST/KILL logic actually work.
    """
    try:
        conn=get_db(); cur=conn.cursor()
        for r in results:
            wins = int(r['win_rate'] * r['trades'])
            cur.execute("""
                UPDATE pattern_library
                SET times_matched = %s,
                    win_count     = %s,
                    updated_at    = NOW()
                WHERE symbol = %s
                AND regime   = %s
                AND action_taken = %s
            """, [
                r['trades'],
                wins,
                r['symbol'],
                r['regime'],
                'BUY' if r['direction'] == 'LONG' else 'SELL'
            ])
        conn.commit(); cur.close(); conn.close()
        log.info(f"pattern_library updated: {len(results)} patterns refreshed")
    except Exception as e:
        log.error(f"pattern_library update failed: {e}")

def update_model_registry(results):
    """Write evaluation results to model registry."""
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS model_registry (
            id SERIAL PRIMARY KEY, symbol VARCHAR(10), regime VARCHAR(20),
            direction VARCHAR(10), win_rate FLOAT, sharpe FLOAT,
            trades INT, promoted BOOLEAN, trained_at TIMESTAMP DEFAULT NOW()
        )""")
        for r in results:
            cur.execute("""INSERT INTO model_registry
                (symbol,regime,direction,win_rate,sharpe,trades,promoted,trained_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())""",
                [r['symbol'],r['regime'],r['direction'],
                 r['win_rate'],r['sharpe'],r['trades'],r['promoted']])
        conn.commit(); cur.close(); conn.close()
        log.info(f"Model registry updated: {len(results)} entries")
    except Exception as e:
        log.error(f"Registry update: {e}")

def feed_to_meta_controller(results):
    """
    Write promoted/rejected signals to aria_config so meta-controller
    can read them and apply BOOST/KILL logic immediately.
    Format: {'BOOST': ['BTC_CRISIS_SHORT', ...], 'KILL': ['NVDA_NORMAL_LONG', ...]}
    """
    try:
        boost = []
        kill  = []
        for r in results:
            key = f"{r['symbol']}_{r['regime']}_{r['direction']}"
            if r['promoted']:
                boost.append({'key': key, 'win_rate': r['win_rate'], 'sharpe': r['sharpe']})
            elif r['win_rate'] < 0.40:
                kill.append({'key': key, 'win_rate': r['win_rate'], 'sharpe': r['sharpe']})

        signal_feedback = {
            'BOOST':      boost,
            'KILL':       kill,
            'updated_at': datetime.utcnow().isoformat(),
            'total_eval': len(results)
        }

        conn=get_db(); cur=conn.cursor()
        cur.execute("""
            INSERT INTO aria_config (key, value, updated_at)
            VALUES ('signal_feedback', %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
        """, [json.dumps(signal_feedback)])
        conn.commit(); cur.close(); conn.close()

        log.info(f"Meta-controller feedback: {len(boost)} BOOST, {len(kill)} KILL signals")
        for b in boost:
            log.info(f"  BOOST: {b['key']} WR={b['win_rate']:.0%}")
        for k in kill:
            log.info(f"  KILL:  {k['key']} WR={k['win_rate']:.0%}")

    except Exception as e:
        log.error(f"Meta-controller feedback failed: {e}")

def should_retrain():
    """Check if enough new data to retrain."""
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("""SELECT COUNT(*) FROM closed_trades
            WHERE exit_time > NOW() - INTERVAL '7 days'""")
        recent=cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM closed_trades")
        total=cur.fetchone()[0]
        cur.close(); conn.close()
        log.info(f"Closed trades: {total} total, {recent} in last 7 days")
        return recent>=10 or total>=20
    except: return False

def is_sunday_3am():
    now=datetime.utcnow()
    return now.weekday()==6 and now.hour==3 and now.minute<5

def main():
    log.info("="*60)
    log.info("ARIA Layer 6 — Learning Loop")
    log.info("Retrains every Sunday 03:00 UTC or when 10+ new trades")
    log.info("PATCH: Feeds results to meta-controller + pattern_library")
    log.info("="*60)
    cycle=0
    while True:
        cycle+=1
        try:
            data=get_training_data()
            total_trades=len(data)
            log.info(f"[Cycle {cycle}] Total closed trades: {total_trades}")

            if total_trades == 0:
                log.info("No closed trades yet — waiting for pattern library to fill")
                log.info("System will retrain automatically when trades close")

            elif is_sunday_3am() or should_retrain():
                log.info(f"RETRAINING — {total_trades} trades available")
                results = evaluate_signal_performance()

                if results:
                    update_pattern_library(results)
                    update_model_registry(results)
                    feed_to_meta_controller(results)
                    promoted = [r for r in results if r['promoted']]
                    log.info(f"Training complete: {len(promoted)}/{len(results)} signals promoted")
                else:
                    log.info("No patterns met minimum trade threshold (3+ trades per signal)")

            else:
                log.info(f"Watching — need 10+ recent trades to retrain (have {total_trades})")

        except Exception as e:
            log.error(f"Learning error: {e}")
            import traceback; traceback.print_exc()

        time.sleep(3600)  # Check every hour

if __name__=='__main__':
    main()
