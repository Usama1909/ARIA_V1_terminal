import psycopg2
import logging

log = logging.getLogger()
DB = {"host":"localhost","port":5432,"dbname":"aria_db","user":"postgres","password":"aria_secure_2026"}

def get_db():
    return psycopg2.connect(**DB)

def recall_regime(narrative, macro_phase, risk_appetite):
    """
    Look up historical performance when similar regime conditions existed.
    Returns asset-level modifiers based on what happened last time.
    """
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT symbol, direction, outcome, pnl_pct
            FROM closed_trades
            WHERE regime_at_entry=%s
        """, [narrative if narrative in ('NORMAL','CRISIS','BULL','BEAR') else 'NORMAL'])
        rows = cur.fetchall()
        cur.close(); conn.close()

        if not rows:
            return {}

        from collections import defaultdict
        stats = defaultdict(lambda: {'wins': 0, 'total': 0, 'pnl': []})
        for symbol, direction, outcome, pnl in rows:
            key = f"{symbol}_{direction}"
            stats[key]['total'] += 1
            stats[key]['pnl'].append(float(pnl))
            if outcome == 'WIN':
                stats[key]['wins'] += 1

        modifiers = {}
        for key, s in stats.items():
            if s['total'] < 3:
                continue
            wr = s['wins'] / s['total']
            avg_pnl = sum(s['pnl']) / len(s['pnl'])
            symbol, direction = key.split('_')
            if wr >= 0.65:
                modifiers[key] = {'modifier': +0.04, 'wr': wr, 'n': s['total']}
            elif wr <= 0.35:
                modifiers[key] = {'modifier': -0.04, 'wr': wr, 'n': s['total']}

        return modifiers
    except Exception as e:
        log.warning(f"Regime recall failed: {e}")
        return {}

def get_regime_modifier(symbol, direction, narrative, macro_phase, risk_appetite):
    """Get confidence modifier based on regime memory."""
    modifiers = recall_regime(narrative, macro_phase, risk_appetite)
    key = f"{symbol}_{direction}"
    if key in modifiers:
        mod = modifiers[key]['modifier']
        wr = modifiers[key]['wr']
        n = modifiers[key]['n']
        log.info(f"  {symbol} REGIME MEMORY: wr:{wr:.0%} n:{n} modifier:{mod:+.2f}")
        return mod, f"REGIME_MATCH(wr:{wr:.0%},n:{n})"
    return 0.0, "NO_REGIME_MATCH"

if __name__ == "__main__":
    print("=== Regime Memory Test ===")
    for symbol in ['BTC','ETH','NVDA','GLD','TSLA','AAPL']:
        mod, reason = get_regime_modifier(symbol, 'LONG', 'CONSOLIDATION', 'CONTRACTION', 'LOW')
        print(f"{symbol} LONG: modifier:{mod:+.3f} reason:{reason}")
