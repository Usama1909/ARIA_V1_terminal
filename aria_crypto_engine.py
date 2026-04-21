"""
ARIA Crypto Signal Engine
Dedicated signal generator for BTC/ETH
Uses: Funding Rate + Open Interest + Price Momentum
No XGBoost — rules-based until 500+ trade history accumulated
"""
import psycopg2, logging
log = logging.getLogger()
DB = {'host':'localhost','port':5432,'dbname':'aria_db','user':'postgres','password':'aria_secure_2026'}

def get_crypto_signal(symbol):
    """
    Returns (direction, confidence, reason)
    direction: 'LONG', 'SHORT', or 'HOLD'
    """
    try:
        conn = psycopg2.connect(**DB); cur = conn.cursor()
        cur.execute("SELECT price, change_24h, funding_rate, oi_change_pct FROM market_state_latest WHERE symbol=%s", [symbol])
        row = cur.fetchone(); cur.close(); conn.close()
        if not row:
            return 'HOLD', 0.5, 'no_data'
        price, change_24h, funding_rate, oi_change = row
        funding_rate = float(funding_rate or 0)
        oi_change = float(oi_change or 0)
        change_24h = float(change_24h or 0)

        reasons = []
        long_score = 0
        short_score = 0

        # Funding rate signal
        if funding_rate < -0.01:
            long_score += 2
            reasons.append(f"funding:{funding_rate:.4f}%(squeeze_risk)")
        elif funding_rate > 0.02:
            short_score += 2
            reasons.append(f"funding:{funding_rate:.4f}%(overleveraged_longs)")

        # OI + Price momentum signal
        if oi_change > 0.05 and change_24h > 0:
            long_score += 2
            reasons.append(f"OI_rising+price_up")
        elif oi_change > 0.05 and change_24h < 0:
            short_score += 2
            reasons.append(f"OI_rising+price_down")
        elif oi_change < -0.05 and change_24h > 0:
            long_score += 1
            reasons.append(f"short_squeeze")
        elif oi_change < -0.05 and change_24h < 0:
            short_score += 1
            reasons.append(f"longs_exiting")

        # Price momentum
        if change_24h > 2:
            long_score += 1
            reasons.append(f"momentum:+{change_24h:.1f}%")
        elif change_24h < -2:
            short_score += 1
            reasons.append(f"momentum:{change_24h:.1f}%")

        # Decision
        if long_score >= 3 and long_score > short_score:
            conf = min(0.80, 0.55 + long_score * 0.05)
            return 'LONG', conf, ' | '.join(reasons)
        elif short_score >= 3 and short_score > long_score:
            conf = min(0.80, 0.55 + short_score * 0.05)
            return 'SHORT', conf, ' | '.join(reasons)
        else:
            return 'HOLD', 0.5, f"no_conviction(long:{long_score} short:{short_score})"

    except Exception as e:
        log.warning(f"Crypto engine failed {symbol}: {e}")
        return 'HOLD', 0.5, 'error'
