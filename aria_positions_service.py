#!/usr/bin/env python3
"""
ARIA Layer 4 — Positions Service & Pattern Builder
Monitors orders_outbox fills → builds positions_live → writes closed_trades → builds pattern_library
This is what gives ARIA a past.
"""
import time, psycopg2, logging, json
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [MEMORY] %(message)s')
log = logging.getLogger()
DB = {'host':'localhost','port':5432,'dbname':'aria_db','user':'postgres','password':'aria_secure_2026'}

def get_db(): return psycopg2.connect(**DB)

def sync_positions():
    """Build positions_live from orders_outbox fills"""
    conn=get_db(); cur=conn.cursor()
    # Get all executed orders
    cur.execute("""SELECT symbol,side,direction,size_usd,entry_price,created_at,confidence
                  FROM orders_outbox WHERE status='EXECUTED' ORDER BY created_at""")
    executed=cur.fetchall()
    # Get all closed orders
    cur.execute("SELECT symbol FROM orders_outbox WHERE status='CLOSED'")
    closed_symbols={r[0] for r in cur.fetchall()}
    # Get current sentiment for context
    cur.execute("SELECT score,regime,fear_greed,velocity FROM sentiment_latest LIMIT 1")
    sent=cur.fetchone()
    sentiment=float(sent[0]) if sent else 0.0
    regime=str(sent[1]) if sent else 'NORMAL'
    fg=int(sent[2]) if sent else 50
    velocity=float(sent[3]) if sent else 0.0
    # Build positions_live
    cur.execute("DELETE FROM positions_live")
    for row in executed:
        symbol,side,direction,size_usd,entry_price,created_at,confidence=row
        if symbol in closed_symbols: continue
        cur.execute("""INSERT INTO positions_live
            (symbol,direction,entry_price,entry_time,size_usd,
             regime_at_entry,sentiment_at_entry,fear_greed_at_entry,status,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'OPEN',NOW())
            ON CONFLICT (symbol) DO UPDATE SET
            direction=EXCLUDED.direction, entry_price=EXCLUDED.entry_price,
            updated_at=NOW()""",
            [symbol,direction,entry_price,created_at,size_usd,regime,sentiment,fg])
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM positions_live")
    count=cur.fetchone()[0]
    cur.close(); conn.close()
    return count

def check_and_close_positions():
    """Check market prices vs positions — write closed_trades on exit"""
    conn=get_db(); cur=conn.cursor()
    # Get open positions
    cur.execute("SELECT symbol,direction,entry_price,size_usd,regime_at_entry,sentiment_at_entry,fear_greed_at_entry,entry_time FROM positions_live WHERE status='OPEN'")
    positions=cur.fetchall()
    # Get current prices
    cur.execute("SELECT symbol,price FROM market_state_latest")
    prices={r[0]:float(r[1]) for r in cur.fetchall()}
    closed=0
    for pos in positions:
        symbol,direction,entry_price,size_usd,regime,sentiment,fg,entry_time=pos
        if symbol not in prices or entry_price<=0: continue
        current=prices[symbol]
        pnl_pct=((current-entry_price)/entry_price) if direction=='LONG' else ((entry_price-current)/entry_price)
        pnl_usd=round(size_usd*pnl_pct,2)
        # Check if closed in orders_outbox
        cur.execute("SELECT COUNT(*) FROM orders_outbox WHERE symbol=%s AND status='CLOSED'",[symbol])
        is_closed=cur.fetchone()[0]>0
        if is_closed or abs(pnl_pct)>=0.05:
            outcome='WIN' if pnl_pct>0 else 'LOSS'
            hold_hours=int((datetime.utcnow()-entry_time.replace(tzinfo=None)).total_seconds()/3600) if entry_time else 0
            cur.execute("""INSERT INTO closed_trades
                (symbol,direction,entry_price,exit_price,entry_time,exit_time,
                 pnl_usd,pnl_pct,size_usd,regime_at_entry,sentiment_at_entry,
                 fear_greed_at_entry,outcome,hold_cycles)
                VALUES (%s,%s,%s,%s,%s,NOW(),%s,%s,%s,%s,%s,%s,%s,%s)""",
                [symbol,direction,entry_price,current,entry_time,
                 pnl_usd,round(pnl_pct,4),size_usd,regime,sentiment,fg,outcome,hold_hours])
            cur.execute("UPDATE positions_live SET status='CLOSED' WHERE symbol=%s",[symbol])
            log.info(f"CLOSED {symbol} {direction} PnL:{pnl_pct*100:.1f}% ({outcome}) ${pnl_usd:.2f}")
            closed+=1
    conn.commit(); cur.close(); conn.close()
    return closed

def build_pattern_library():
    """Aggregate closed_trades into pattern_library"""
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT COUNT(*) FROM closed_trades")
    total=cur.fetchone()[0]
    if total==0:
        cur.close(); conn.close()
        return 0
    # Aggregate by symbol + regime
    cur.execute("""SELECT symbol, regime_at_entry, direction,
        COUNT(*) as trades,
        SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) as wins,
        AVG(pnl_pct) as avg_pnl,
        AVG(CASE WHEN outcome='WIN' THEN pnl_pct END) as avg_win,
        AVG(CASE WHEN outcome='LOSS' THEN pnl_pct END) as avg_loss,
        MAX(pnl_pct) as best_trade,
        MIN(pnl_pct) as worst_trade
        FROM closed_trades
        GROUP BY symbol, regime_at_entry, direction""")
    rows=cur.fetchall()
    patterns_written=0
    for row in rows:
        symbol,regime,direction,trades,wins,avg_pnl,avg_win,avg_loss,best,worst=row
        win_rate=float(wins)/float(trades) if trades>0 else 0
        avg_r=float(avg_win or 0)/abs(float(avg_loss or 1)) if avg_loss else 0
        # Write to pattern_library
        cur.execute("""INSERT INTO pattern_library
            (fingerprint, action_taken, symbol, outcome, pnl, confidence, hold_hours, regime)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING""",
            [json.dumps({'symbol':symbol,'regime':regime,'direction':direction,'trades':trades}),
             direction, symbol,
             'WIN' if win_rate>0.5 else 'LOSS',
             float(avg_pnl or 0), win_rate, 0, regime])
        patterns_written+=1
    conn.commit(); cur.close(); conn.close()
    log.info(f"Pattern library: {patterns_written} patterns from {total} closed trades")
    return patterns_written

def main():
    log.info("="*60)
    log.info("ARIA Layer 4 — Memory & Pattern Library Service")
    log.info("positions_live → closed_trades → pattern_library")
    log.info("="*60)
    cycle=0
    while True:
        cycle+=1
        try:
            positions=sync_positions()
            closed=check_and_close_positions()
            patterns=build_pattern_library()
            log.info(f"[Cycle {cycle}] Open:{positions} Closed:{closed} Patterns:{patterns}")
        except Exception as e:
            log.error(f"Memory error: {e}")
            import traceback; traceback.print_exc()
        time.sleep(60)

if __name__=='__main__':
    main()
