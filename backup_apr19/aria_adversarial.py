import psycopg2
import logging

log = logging.getLogger()
DB = {"host":"localhost","port":5432,"dbname":"aria_db","user":"postgres","password":"aria_secure_2026"}

def get_db():
    return psycopg2.connect(**DB)

def get_failure_patterns():
    """Extract conditions where strategy historically fails."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT symbol, direction, regime_at_entry,
                   COUNT(*) as total,
                   SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) as losses,
                   AVG(pnl_pct) as avg_pnl
            FROM closed_trades
            GROUP BY symbol, direction, regime_at_entry
            HAVING COUNT(*) >= 2
            ORDER BY losses DESC
        """)
        rows = cur.fetchall()
        cur.close(); conn.close()
        patterns = []
        for r in rows:
            symbol, direction, regime, total, losses, avg_pnl = r
            loss_rate = losses / total if total > 0 else 0
            if loss_rate >= 0.5:
                patterns.append({
                    'symbol': symbol,
                    'direction': direction,
                    'regime': regime,
                    'loss_rate': round(loss_rate, 2),
                    'total': total,
                    'avg_pnl': round(float(avg_pnl), 4)
                })
        return patterns
    except Exception as e:
        log.warning(f"Failure pattern extraction failed: {e}")
        return []

def adversarial_check(symbol, direction, regime, fear_greed):
    """
    Check if current trade matches known failure patterns.
    Returns penalty modifier and reason.
    """
    try:
        patterns = get_failure_patterns()
        for p in patterns:
            if p['symbol'] == symbol and p['direction'] == direction and p['regime'] == regime:
                if p['loss_rate'] >= 0.7:
                    penalty = -0.10
                    reason = f"HIGH_FAIL_RATE({p['loss_rate']:.0%} loss, n={p['total']})"
                elif p['loss_rate'] >= 0.5:
                    penalty = -0.05
                    reason = f"MOD_FAIL_RATE({p['loss_rate']:.0%} loss, n={p['total']})"
                else:
                    continue
                log.info(f"  {symbol} ADVERSARIAL: {reason} → penalty:{penalty}")
                return penalty, reason
        return 0.0, "NO_FAILURE_PATTERN"
    except Exception as e:
        log.warning(f"Adversarial check failed: {e}")
        return 0.0, "ERROR"

if __name__ == "__main__":
    print("=== Adversarial Self-Test ===")
    patterns = get_failure_patterns()
    print(f"Found {len(patterns)} failure patterns:")
    for p in patterns:
        print(f"  {p['symbol']} {p['direction']} {p['regime']}: {p['loss_rate']:.0%} loss rate (n={p['total']}) avg_pnl:{p['avg_pnl']:+.3f}")
    print("\n=== Live Check ===")
    for symbol, direction, regime in [('BTC','LONG','CRISIS'), ('ETH','LONG','NORMAL'), ('NVDA','LONG','NORMAL')]:
        penalty, reason = adversarial_check(symbol, direction, regime, 23)
        print(f"{symbol} {direction} {regime}: penalty:{penalty} reason:{reason}")
