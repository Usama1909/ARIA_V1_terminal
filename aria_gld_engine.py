#!/usr/bin/env python3
"""
ARIA GLD Signal Engine
Gold moves on: DXY inverse, Fear & Greed, price momentum
"""
import psycopg2, logging
log = logging.getLogger()
DB = {'host':'localhost','port':5432,'dbname':'aria_db','user':'postgres','password':'aria_secure_2026'}

def get_gld_signal():
    try:
        conn = psycopg2.connect(**DB); cur = conn.cursor()
        cur.execute("SELECT price, change_24h FROM market_state_latest WHERE symbol='GLD'")
        gld = cur.fetchone()
        cur.execute("SELECT price, change_24h FROM market_state_latest WHERE symbol='DXY'")
        dxy = cur.fetchone()
        cur.execute("SELECT score, fear_greed, regime FROM sentiment_latest ORDER BY updated_at DESC LIMIT 1")
        sent = cur.fetchone()
        cur.close(); conn.close()

        if not gld or not sent:
            return 'HOLD', 0.5, 'no_data'

        gld_change = float(gld[1] or 0)
        dxy_change = float(dxy[1] or 0) if dxy else 0
        fear_greed = int(sent[1] or 50)
        sentiment = float(sent[0] or 0)
        regime = str(sent[2] or 'NORMAL')

        long_score = 0
        short_score = 0
        reasons = []

        # DXY inverse signal
        if dxy_change < -0.3:
            long_score += 2
            reasons.append(f"DXY_weak:{dxy_change:.2f}%")
        elif dxy_change > 0.3:
            short_score += 2
            reasons.append(f"DXY_strong:{dxy_change:.2f}%")

        # Fear & Greed — low fear = safe haven demand
        if fear_greed < 40:
            long_score += 2
            reasons.append(f"fear:{fear_greed}")
        elif fear_greed > 70:
            short_score += 2
            reasons.append(f"greed:{fear_greed}")

        # Regime
        if regime == 'CRISIS':
            long_score += 2
            reasons.append("crisis_regime")

        # Price momentum
        if gld_change > 0.1:
            long_score += 1
            reasons.append(f"momentum:+{gld_change:.2f}%")
        elif gld_change < -0.1:
            short_score += 1
            reasons.append(f"momentum:{gld_change:.2f}%")

        # Decision
        if long_score >= 3 and long_score > short_score:
            conf = min(0.82, 0.55 + long_score * 0.05)
            return 'LONG', conf, ' | '.join(reasons)
        elif short_score >= 3 and short_score > long_score:
            conf = min(0.78, 0.55 + short_score * 0.05)
            return 'SHORT', conf, ' | '.join(reasons)
        else:
            return 'HOLD', 0.5, f"no_conviction(long:{long_score} short:{short_score})"

    except Exception as e:
        log.warning(f"GLD engine failed: {e}")
        return 'HOLD', 0.5, 'error'
