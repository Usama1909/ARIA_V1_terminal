import logging
log = logging.getLogger()

def bull_agent(symbol, signal, confidence, market_data, sentiment, nlp, causal, episodic):
    """Argues for entering the trade. Returns score 0-1."""
    score = 0.0
    reasons = []

    # Base signal strength
    if confidence >= 0.65:
        score += 0.3
        reasons.append(f"strong_signal({confidence:.2f})")
    elif confidence >= 0.55:
        score += 0.15
        reasons.append(f"moderate_signal({confidence:.2f})")

    # NLP supports
    nlp_score = nlp.get('score', 0)
    if signal == 'BUY' and nlp_score > 0.1:
        score += 0.2
        reasons.append(f"nlp_positive({nlp_score:+.2f})")
    elif signal == 'SELL' and nlp_score < -0.1:
        score += 0.2
        reasons.append(f"nlp_negative({nlp_score:+.2f})")

    # Episodic memory supports
    ep_wr = episodic.get('win_rate', None)
    if ep_wr and ep_wr >= 0.65:
        score += 0.2
        reasons.append(f"episodic_wr({ep_wr:.0%})")

    # Causal supports
    causal_net = causal.get('net_modifier', 0)
    if signal == 'BUY' and causal_net > 0.05:
        score += 0.15
        reasons.append(f"causal_supports({causal_net:+.2f})")
    elif signal == 'SELL' and causal_net < -0.05:
        score += 0.15
        reasons.append(f"causal_supports({causal_net:+.2f})")

    # Fear greed
    fg = sentiment.get('fear_greed', 50)
    if signal == 'BUY' and fg > 55:
        score += 0.1
        reasons.append("greed_momentum")
    elif signal == 'SELL' and fg < 30:
        score += 0.1
        reasons.append("fear_confirms_short")

    return min(1.0, score), reasons

def bear_agent(symbol, signal, confidence, market_data, sentiment, nlp, causal, episodic):
    """Argues against entering. Returns risk score 0-1."""
    score = 0.0
    reasons = []

    # Low confidence
    if confidence < 0.57:
        score += 0.3
        reasons.append(f"weak_signal({confidence:.2f})")

    # NLP opposes
    nlp_score = nlp.get('score', 0)
    if signal == 'BUY' and nlp_score < -0.1:
        score += 0.25
        reasons.append(f"nlp_negative({nlp_score:+.2f})")
    elif signal == 'SELL' and nlp_score > 0.1:
        score += 0.25
        reasons.append(f"nlp_positive({nlp_score:+.2f})")

    # FOMC risk
    fomc = nlp.get('fomc', 'NEUTRAL')
    if fomc == 'HAWKISH' and signal == 'BUY' and symbol in ['BTC','ETH','NVDA','TSLA']:
        score += 0.2
        reasons.append("fomc_hawkish_risk")

    # Poor episodic history
    ep_wr = episodic.get('win_rate', None)
    if ep_wr and ep_wr <= 0.40:
        score += 0.2
        reasons.append(f"poor_history({ep_wr:.0%})")

    # Crisis regime risk
    regime = sentiment.get('regime', 'NORMAL')
    if regime == 'CRISIS' and signal == 'BUY' and symbol != 'GLD':
        score += 0.15
        reasons.append("crisis_regime_risk")

    # Fragile liquidity
    liquidity = sentiment.get('liquidity', 'NORMAL')
    if liquidity == 'FRAGILE':
        score += 0.1
        reasons.append("fragile_liquidity")

    return min(1.0, score), reasons

def debate(symbol, signal, confidence, market_data, sentiment, nlp, causal, episodic):
    """
    Run bull vs bear debate.
    Returns verdict: APPROVE, REDUCE, or REJECT with size multiplier.
    """
    bull_score, bull_reasons = bull_agent(symbol, signal, confidence, market_data, sentiment, nlp, causal, episodic)
    bear_score, bear_reasons = bear_agent(symbol, signal, confidence, market_data, sentiment, nlp, causal, episodic)

    net = bull_score - bear_score

    if net >= 0.2:
        verdict = 'APPROVE'
        size_mult = 1.0
    elif net >= 0.0:
        verdict = 'REDUCE'
        size_mult = 0.5
    else:
        verdict = 'REJECT'
        size_mult = 0.0

    log.info(f"  {symbol} DEBATE: BULL:{bull_score:.2f} BEAR:{bear_score:.2f} net:{net:+.2f} → {verdict}")
    return {
        'verdict': verdict,
        'size_multiplier': size_mult,
        'bull_score': round(bull_score, 3),
        'bear_score': round(bear_score, 3),
        'bull_reasons': bull_reasons,
        'bear_reasons': bear_reasons
    }

if __name__ == "__main__":
    print("=== Debate Agent Test ===")
    mock_sentiment = {'fear_greed': 23, 'regime': 'CRISIS', 'liquidity': 'FRAGILE'}
    mock_nlp = {'score': -0.15, 'fomc': 'HAWKISH'}
    mock_causal = {'net_modifier': -0.16}
    mock_episodic = {'win_rate': 1.0}

    for symbol, signal, conf in [('GLD','BUY',0.78), ('BTC','BUY',0.54), ('NVDA','BUY',0.65), ('TSLA','SELL',0.68)]:
        result = debate(symbol, signal, conf, {}, mock_sentiment, mock_nlp, mock_causal, mock_episodic)
        print(f"{symbol} {signal}: {result['verdict']} (bull:{result['bull_score']} bear:{result['bear_score']})")
        print(f"  Bull: {result['bull_reasons']}")
        print(f"  Bear: {result['bear_reasons']}")
