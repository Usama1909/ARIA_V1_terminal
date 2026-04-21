journalctl -u aria_loop_v5.service -n 10 --no-pager | grep -i "deprecat\|model load\|AAPL\|error"
sed -n '65,70p' /root/agent_loop_v5.py
sed -i '67s/datetime.utcnow()/datetime.now()/' /root/agent_loop_v5.py
# Check for any remaining utcnow
grep -n "utcnow" /root/agent_loop_v5.py
sed -i 's/datetime.utcnow()/datetime.now()/g' /root/agent_loop_v5.py
grep -n "utcnow" /root/agent_loop_v5.py
systemctl restart aria_loop_v5.service
sleep 15
journalctl -u aria_loop_v5.service -n 5 --no-pager | grep -i "deprecat\|error\|failed"
git add agent_loop_v5.py aria_model_inference.py && git commit -m "fix: remove all utcnow deprecations, fix AAPL model path to temp_aria"
git push origin master && git push v1 master
grep -n "agent/reports\|agent_decisions" /root/main.py | head -10
sed -n '1229,1250p' /root/main.py
python3 << 'EOF'
with open('/root/main.py', 'r') as f:
    content = f.read()

old = '''@app.get("/agent/reports")
def get_agent_reports():
    return {"reports": _agent_reports[:50], "count": len(_agent_reports), "timestamp": datetime.now().isoformat()}'''

new = '''@app.get("/agent/reports")
def get_agent_reports():
    if not RAILWAY_DB_URL:
        try:
            conn = get_railway_db(); cur = conn.cursor()
            cur.execute("SELECT agent_id, symbol, action, confidence, reasoning, timestamp FROM agent_decisions ORDER BY timestamp DESC LIMIT 100")
            rows = cur.fetchall()
            cur.close(); conn.close()
            reports = [{'agent_id': r[0], 'symbol': r[1], 'action': r[2], 'confidence': float(r[3]) if r[3] else 0.5, 'reasoning': r[4], 'timestamp': r[5].isoformat(), 'agent_type': 'SPECIALIST'} for r in rows]
            return {"reports": reports, "count": len(reports), "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"reports": [], "count": 0, "error": str(e), "timestamp": datetime.now().isoformat()}
    return {"reports": _agent_reports[:50], "count": len(_agent_reports), "timestamp": datetime.now().isoformat()}'''

content = content.replace(old, new)
with open('/root/main.py', 'w') as f:
    f.write(content)
print("Done!")
EOF

python3 -c "import ast; ast.parse(open('/root/main.py').read()); print('Syntax OK')"
systemctl restart aria_frontend.service
sleep 5
curl -s http://localhost:8000/agent/reports | python3 -m json.tool | head -30
git add main.py && git commit -m "fix: agent reports read from local DB on Hetzner"
git push origin master && git push v1 master
pip install python-binance --break-system-packages
python3 -c "from binance.client import Client; print('Binance OK')"
cat /root/aria_market_updater.py
pip install websocket-client --break-system-packages
python3 -c "import websocket; print('WebSocket OK')"
systemctl restart aria_market.service
sleep 5
journalctl -u aria_market.service -n 20 --no-pager
cat > /root/aria_market_updater.py << 'ENDOFFILE'
#!/usr/bin/env python3
"""
ARIA Market Data Updater v2
- Binance MAINNET WebSocket real-time crypto
- Yahoo Finance for stocks
- Funding rates for BTC/ETH
- Crypto updates real-time, stocks every 60s
"""
import time, psycopg2, logging, requests, threading, json
from datetime import datetime
logging.basicConfig(level=logging.INFO, format='%(asctime)s [MARKET] %(message)s')
log = logging.getLogger()
DB = {'host':'localhost','port':5432,'dbname':'aria_db','user':'postgres','password':'aria_secure_2026'}
BINANCE_API = "https://api.binance.com/api"
BINANCE_FAPI = "https://fapi.binance.com/fapi"
CRYPTO = ['BTC', 'ETH']
STOCKS = ['AAPL', 'NVDA', 'TSLA', 'GLD']
_ws_prices = {}

def get_funding_rate(symbol):
    try:
        r = requests.get(f"{BINANCE_FAPI}/v1/premiumIndex", params={'symbol': f'{symbol}USDT'}, timeout=5)
        d = r.json()
        return float(d.get('lastFundingRate', 0)) * 100
    except:
        return 0.0

def get_stock_price(symbol):
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        fi = t.fast_info
        price = float(fi.get('last_price') or fi.get('previousClose') or 0)
        prev = float(fi.get('previous_close') or fi.get('regularMarketPreviousClose') or 0)
        if price > 0 and prev > 0:
            return price, round(((price - prev) / prev) * 100, 4)
    except:
        pass
    try:
        import yfinance as yf
        hist = yf.Ticker(symbol).history(period='2d')
        if len(hist) >= 2:
            price = float(hist['Close'].iloc[-1])
            prev = float(hist['Close'].iloc[-2])
            return price, round(((price - prev) / prev * 100) if prev > 0 else 0.0, 4)
        elif len(hist) == 1:
            return float(hist['Close'].iloc[-1]), 0.0
    except:
        pass
    return 0.0, 0.0

def get_dxy():
    try:
        import yfinance as yf
        hist = yf.Ticker('DX-Y.NYB').history(period='2d')
        if len(hist) >= 2:
            price = float(hist['Close'].iloc[-1])
            prev = float(hist['Close'].iloc[-2])
            return price, round(((price - prev) / prev * 100) if prev > 0 else 0.0, 4)
        elif len(hist) == 1:
            return float(hist['Close'].iloc[-1]), 0.0
    except Exception as e:
        log.warning(f"DXY fetch failed: {e}")
    return 0.0, 0.0

def write_market_state(symbol, price, change, signal):
    try:
        conn = psycopg2.connect(**DB); cur = conn.cursor()
        cur.execute("DELETE FROM market_state_latest WHERE symbol=%s", [symbol])
        cur.execute("INSERT INTO market_state_latest (symbol, price, change_24h, signal, updated_at) VALUES (%s,%s,%s,%s,NOW())", [symbol, price, change, signal])
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.error(f"DB write failed {symbol}: {e}")

def write_price_data(symbol, price, change):
    try:
        conn = psycopg2.connect(**DB); cur = conn.cursor()
        cur.execute("INSERT INTO price_data (symbol, price, volume, source) VALUES (%s,%s,%s,%s)", [symbol, price, 0, 'binance_mainnet'])
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.warning(f"write_price_data failed {symbol}: {e}")

def binance_websocket_thread():
    import websocket
    ws_url = "wss://stream.binance.com:9443/ws/btcusdt@ticker/ethusdt@ticker"
    def on_message(ws, message):
        try:
            d = json.loads(message)
            symbol = d.get('s', '').replace('USDT', '')
            if symbol in CRYPTO:
                price = float(d.get('c', 0))
                change = float(d.get('P', 0))
                _ws_prices[symbol] = {'price': price, 'change': change, 'ts': time.time()}
                write_market_state(symbol, price, change, 'HOLD')
                write_price_data(symbol, price, change)
                log.info(f"WS {symbol}: ${price:.2f} ({change:+.2f}%)")
        except Exception as e:
            log.warning(f"WS message error: {e}")
    def on_error(ws, error):
        log.error(f"WebSocket error: {error}")
    def on_close(ws, close_status_code, close_msg):
        log.warning("WebSocket closed — reconnecting in 5s")
        time.sleep(5)
    def on_open(ws):
        log.info("Binance WebSocket connected — real-time BTC/ETH active")
    while True:
        try:
            ws = websocket.WebSocketApp(ws_url, on_message=on_message, on_error=on_error, on_close=on_close, on_open=on_open)
            ws.run_forever()
        except Exception as e:
            log.error(f"WebSocket thread error: {e}")
        time.sleep(10)

def main():
    log.info("ARIA Market Updater v2 — Binance mainnet WebSocket + Yahoo Finance")
    ws_thread = threading.Thread(target=binance_websocket_thread, daemon=True)
    ws_thread.start()
    log.info("Binance WebSocket thread started")
    stock_timer = 0
    while True:
        if stock_timer <= 0:
            for symbol in STOCKS:
                try:
                    price, change = get_stock_price(symbol)
                    if price > 0:
                        write_market_state(symbol, price, change, 'HOLD')
                        log.info(f"{symbol}: ${price:.2f} ({change:+.2f}%)")
                except Exception as e:
                    log.error(f"{symbol}: {e}")
            try:
                dxy_price, dxy_change = get_dxy()
                if dxy_price > 0:
                    write_market_state('DXY', dxy_price, dxy_change, 'HOLD')
                    write_price_data('DXY', dxy_price, dxy_change)
                    log.info(f"DXY: {dxy_price:.2f} ({dxy_change:+.2f}%)")
            except Exception as e:
                log.error(f"DXY: {e}")
            for symbol in CRYPTO:
                try:
                    fr = get_funding_rate(symbol)
                    if fr != 0:
                        log.info(f"{symbol} funding rate: {fr:.4f}%")
                except Exception as e:
                    log.warning(f"Funding rate {symbol}: {e}")
            stock_timer = 60
        stock_timer -= 5
        time.sleep(5)

if __name__ == '__main__':
    main()
ENDOFFILE

python3 -c "import ast; ast.parse(open('/root/aria_market_updater.py').read()); print('Syntax OK')"
systemctl restart aria_market.service
sleep 5
journalctl -u aria_market.service -n 20 --no-pager
git add aria_market_updater.py && git commit -m "feat: Binance mainnet WebSocket real-time BTC/ETH + funding rates"
git push origin master && git push v1 master
cat > /root/README.md << 'EOF'
# ARIA — Autonomous Reasoning & Intelligence Architecture

> A live, self-improving multi-asset trading system built on ensemble ML, autonomous agent swarms, and institutional-grade risk management.

## 🔴 Live Performance (Updated: April 20, 2026)

| Metric | Value |
|--------|-------|
| Portfolio Value | $14,577 |
| Total Return | +45.76% |
| Win Rate | 95.0% |
| Closed Trades | 933 |
| Open Positions | 4 |
| Agent Cycles | 1,852+ |
| Pattern Library | 76,141 patterns |

## 🖥️ Live Terminals
- **Product:** http://65.108.217.183/terminal
- **Dissertation:** https://web-production-548c0.up.railway.app/terminal

## 🏗️ Architecture
## 🧠 13-Capability Intelligence Blueprint

| Cap | Name | Status |
|-----|------|--------|
| 1 | NLP / FinBERT / FOMC / Reddit | ✅ Live |
| 2 | Causal Graph | ✅ Live |
| 3 | Episodic Memory | ✅ Live |
| 4 | Uncertainty / OOD Detection | ✅ Live |
| 5 | Cross-Asset Signal Chains | ✅ Live |
| 6 | Multi-Agent Debate | ✅ Live |
| 7 | Adversarial Self-Test | ✅ Live |
| 8 | Hypothesis Engine | ✅ Live |
| 9 | Self-Improvement Loop | ✅ Live |
| 10 | Order Book Microstructure (VPIN) | ✅ Live |
| 11 | Narrative Engine | ✅ Live |
| 12 | Regime Memory | ✅ Live |
| 13 | DRL VWAP Execution Agent | 🔄 Building |

## 📊 Technical Stack

- **ML:** XGBoost + Random Forest + Neural Network ensemble (27 features)
- **Risk:** EVT/GPD, Kupiec+Christoffersen backtests, Student-t Monte Carlo
- **Data:** Binance WebSocket (real-time), Yahoo Finance, FRED macro, Reddit NLP
- **Execution:** Kelly Criterion regime-adjusted position sizing
- **Backend:** FastAPI + PostgreSQL + WebSocket
- **Infrastructure:** Hetzner CPX32 + Railway + GitHub Actions

## 🎯 Core Finding

Multi-asset ensemble training achieves **78.3% accuracy** vs **41.8% single-asset baseline** — a 36.5 percentage point improvement validated across 6 asset classes using 2 years of historical data and walk-forward methodology.

## 📁 Repository Structure
## 🚀 Roadmap (45-Day Plan)

- [x] Multi-asset ensemble (78.3% accuracy)
- [x] Binance WebSocket real-time data
- [x] WebSocket live terminal broadcasts
- [x] 933 closed trades, 95% win rate
- [ ] Alpaca real-time stock data
- [ ] SEC EDGAR earnings signals
- [ ] Options flow signals
- [ ] Real broker connection
- [ ] 1000+ signal pipeline

## 📚 Academic Context

MSc Data Analytics — De Montfort University 2026
Supervisor: Dr. Usama Mannai | Module: CSIP5501_2025_631

---
*"No one made more money in trading than Jim Simons. He proved that data, math, and disciplined models can outperform even the best human intuition."*

*ARIA is built on the same principle.*
EOF

echo "Done!"
git add README.md && git commit -m "docs: professional README with live performance metrics and architecture"
git push origin master && git push v1 master
pip install alpaca-trade-api --break-system-packages
python3 -c "import alpaca_trade_api; print('Alpaca OK')"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "\d market_state_latest"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "ALTER TABLE market_state_latest ADD COLUMN IF NOT EXISTS funding_rate FLOAT DEFAULT 0.0;"
python3 << 'EOF'
with open('/root/aria_market_updater.py', 'r') as f:
    content = f.read()

# Update write_market_state to include funding_rate
old = '''def write_market_state(symbol, price, change, signal):
    try:
        conn = psycopg2.connect(**DB); cur = conn.cursor()
        cur.execute("DELETE FROM market_state_latest WHERE symbol=%s", [symbol])
        cur.execute("INSERT INTO market_state_latest (symbol, price, change_24h, signal, updated_at) VALUES (%s,%s,%s,%s,NOW())", [symbol, price, change, signal])
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.error(f"DB write failed {symbol}: {e}")'''

new = '''def write_market_state(symbol, price, change, signal, funding_rate=0.0):
    try:
        conn = psycopg2.connect(**DB); cur = conn.cursor()
        cur.execute("DELETE FROM market_state_latest WHERE symbol=%s", [symbol])
        cur.execute("INSERT INTO market_state_latest (symbol, price, change_24h, signal, funding_rate, updated_at) VALUES (%s,%s,%s,%s,%s,NOW())", [symbol, price, change, signal, funding_rate])
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.error(f"DB write failed {symbol}: {e}")'''

content = content.replace(old, new)

# Update funding rate collection to store in DB
old = '''            for symbol in CRYPTO:
                try:
                    fr = get_funding_rate(symbol)
                    if fr != 0:
                        log.info(f"{symbol} funding rate: {fr:.4f}%")
                except Exception as e:
                    log.warning(f"Funding rate {symbol}: {e}")'''

new = '''            for symbol in CRYPTO:
                try:
                    fr = get_funding_rate(symbol)
                    if fr != 0:
                        # Update funding rate in DB
                        conn = psycopg2.connect(**DB); cur = conn.cursor()
                        cur.execute("UPDATE market_state_latest SET funding_rate=%s WHERE symbol=%s", [fr, symbol])
                        conn.commit(); cur.close(); conn.close()
                        log.info(f"{symbol} funding rate: {fr:.4f}%")
                except Exception as e:
                    log.warning(f"Funding rate {symbol}: {e}")'''

content = content.replace(old, new)

with open('/root/aria_market_updater.py', 'w') as f:
    f.write(content)
print("Done!")
EOF

python3 -c "import ast; ast.parse(open('/root/aria_market_updater.py').read()); print('Syntax OK')"
grep -n "funding\|market_state_latest\|change_24h" /root/agent_loop_v5.py | head -20
python3 << 'EOF'
with open('/root/agent_loop_v5.py', 'r') as f:
    content = f.read()

# Update market read to include funding_rate
old = '''        cur.execute("SELECT symbol,price,change_24h,updated_at FROM market_state_latest")'''
new = '''        cur.execute("SELECT symbol,price,change_24h,updated_at,funding_rate FROM market_state_latest")'''
content = content.replace(old, new)

# Update market dict to include funding_rate
old = '''            market[row[0]]={'price':float(row[1]),'change_24h':float(row[2]),'age_seconds':age,'stale':age>STALE_MARKET}'''
new = '''            market[row[0]]={'price':float(row[1]),'change_24h':float(row[2]),'age_seconds':age,'stale':age>STALE_MARKET,'funding_rate':float(row[4]) if row[4] else 0.0}'''
content = content.replace(old, new)

with open('/root/agent_loop_v5.py', 'w') as f:
    f.write(content)
print("Done!")
EOF

python3 -c "import ast; ast.parse(open('/root/agent_loop_v5.py').read()); print('Syntax OK')"
grep -n "confidence\|conf\|Kelly\|signal_strength" /root/agent_loop_v5.py | grep -i "def\|=.*conf\|conf.*=" | head -20
sed -n '285,340p' /root/agent_loop_v5.py
sed -n '340,420p' /root/agent_loop_v5.py
python3 << 'EOF'
with open('/root/agent_loop_v5.py', 'r') as f:
    content = f.read()

funding_signal = '''
    # ── Step 5: Funding Rate Signal (Crypto only) ────────
    if symbol in ['BTC', 'ETH']:
        try:
            funding_rate = market_data.get(symbol, {}).get('funding_rate', 0.0)
            if funding_rate < -0.01:
                # Very negative funding = shorts overleveraged = squeeze likely = boost LONG
                if final_dir == 'LONG':
                    final_conf = min(0.92, final_conf + 0.04)
                    log.info(f"  {symbol} FUNDING BOOST: rate:{funding_rate:.4f}% (short squeeze likely) → conf:{final_conf:.3f}")
                elif final_dir == 'SHORT':
                    final_conf = max(0.45, final_conf - 0.04)
                    log.info(f"  {symbol} FUNDING DRAG: rate:{funding_rate:.4f}% (short squeeze risk) → conf:{final_conf:.3f}")
            elif funding_rate > 0.01:
                # Very positive funding = longs overleveraged = dump likely = boost SHORT
                if final_dir == 'SHORT':
                    final_conf = min(0.92, final_conf + 0.04)
                    log.info(f"  {symbol} FUNDING BOOST: rate:{funding_rate:.4f}% (long squeeze likely) → conf:{final_conf:.3f}")
                elif final_dir == 'LONG':
                    final_conf = max(0.45, final_conf - 0.04)
                    log.info(f"  {symbol} FUNDING DRAG: rate:{funding_rate:.4f}% (long squeeze risk) → conf:{final_conf:.3f}")
        except Exception as e:
            log.warning(f"Funding rate signal failed {symbol}: {e}")

'''

# Insert after NLP modifier block
old = '    # ── Step 12: Regime memory modifier ────────────────────'
new = funding_signal + '    # ── Step 12: Regime memory modifier ────────────────────'
content = content.replace(old, new)

with open('/root/agent_loop_v5.py', 'w') as f:
    f.write(content)
print("Done!")
EOF

python3 -c "import ast; ast.parse(open('/root/agent_loop_v5.py').read()); print('Syntax OK')"
systemctl restart aria_market.service aria_loop_v5.service
sleep 20
journalctl -u aria_loop_v5.service -n 20 --no-pager | grep -i "funding\|BTC\|ETH"
sleep 60 && journalctl -u aria_loop_v5.service -n 30 --no-pager | grep -i "funding\|BTC\|ETH"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT symbol, price, change_24h, funding_rate, updated_at FROM market_state_latest WHERE symbol IN ('BTC','ETH');"
python3 << 'EOF'
with open('/root/aria_market_updater.py', 'r') as f:
    content = f.read()

# Store funding rates in memory and include in WebSocket write
old = '''_ws_prices = {}

def get_funding_rate(symbol):'''
new = '''_ws_prices = {}
_funding_rates = {}

def get_funding_rate(symbol):'''
content = content.replace(old, new)

# Update funding rate collection to store in memory first
old = '''            for symbol in CRYPTO:
                try:
                    fr = get_funding_rate(symbol)
                    if fr != 0:
                        # Update funding rate in DB
                        conn = psycopg2.connect(**DB); cur = conn.cursor()
                        cur.execute("UPDATE market_state_latest SET funding_rate=%s WHERE symbol=%s", [fr, symbol])
                        conn.commit(); cur.close(); conn.close()
                        log.info(f"{symbol} funding rate: {fr:.4f}%")
                except Exception as e:
                    log.warning(f"Funding rate {symbol}: {e}")'''
new = '''            for symbol in CRYPTO:
                try:
                    fr = get_funding_rate(symbol)
                    if fr != 0:
                        _funding_rates[symbol] = fr
                        conn = psycopg2.connect(**DB); cur = conn.cursor()
                        cur.execute("UPDATE market_state_latest SET funding_rate=%s WHERE symbol=%s", [fr, symbol])
                        conn.commit(); cur.close(); conn.close()
                        log.info(f"{symbol} funding rate: {fr:.4f}%")
                except Exception as e:
                    log.warning(f"Funding rate {symbol}: {e}")'''
content = content.replace(old, new)

# Include funding rate in WebSocket write
old = '''                _ws_prices[symbol] = {'price': price, 'change': change, 'ts': time.time()}
                write_market_state(symbol, price, change, 'HOLD')'''
new = '''                _ws_prices[symbol] = {'price': price, 'change': change, 'ts': time.time()}
                fr = _funding_rates.get(symbol, 0.0)
                write_market_state(symbol, price, change, 'HOLD', fr)'''
content = content.replace(old, new)

with open('/root/aria_market_updater.py', 'w') as f:
    f.write(content)
print("Done!")
EOF

python3 -c "import ast; ast.parse(open('/root/aria_market_updater.py').read()); print('Syntax OK')"
grep -n "_funding_rates" /root/aria_market_updater.py
systemctl restart aria_market.service
sleep 70
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT symbol, price, funding_rate, updated_at FROM market_state_latest WHERE symbol IN ('BTC','ETH');"
git push origin master && git push v1 master
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT COUNT(*) FROM pattern_library;"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT COUNT(*) FROM closed_trades;"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT outcome, COUNT(*), ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl FROM closed_trades GROUP BY outcome;"

tail -5 /var/log/aria_db_sync.log
journalctl -u aria_loop_v5.service -n 5 --no-pager
curl -s http://localhost:8000/live/portfolio | python3 -m json.tool
curl -s "https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT" | python3 -m json.tool
curl -s "https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=5m&limit=5" | python3 -m json.tool
curl -s "https://fapi.binance.com/futures/data/openInterestHist?symbol=ETHUSD T&period=5m&limit=5" | python3 -m json.tool
curl -s "https://fapi.binance.com/futures/data/openInterestHist?symbol=ETHUSDT&period=5m&limit=5" | python3 -m json.tool
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "
CREATE TABLE IF NOT EXISTS crypto_signals (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10),
    open_interest FLOAT,
    oi_change_pct FLOAT,
    funding_rate FLOAT,
    long_short_ratio FLOAT,
    signal VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);"
python3 << 'EOF'
with open('/root/aria_market_updater.py', 'r') as f:
    content = f.read()

oi_code = '''
def get_open_interest_signal(symbol):
    """
    Returns OI signal: BULLISH, BEARISH, SQUEEZE, or NEUTRAL
    Rising OI + Rising Price = BULLISH
    Rising OI + Falling Price = BEARISH  
    Falling OI + Rising Price = SQUEEZE (short squeeze)
    Falling OI + Falling Price = WEAK
    """
    try:
        r = requests.get(f"{BINANCE_FAPI}/futures/data/openInterestHist",
                        params={'symbol': f'{symbol}USDT', 'period': '5m', 'limit': 3}, timeout=5)
        data = r.json()
        if len(data) < 2:
            return 'NEUTRAL', 0.0
        oi_latest = float(data[-1]['sumOpenInterest'])
        oi_prev = float(data[-2]['sumOpenInterest'])
        oi_change_pct = ((oi_latest - oi_prev) / oi_prev) * 100
        # Store in DB
        conn = psycopg2.connect(**DB); cur = conn.cursor()
        cur.execute("INSERT INTO crypto_signals (symbol, open_interest, oi_change_pct, funding_rate) VALUES (%s,%s,%s,%s)",
                   [symbol, oi_latest, oi_change_pct, _funding_rates.get(symbol, 0.0)])
        conn.commit(); cur.close(); conn.close()
        return oi_change_pct
    except Exception as e:
        log.warning(f"OI signal failed {symbol}: {e}")
        return 0.0

'''

old = 'def get_funding_rate(symbol):'
new = oi_code + 'def get_funding_rate(symbol):'
content = content.replace(old, new)

# Add OI collection in the stock timer loop
old = '''            for symbol in CRYPTO:
                try:
                    fr = get_funding_rate(symbol)'''
new = '''            for symbol in CRYPTO:
                try:
                    oi_change = get_open_interest_signal(symbol)
                    log.info(f"{symbol} OI change: {oi_change:.4f}%")
                except Exception as e:
                    log.warning(f"OI {symbol}: {e}")
            for symbol in CRYPTO:
                try:
                    fr = get_funding_rate(symbol)'''
content = content.replace(old, new)

with open('/root/aria_market_updater.py', 'w') as f:
    f.write(content)
print("Done!")
EOF

python3 -c "import ast; ast.parse(open('/root/aria_market_updater.py').read()); print('Syntax OK')"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "ALTER TABLE market_state_latest ADD COLUMN IF NOT EXISTS oi_change_pct FLOAT DEFAULT 0.0;"
python3 << 'EOF'
with open('/root/aria_market_updater.py', 'r') as f:
    content = f.read()

# Update write_market_state to include oi_change_pct
old = '''def write_market_state(symbol, price, change, signal, funding_rate=0.0):
    try:
        conn = psycopg2.connect(**DB); cur = conn.cursor()
        cur.execute("DELETE FROM market_state_latest WHERE symbol=%s", [symbol])
        cur.execute("INSERT INTO market_state_latest (symbol, price, change_24h, signal, funding_rate, updated_at) VALUES (%s,%s,%s,%s,%s,NOW())", [symbol, price, change, signal, funding_rate])
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.error(f"DB write failed {symbol}: {e}")'''

new = '''def write_market_state(symbol, price, change, signal, funding_rate=0.0, oi_change_pct=0.0):
    try:
        conn = psycopg2.connect(**DB); cur = conn.cursor()
        cur.execute("DELETE FROM market_state_latest WHERE symbol=%s", [symbol])
        cur.execute("INSERT INTO market_state_latest (symbol, price, change_24h, signal, funding_rate, oi_change_pct, updated_at) VALUES (%s,%s,%s,%s,%s,%s,NOW())", [symbol, price, change, signal, funding_rate, oi_change_pct])
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.error(f"DB write failed {symbol}: {e}")'''

content = content.replace(old, new)

# Store OI in memory and pass to write
old = '''_ws_prices = {}
_funding_rates = {}'''
new = '''_ws_prices = {}
_funding_rates = {}
_oi_changes = {}'''
content = content.replace(old, new)

# Store OI change in memory
old = '''                try:
                    oi_change = get_open_interest_signal(symbol)
                    log.info(f"{symbol} OI change: {oi_change:.4f}%")
                except Exception as e:
                    log.warning(f"OI {symbol}: {e}")'''
new = '''                try:
                    oi_change = get_open_interest_signal(symbol)
                    _oi_changes[symbol] = oi_change
                    log.info(f"{symbol} OI change: {oi_change:.4f}%")
                except Exception as e:
                    log.warning(f"OI {symbol}: {e}")'''
content = content.replace(old, new)

# Include OI in WebSocket write
old = '''                fr = _funding_rates.get(symbol, 0.0)
                write_market_state(symbol, price, change, 'HOLD', fr)'''
new = '''                fr = _funding_rates.get(symbol, 0.0)
                oi = _oi_changes.get(symbol, 0.0)
                write_market_state(symbol, price, change, 'HOLD', fr, oi)'''
content = content.replace(old, new)

with open('/root/aria_market_updater.py', 'w') as f:
    f.write(content)
print("Done!")
EOF

python3 -c "import ast; ast.parse(open('/root/aria_market_updater.py').read()); print('Syntax OK')"
python3 << 'EOF'
with open('/root/agent_loop_v5.py', 'r') as f:
    content = f.read()

# Read OI from market state
old = "            market[row[0]]={'price':float(row[1]),'change_24h':float(row[2]),'age_seconds':age,'stale':age>STALE_MARKET,'funding_rate':float(row[4]) if row[4] else 0.0}"
new = "            market[row[0]]={'price':float(row[1]),'change_24h':float(row[2]),'age_seconds':age,'stale':age>STALE_MARKET,'funding_rate':float(row[4]) if row[4] else 0.0,'oi_change_pct':float(row[5]) if len(row)>5 and row[5] else 0.0}"
content = content.replace(old, new)

# Update SELECT to include oi_change_pct
old = '        cur.execute("SELECT symbol,price,change_24h,updated_at,funding_rate FROM market_state_latest")'
new = '        cur.execute("SELECT symbol,price,change_24h,updated_at,funding_rate,oi_change_pct FROM market_state_latest")'
content = content.replace(old, new)

# Add OI signal after funding rate signal
old = '    # ── Step 12: Regime memory modifier ────────────────────'
new = '''    # ── Step 6: Open Interest Signal (Crypto only) ──────────
    if symbol in ['BTC', 'ETH']:
        try:
            oi_change = market_data.get(symbol, {}).get('oi_change_pct', 0.0)
            price_change = market_data.get(symbol, {}).get('change_24h', 0.0)
            if oi_change > 0.05 and price_change > 0:
                # Rising OI + Rising Price = BULLISH
                if final_dir == 'LONG':
                    final_conf = min(0.92, final_conf + 0.05)
                    log.info(f"  {symbol} OI BULLISH: oi:{oi_change:.3f}% price:{price_change:.2f}% → conf:{final_conf:.3f}")
                elif final_dir == 'SHORT':
                    final_conf = max(0.45, final_conf - 0.05)
                    log.info(f"  {symbol} OI BEARISH for SHORT: oi:{oi_change:.3f}% → conf:{final_conf:.3f}")
            elif oi_change < -0.05 and price_change > 0:
                # Falling OI + Rising Price = SHORT SQUEEZE — avoid shorting
                if final_dir == 'SHORT':
                    final_conf = max(0.45, final_conf - 0.08)
                    log.info(f"  {symbol} OI SQUEEZE WARNING: oi:{oi_change:.3f}% price up → conf:{final_conf:.3f}")
            elif oi_change > 0.05 and price_change < 0:
                # Rising OI + Falling Price = BEARISH
                if final_dir == 'SHORT':
                    final_conf = min(0.92, final_conf + 0.05)
                    log.info(f"  {symbol} OI BEARISH CONFIRMED: oi:{oi_change:.3f}% price down → conf:{final_conf:.3f}")
        except Exception as e:
            log.warning(f"OI signal failed {symbol}: {e}")

    # ── Step 12: Regime memory modifier ────────────────────'''
content = content.replace(old, new)

with open('/root/agent_loop_v5.py', 'w') as f:
    f.write(content)
print("Done!")
EOF

python3 -c "import ast; ast.parse(open('/root/agent_loop_v5.py').read()); print('Syntax OK')"
# Check aria_market_updater.py
echo "=== MARKET UPDATER CHECKS ==="
grep -n "_oi_changes" /root/aria_market_updater.py
grep -n "oi_change_pct" /root/aria_market_updater.py
grep -n "get_open_interest_signal" /root/aria_market_updater.py
echo "=== AGENT LOOP CHECKS ==="
grep -n "oi_change_pct" /root/agent_loop_v5.py
grep -n "OI BULLISH\|OI BEARISH\|OI SQUEEZE" /root/agent_loop_v5.py
grep -n "Step 6" /root/agent_loop_v5.py
grep -n "── Step" /root/agent_loop_v5.py
systemctl restart aria_market.service aria_loop_v5.service
sleep 10
journalctl -u aria_market.service -n 15 --no-pager | grep -i "OI\|funding\|BTC\|ETH"
sleep 60 && journalctl -u aria_market.service -n 10 --no-pager | grep -i "OI\|funding"
journalctl -u aria_market.service -n 30 --no-pager | tail -20
# Test the correct URL
curl -s "https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=5m&limit=3" | python3 -m json.tool | head -10
python3 << 'EOF'
with open('/root/aria_market_updater.py', 'r') as f:
    content = f.read()

old = '''        r = requests.get(f"{BINANCE_FAPI}/futures/data/openInterestHist",
                        params={'symbol': f'{symbol}USDT', 'period': '5m', 'limit': 3}, timeout=5)'''
new = '''        r = requests.get("https://fapi.binance.com/futures/data/openInterestHist",
                        params={'symbol': f'{symbol}USDT', 'period': '5m', 'limit': 3}, timeout=5)'''

content = content.replace(old, new)
with open('/root/aria_market_updater.py', 'w') as f:
    f.write(content)
print("Done!")
EOF

python3 -c "import ast; ast.parse(open('/root/aria_market_updater.py').read()); print('Syntax OK')"
grep -n "openInterestHist\|BINANCE_FAPI" /root/aria_market_updater.py
systemctl restart aria_market.service
sleep 65
journalctl -u aria_market.service -n 10 --no-pager | grep -i "OI\|funding"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT symbol, price, funding_rate, oi_change_pct, updated_at FROM market_state_latest WHERE symbol IN ('BTC','ETH');"
systemctl list-units | grep aria | grep -v "dead\|failed"
git add agent_loop_v5.py aria_market_updater.py && git commit -m "feat: OI signal + funding rate wired into agent loop - BTC/ETH intelligence upgrade"
git push origin master && git push v1 master
# Check all original core files exist
ls -la /root/aria_model_inference.py        /root/aria_regime_memory.py        /root/aria_episodic_memory.py        /root/aria_hypothesis.py        /root/aria_causal_graph.py        /root/aria_adversarial.py        /root/aria_cross_asset.py        /root/aria_debate.py        /root/aria_microstructure.py        /root/aria_narrative.py        /root/aria_ood_detector.py        /root/aria_self_improvement.py        /root/retrain_models.py 2>/dev/null
ls -la /root/temp_aria/*.pkl 2>/dev/null | head -20
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT COUNT(*) FROM market_data_raw;"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;"
# Check data collection services
journalctl -u aria_sentiment.service -n 5 --no-pager
journalctl -u aria_nlp.service -n 5 --no-pager
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT COUNT(*) FROM price_data;"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT COUNT(*) FROM nlp_sentiment;"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT COUNT(*) FROM sentiment_latest;"
grep -n "newsapi\|NewsAPI\|news_api" /root/aria_nlp_service.py | head -10
journalctl -u aria_loop_v5.service -n 30 --no-pager | grep -i "OI\|funding\|BTC\|ETH" | head -20
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT mode, score, updated_at FROM system_health ORDER BY id DESC LIMIT 5;"
grep -n "DEGRADED\|score\|system_health" /root/aria_anomaly_detector.py | head -20
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT details FROM system_health ORDER BY id DESC LIMIT 1;" | python3 -m json.tool 2>/dev/null || psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT details FROM system_health ORDER BY id DESC LIMIT 1;"
grep -n "threshold\|stale\|STALE\|market_stale" /root/aria_anomaly_detector.py | head -20
grep -n "market_state.*300\|market_state.*threshold" /root/aria_anomaly_detector.py | head -10
sed -n '108,120p' /root/aria_anomaly_detector.py
sed -n '25,35p' /root/aria_anomaly_detector.py
python3 << 'EOF'
with open('/root/aria_anomaly_detector.py', 'r') as f:
    content = f.read()

old = """    'market_state': {
        'BTC':  120,   # 2 mins — crypto updates every 60s
        'ETH':  120,
        'AAPL': 300,   # 5 mins — stocks
        'NVDA': 300,
        'TSLA': 300,
        'GLD':  300,"""

new = """    'market_state': {
        'BTC':  120,   # 2 mins — crypto updates every 60s
        'ETH':  120,
        'AAPL': 28800,  # 8 hours — stocks only update during market hours
        'NVDA': 28800,
        'TSLA': 28800,
        'GLD':  28800,"""

content = content.replace(old, new)
with open('/root/aria_anomaly_detector.py', 'w') as f:
    f.write(content)
print("Done!")
EOF

python3 -c "import ast; ast.parse(open('/root/aria_anomaly_detector.py').read()); print('Syntax OK')"
systemctl restart aria_anomaly.service
sleep 15
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT mode, score, updated_at FROM system_health ORDER BY id DESC LIMIT 3;"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT details FROM system_health ORDER BY id DESC LIMIT 1;" | head -5
sed -n '35,45p' /root/aria_anomaly_detector.py
sed -i "s/'DXY':  600,   # 10 mins — macro/'DXY':  28800, # 8 hours — macro index/" /root/aria_anomaly_detector.py
grep -n "DXY" /root/aria_anomaly_detector.py
sed -i "47s/'DXY':  600,/'DXY':  28800,/" /root/aria_anomaly_detector.py
grep -n "DXY" /root/aria_anomaly_detector.py
systemctl restart aria_anomaly.service
sleep 15
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT mode, score, updated_at FROM system_health ORDER BY id DESC LIMIT 3;"
git add aria_anomaly_detector.py aria_market_updater.py agent_loop_v5.py && git commit -m "fix: health thresholds for market hours, OI signal live, funding rates in DB"
git push origin master && git push v1 master
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT symbol, direction, entry_price, size_usd FROM positions_live WHERE status='OPEN';"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT symbol, price, change_24h, funding_rate, oi_change_pct FROM market_state_latest WHERE symbol IN ('BTC','ETH');"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" << 'EOF'
BEGIN;

-- Close BTC SHORT (losing trade)
INSERT INTO closed_trades (symbol, direction, entry_price, exit_price, pnl_usd, pnl_pct, size_usd, outcome, hold_cycles, signal_id)
SELECT 'BTC', 'SHORT', 74760.44, 75860.42, 
       ((74760.44 - 75860.42) / 74760.44) * 50,
       ((74760.44 - 75860.42) / 74760.44) * 100,
       50, 'LOSS', 10, 'manual_close_signal_upgrade';

-- Close ETH SHORT (losing trade)
INSERT INTO closed_trades (symbol, direction, entry_price, exit_price, pnl_usd, pnl_pct, size_usd, outcome, hold_cycles, signal_id)
SELECT 'ETH', 'SHORT', 2261.16, 2300.18,
       ((2261.16 - 2300.18) / 2261.16) * 247.25,
       ((2261.16 - 2300.18) / 2261.16) * 100,
       247.25, 'LOSS', 10, 'manual_close_signal_upgrade';

-- Remove from positions
EOF

psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT symbol, direction FROM positions_live WHERE status='OPEN';"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "DELETE FROM positions_live WHERE symbol IN ('BTC', 'ETH');"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT symbol, direction FROM positions_live WHERE status='OPEN';"
sleep 60 && journalctl -u aria_loop_v5.service -n 20 --no-pager | grep -i "BTC\|ETH\|LONG\|SHORT\|open\|decision"
:
systemctl restart aria_loop_v5.service
sleep 15
journalctl -u aria_loop_v5.service -n 10 --no-pager | grep -i "restored\|open\|portfolio"
journalctl -u aria_loop_v5.service -n 20 --no-pager | grep -i "restored\|positions\|startup"
journalctl -u aria_loop_v5.service -n 30 --no-pager | head -20
grep -n "open_positions\|restore\|load.*position\|positions_live" /root/agent_loop_v5.py | head -20
sed -n '598,632p' /root/agent_loop_v5.py
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT symbol, side, direction, status FROM orders_outbox WHERE status='EXECUTED' ORDER BY created_at DESC LIMIT 10;"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "UPDATE orders_outbox SET status='CLOSED' WHERE symbol IN ('BTC','ETH') AND status='EXECUTED';"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT symbol, direction, status FROM orders_outbox WHERE symbol IN ('BTC','ETH');"
systemctl restart aria_loop_v5.service
sleep 15
journalctl -u aria_loop_v5.service -n 10 --no-pager | grep -i "restored\|open\|cycle 1"
sed -n '601,615p' /root/agent_loop_v5.py
python3 << 'EOF'
with open('/root/agent_loop_v5.py', 'r') as f:
    content = f.read()

old = '''    open_positions={}
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
        log.info(f"Restored {len(open_positions)} open positions: {list(open_positions.keys())}")'''

new = '''    open_positions={}
    try:
        conn=get_db(); cur=conn.cursor()
        # Single source of truth — always restore from positions_live
        cur.execute("""SELECT symbol, direction, size_usd, entry_price, entry_time
            FROM positions_live WHERE status='OPEN' ORDER BY entry_time DESC""")
        rows=cur.fetchall(); cur.close(); conn.close()
        for row in rows:
            if row[0] not in open_positions:
                open_positions[row[0]]={
                    'side': 'BUY' if row[1]=='LONG' else 'SELL',
                    'direction': row[1],
                    'size_usd': float(row[2]),
                    'confidence': 0.6,
                    'entry_price': float(row[3]) if row[3] else 0.0,
                    'entry_time': row[4], 'hold_cycles': 0
                }
        log.info(f"Restored {len(open_positions)} open positions: {list(open_positions.keys())}")'''

content = content.replace(old, new)
with open('/root/agent_loop_v5.py', 'w') as f:
    f.write(content)
print("Done!")
EOF

python3 -c "import ast; ast.parse(open('/root/agent_loop_v5.py').read()); print('Syntax OK')"
sed -n '616,632p' /root/agent_loop_v5.py
python3 << 'EOF'
with open('/root/agent_loop_v5.py', 'r') as f:
    content = f.read()

old = '''        log.info(f"Restored {len(open_positions)} open positions: {list(open_positions.keys())}")
        # Sync restored positions to positions_live
        if open_positions:
            conn2 = get_db(); cur2 = conn2.cursor()
            for sym, pos in open_positions.items():
                cur2.execute("""
                    INSERT INTO positions_live (symbol, direction, entry_price, size_usd, status, updated_at)
                    VALUES (%s, %s, %s, %s, 'OPEN', NOW())
                    ON CONFLICT (symbol) DO UPDATE SET
                    direction=EXCLUDED.direction, entry_price=EXCLUDED.entry_price,
                    size_usd=EXCLUDED.size_usd, status='OPEN', updated_at=NOW()
                """, (sym, pos['direction'], pos['entry_price'], pos['size_usd']))
            conn2.commit(); cur2.close(); conn2.close()
            log.info(f"Synced {len(open_positions)} positions to positions_live")'''

new = '''        log.info(f"Restored {len(open_positions)} open positions from positions_live: {list(open_positions.keys())}")'''

content = content.replace(old, new)
with open('/root/agent_loop_v5.py', 'w') as f:
    f.write(content)
print("Done!")
EOF

python3 -c "import ast; ast.parse(open('/root/agent_loop_v5.py').read()); print('Syntax OK')"
systemctl restart aria_loop_v5.service
sleep 15
journalctl -u aria_loop_v5.service -n 10 --no-pager | grep -i "restored\|open positions\|cycle 1"
journalctl -u aria_loop_v5.service -n 15 --no-pager
journalctl -u aria_loop_v5.service --since "13:33:00" --until "13:33:40" --no-pager
journalctl -u aria_loop_v5.service --no-pager | grep "Started\|Restored\|ARIAv5.*Cycle 1" | tail -5
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT symbol, direction, entry_price, size_usd, entry_time FROM positions_live WHERE status='OPEN';"
journalctl -u aria_loop_v5.service -n 50 --no-pager | grep -i "BTC\|ETH" | head -20
grep -n "MIN_CONFIDENCE\|min_conf\|CONFIDENCE" /root/agent_loop_v5.py | head -10
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "SELECT symbol, COUNT(*) FROM closed_trades GROUP BY symbol ORDER BY count DESC;"
python3 << 'EOF'
with open('/root/agent_loop_v5.py', 'r') as f:
    content = f.read()

old = '''    # ── Step 1: Get model signal ──────────────────────────
    try:
        from aria_model_inference import get_model_signal
        model_dir, model_conf, model_reason = get_model_signal(symbol)
    except Exception as e:
        log.warning(f"Model inference import failed: {e}")
        model_dir, model_conf, model_reason = None, 0.52, "import_error"'''

new = '''    # ── Step 1: Get model signal ──────────────────────────
    # Crypto uses rules only until 500+ trades accumulated
    if symbol in ['BTC', 'ETH']:
        model_dir, model_conf, model_reason = None, 0.52, "crypto_rules_only"
        log.info(f"  {symbol} CRYPTO MODE: rules-only (insufficient trade history)")
    else:
        try:
            from aria_model_inference import get_model_signal
            model_dir, model_conf, model_reason = get_model_signal(symbol)
        except Exception as e:
            log.warning(f"Model inference import failed: {e}")
            model_dir, model_conf, model_reason = None, 0.52, "import_error"'''

content = content.replace(old, new)
with open('/root/agent_loop_v5.py', 'w') as f:
    f.write(content)
print("Done!")
EOF

python3 -c "import ast; ast.parse(open('/root/agent_loop_v5.py').read()); print('Syntax OK')"
systemctl restart aria_loop_v5.service
sleep 65
journalctl -u aria_loop_v5.service -n 30 --no-pager | grep -i "BTC\|ETH\|crypto\|rules"
psql "postgresql://postgres:aria_secure_2026@localhost:5432/aria_db" -c "
DELETE FROM positions_live WHERE symbol IN ('BTC','ETH');
UPDATE orders_outbox SET status='CLOSED' WHERE symbol IN ('BTC','ETH') AND status='EXECUTED';
SELECT symbol, direction FROM positions_live WHERE status='OPEN';"
grep -n "BTC\|ETH" /root/agent_loop_v5.py | grep -i "LONG\|SHORT\|rules" | head -20
cat > /root/aria_crypto_engine.py << 'EOF'
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
EOF

python3 -c "import ast; ast.parse(open('/root/aria_crypto_engine.py').read()); print('Syntax OK')"
git add agent_loop_v5.py aria_crypto_engine.py aria_market_updater.py aria_anomaly_detector.py && git commit -m "feat: crypto engine rules-only, OI signals, single source of truth positions_live, health thresholds fixed"
git push origin master && git push v1 master
UNT(*) FROM jobs_raw; SELECT COUNT(*) FROM jobs_scored; SELECT COUNT(*) FROM star_stories; SELECT COUNT(*) FROM cv_versions;"
cd /root/JobPilot
systemctl status jobpilot.service
sqlite3 jobpilot.db "SELECT COUNT(*) FROM jobs_raw; SELECT COUNT(*) FROM jobs_scored; SELECT COUNT(*) FROM star_stories; SELECT COUNT(*) FROM cv_versions;"
cd /root/JobPilot && sqlite3 jobpilot.db "SELECT date, tokens_used, estimated_cost FROM api_usage ORDER BY date DESC LIMIT 5;"
cd /root/JobPilot && python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
print('GEMINI:', 'SET' if os.getenv('GEMINI_API_KEY') else 'MISSING')
print('GROQ:', 'SET' if os.getenv('GROQ_API_KEY') else 'MISSING')
print('ANTHROPIC:', 'SET' if os.getenv('ANTHROPIC_API_KEY') else 'MISSING')
"
cd /root/JobPilot
systemctl status jobpilot.service
cd /root/JobPilot && systemctl status jobpilot.service
ss -tlnp | grep -E '8080|8081|5000|3000'
pip install fastapi uvicorn jinja2 --break-system-packages
mkdir -p /root/JobPilot/dashboard/templates
mkdir -p /root/JobPilot/dashboard/static
ls -la /root/JobPilot/dashboard/
# 1. Copy backend
nano /root/JobPilot/dashboard/app.py
# paste dashboard_app.py contents
# 2. Copy template
nano /root/JobPilot/dashboard/templates/index.html
cd /root/JobPilot
systemctl status jobpilot.service
cd /root/JobPilot && python3 -c "
import sqlite3
conn = sqlite3.connect('jobpilot.db')
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)')
c.execute(\"INSERT OR IGNORE INTO settings (key,value) VALUES ('notifications_enabled','1')\")
c.execute(\"INSERT OR IGNORE INTO settings (key,value) VALUES ('notifications_mode','auto')\")
conn.commit()
print('Done')
"
nano /root/JobPilot/dashboard/app.py
cd /root/JobPilot && python3 -c "import dashboard.app; print('Import OK')"
nano /root/JobPilot/dashboard/templates/index.html
ls -la /root/JobPilot/dashboard/templates/
cat > /etc/systemd/system/jobpilot-dashboard.service << 'EOF'
[Unit]
Description=JobPilot Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/JobPilot
ExecStart=/usr/bin/python3 /root/JobPilot/dashboard/app.py
Restart=always
RestartSec=5
EnvironmentFile=/root/JobPilot/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable jobpilot-dashboard
systemctl start jobpilot-dashboard
systemctl status jobpilot-dashboard
journalctl -u jobpilot-dashboard.service -n 30 --no-pager
nano /root/JobPilot/dashboard/app.py
systemctl restart jobpilot-dashboard && systemctl status jobpilot-dashboard
pip install python-multipart --break-system-packages
nano /root/JobPilot/dashboard/app.py
systemctl restart jobpilot-dashboard && systemctl status jobpilot-dashboard
apt install nginx -y
openssl req -x509 -nodes -days 365 -newkey rsa:2048   -keyout /etc/ssl/private/jobpilot.key   -out /etc/ssl/certs/jobpilot.crt   -subj "/C=GB/ST=Leeds/L=Leeds/O=JobPilot/CN=65.108.217.183"
cat > /etc/nginx/sites-available/jobpilot << 'EOF'
server {
    listen 80;
    server_name 65.108.217.183;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name 65.108.217.183;

    ssl_certificate     /etc/ssl/certs/jobpilot.crt;
    ssl_certificate_key /etc/ssl/private/jobpilot.key;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

ln -s /etc/nginx/sites-available/jobpilot /etc/nginx/sites-enabled/
nginx -t
systemctl restart nginx
systemctl status nginx
cd /root/JobPilot && python3 -c "
from scrapers.portal_scanner import COMPANIES
print(f'Total companies configured: {len(COMPANIES)}')
for name, portal, pid in COMPANIES:
    print(f'  {name} → {portal}/{pid}')
"
cd /root/JobPilot && python3 -c "
import requests

# Test each broken company with correct format
tests = [
    ('Revolut',      'https://api.lever.co/v0/postings/revolut?mode=json'),
    ('Wise',         'https://boards-api.greenhouse.io/v1/boards/wise/jobs'),
    ('Starling',     'https://boards-api.greenhouse.io/v1/boards/starlingbank/jobs'),
    ('Quantexa',     'https://boards-api.greenhouse.io/v1/boards/quantexa/jobs'),
    ('Palantir',     'https://boards-api.greenhouse.io/v1/boards/palantir/jobs'),
    ('Synthesia',    'https://boards-api.greenhouse.io/v1/boards/synthesia/jobs'),
    ('Darktrace',    'https://boards-api.greenhouse.io/v1/boards/darktrace/jobs'),
    ('Onfido',       'https://boards-api.greenhouse.io/v1/boards/onfido/jobs'),
    ('Tide',         'https://api.lever.co/v0/postings/tide?mode=json'),
    ('Tractable',    'https://api.lever.co/v0/postings/tractable?mode=json'),
]

for name, url in tests:
    try:
        r = requests.get(url, timeout=10, headers={'User-Agent':'Mozilla/5.0'})
        print(f'{name}: {r.status_code}')
    except Exception as e:
        print(f'{name}: ERROR {e}')
"
cd /root/JobPilot && python3 -c "
import requests
h = {'User-Agent':'Mozilla/5.0'}

tests = [
    ('Revolut-ashby',    'https://jobs.ashbyhq.com/api/non-user-graphql', 'ashby', 'revolut'),
    ('Wise-ashby',       'https://jobs.ashbyhq.com/api/non-user-graphql', 'ashby', 'wise'),
    ('Starling-ashby',   'https://jobs.ashbyhq.com/api/non-user-graphql', 'ashby', 'starlingbank'),
    ('Quantexa-ashby',   'https://jobs.ashbyhq.com/api/non-user-graphql', 'ashby', 'quantexa'),
    ('Palantir-ashby',   'https://jobs.ashbyhq.com/api/non-user-graphql', 'ashby', 'palantir'),
    ('Synthesia-ashby',  'https://jobs.ashbyhq.com/api/non-user-graphql', 'ashby', 'synthesia'),
    ('Darktrace-ashby',  'https://jobs.ashbyhq.com/api/non-user-graphql', 'ashby', 'darktrace'),
    ('Onfido-ashby',     'https://jobs.ashbyhq.com/api/non-user-graphql', 'ashby', 'onfido'),
    ('Tide-ashby',       'https://jobs.ashbyhq.com/api/non-user-graphql', 'ashby', 'tide'),
    ('Tractable-ashby',  'https://jobs.ashbyhq.com/api/non-user-graphql', 'ashby', 'tractable'),
]

payload_template = {
    'operationName': 'ApiJobBoardWithTeams',
    'variables': {'organizationHostedJobsPageName': ''},
    'query': 'query ApiJobBoardWithTeams(\$organizationHostedJobsPageName: String!) { jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: \$organizationHostedJobsPageName) { jobPostings { id title } } }'
}

for name, url, portal, pid in tests:
    try:
        import json
        p = dict(payload_template)
        p['variables'] = {'organizationHostedJobsPageName': pid}
        r = requests.post(url, json=p, headers={**h, 'Content-Type':'application/json'}, timeout=10)
        data = r.json()
        jobs = data.get('data',{}).get('jobBoard',{}).get('jobPostings',[]) or []
        print(f'{name}: {len(jobs)} jobs')
    except Exception as e:
        print(f'{name}: ERROR {e}')
"
cd /root/JobPilot && python3 -c "
import requests, json
h = {'User-Agent':'Mozilla/5.0', 'Content-Type':'application/json'}
url = 'https://jobs.ashbyhq.com/api/non-user-graphql'
q = 'query ApiJobBoardWithTeams(\$organizationHostedJobsPageName: String!) { jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: \$organizationHostedJobsPageName) { jobPostings { id title } } }'

# Try alternative IDs
tests = [
    ('Revolut',     ['revolut','Revolut']),
    ('Wise',        ['wise','transferwise','wiseapp']),
    ('Starling',    ['starling','starlingbank','starling-bank']),
    ('Palantir',    ['palantir','palantir-technologies']),
    ('Darktrace',   ['darktrace','Darktrace']),
    ('Onfido',      ['onfido','Onfido']),
    ('Tide',        ['tide','tideplatform']),
]

for name, ids in tests:
    for pid in ids:
        try:
            p = {'operationName':'ApiJobBoardWithTeams','variables':{'organizationHostedJobsPageName':pid},'query':q}
            r = requests.post(url, json=p, headers=h, timeout=8)
            data = r.json()
            jobs = (data.get('data') or {}).get('jobBoard') or {}
            postings = jobs.get('jobPostings') or []
            if postings:
                print(f'{name} [{pid}]: {len(postings)} jobs FOUND')
                break
        except:
            pass
    else:
        print(f'{name}: not on Ashby — trying Greenhouse/Lever...')
"
cd /root/JobPilot && python3 -c "
import requests
h = {'User-Agent':'Mozilla/5.0'}

# Test Lever with correct URL format
tests = [
    ('Revolut-lever',  'https://api.lever.co/v0/postings/revolut'),
    ('Wise-lever',     'https://api.lever.co/v0/postings/wise'),
    ('Tide-lever',     'https://api.lever.co/v0/postings/tide'),
    ('Starling-lever', 'https://api.lever.co/v0/postings/starling'),
    ('Palantir-lever', 'https://api.lever.co/v0/postings/palantir'),
    ('Darktrace-lever','https://api.lever.co/v0/postings/darktrace'),
    ('Onfido-lever',   'https://api.lever.co/v0/postings/onfido'),
    ('Wise-gh',        'https://boards-api.greenhouse.io/v1/boards/transferwise/jobs'),
    ('Starling-gh',    'https://boards-api.greenhouse.io/v1/boards/starling/jobs'),
    ('Palantir-gh',    'https://boards-api.greenhouse.io/v1/boards/palantirtechnologies/jobs'),
]

for name, url in tests:
    try:
        r = requests.get(url, headers=h, timeout=10)
        print(f'{name}: {r.status_code}')
    except Exception as e:
        print(f'{name}: ERROR')
"
cd /root/JobPilot && python3 -c "
import requests
h = {'User-Agent':'Mozilla/5.0'}

tests = [
    ('Wise-gh2',        'https://boards-api.greenhouse.io/v1/boards/wiseapp/jobs'),
    ('Starling-gh2',    'https://boards-api.greenhouse.io/v1/boards/starlingbankcareers/jobs'),
    ('Revolut-gh',      'https://boards-api.greenhouse.io/v1/boards/revolut/jobs'),
    ('Darktrace-gh',    'https://boards-api.greenhouse.io/v1/boards/darktracecareers/jobs'),
    ('Onfido-gh2',      'https://boards-api.greenhouse.io/v1/boards/onfidocareers/jobs'),
    ('Tide-gh',         'https://boards-api.greenhouse.io/v1/boards/tide/jobs'),
    ('Checkout-gh2',    'https://boards-api.greenhouse.io/v1/boards/checkoutcom/jobs'),
    ('Palantir-lever2', 'https://api.lever.co/v0/postings/palantir-technologies'),
    ('Monzo-gh2',       'https://boards-api.greenhouse.io/v1/boards/monzo/jobs'),
    ('Improbable-gh2',  'https://boards-api.greenhouse.io/v1/boards/improbable/jobs'),
]

for name, url in tests:
    try:
        r = requests.get(url, headers=h, timeout=10)
        if r.status_code == 200:
            import json
            data = r.json()
            if 'jobs' in data:
                count = len(data['jobs'])
            else:
                count = len(data) if isinstance(data, list) else '?'
            print(f'{name}: 200 OK — {count} jobs')
        else:
            print(f'{name}: {r.status_code}')
    except Exception as e:
        print(f'{name}: ERROR')
"
cp /root/JobPilot/scrapers/portal_scanner.py /root/JobPilot/scrapers/portal_scanner_backup.py
nano /root/JobPilot/scrapers/portal_scanner.py
cd /root/JobPilot && python3 scrapers/portal_scanner.py
nano /root/JobPilot/scrapers/portal_scanner.py
systemctl restart jobpilot.service
systemctl status jobpilot.service
cd /root/JobPilot && python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()

# Test Gemini rate limit handling
from google import genai
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
try:
    r = client.models.generate_content(model='gemini-2.0-flash-lite', contents='Say OK')
    print('Gemini: OK -', r.text.strip())
except Exception as e:
    print('Gemini error:', type(e).__name__, str(e)[:100])

# Test Groq
from groq import Groq
client2 = Groq(api_key=os.getenv('GROQ_API_KEY'))
try:
    r2 = client2.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[{'role':'user','content':'Say OK'}],
        max_tokens=10
    )
    print('Groq: OK -', r2.choices[0].message.content.strip())
except Exception as e:
    print('Groq error:', type(e).__name__, str(e)[:100])
"
nano /root/JobPilot/scoring/claude_scorer.py
cd /root/JobPilot && python3 -c "
from scoring.claude_scorer import ClaudeScorer
scorer = ClaudeScorer()
result = scorer.score_job(
    job_id=7777,
    title='Data Engineer',
    company='Palantir',
    location='London, UK',
    description='Data Engineer building large scale data pipelines. Python, Spark, SQL required.'
)
print('Provider:', result.get('provider'))
print('Grade:', result.get('grade'))
print('Score:', result.get('weighted_score'))
"
nano /root/JobPilot/scoring/claude_scorer.py
cat -n /root/JobPilot/scoring/claude_scorer.py | head -50
grep -n "def call_llm\|def call_gemini\|def call_groq\|def run" /root/JobPilot/scoring/claude_scorer.py
sed -n '134,220p' /root/JobPilot/scoring/claude_scorer.py
sed -n '330,380p' /root/JobPilot/scoring/claude_scorer.py
cat > /tmp/run_method.py << 'EOF'
   def run(self):
        """Score all unscored jobs."""
        jobs = self._get_unscored_jobs()
        print(f"[SCORER] {len(jobs)} unscored jobs found.")

        MAX_PER_RUN = 50
        if len(jobs) > MAX_PER_RUN:
            print(f"[SCORER] Limiting to {MAX_PER_RUN} jobs this run to protect rate limits.")
            jobs = jobs[:MAX_PER_RUN]

        apply_list = []

        for job in jobs:
            job_id, title, company, location, description, url = job
            print(f"[SCORER] Scoring: {title} @ {company}...")

            result = self.score_job(job_id, title, company, location, description)

            grade    = result.get("grade", "F")
            ws       = result.get("weighted_score", 0)
            priority = result.get("priority", "low")
            summary  = result.get("one_line_summary", "")
            provider = result.get("provider", "unknown")

            bar = "█" * int(ws // 10) + "░" * (10 - int(ws // 10))
            print(f"         [{provider}] Grade: {grade} | Score: {int(ws)}/100 [{bar}] | {priority.upper()}")
            print(f"         {summary}")

            if grade in ("A", "B"):
                self._send_telegram_alert(title, company, grade, ws, url, summary, result, provider)

            if result.get("apply"):
                apply_list.append({
                    "title":    title,
                    "company":  company,
                    "grade":    grade,
                    "score":    int(ws),
                    "priority": priority,
                    "url":      url,
                    "provider": provider,
                })

        apply_list.sort(key=lambda x: x["score"], reverse=True)

        print(f"\n[SCORER] Done. {len(jobs)} jobs scored.")
        print(f"[SCORER] {len(apply_list)} jobs recommended.")

        if apply_list:
            print("\n── TOP MATCHES ──────────────────────────────────────────")
            for i, job in enumerate(apply_list[:10], 1):
                print(f"{i:2}. [Grade {job['grade']} | {job['score']:3}/100] [{job['provider']}] {job['title']} @ {job['company']}")
                print(f"     {job['url']}")

        return apply_list
EOF

cat > /root/JobPilot/scoring/claude_scorer.py << 'SCORER_EOF'
"""
JobPilot Scoring Engine — Multi-Provider
=========================================
Primary:  Groq Llama 3.3 70B (free, fast, reliable)
Fallback: Google Gemini 1.5 Flash (free, good quality)
Last:     Anthropic Claude (paid, only if both fail)

A-F grading across 10 weighted dimensions.
6-block evaluation output per job.
Telegram alert on A/B grade jobs.
"""

import sqlite3
import json
import os
import sys
import time
sys.path.insert(0, "/root/JobPilot")
from datetime import datetime
from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    MIN_SCORE_TO_APPLY,
    DAILY_TOKEN_LIMIT,
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")

CV_SUMMARY = """
Name: Usama Fateh Ali
Current: MSc Data Analytics, De Montfort University (graduating Sep 2026)
Previous: BEng Electrical Engineering, UMT Lahore (2024)

Key Projects:
- ARIA: 7-layer autonomous multi-agent trading system. Live in production.
  XGBoost+RF ensemble 78.3% multi-asset accuracy. 9 systemd services,
  FastAPI, PostgreSQL, Hetzner CPX32, Railway, Claude API.
- Quantum Adversarial Market Detection: IBM Torino 133-qubit hardware.
- CoBots (BEng Thesis): 6-DOF robotic arm, ESP32, OpenCV, Tesseract OCR.
- JobPilot: Autonomous AI job search agent, 24/7 systemd, multi-provider LLM.

Skills: Python, FastAPI, PostgreSQL, XGBoost, PyTorch, systemd, Docker,
        multi-agent systems, safety architecture, anomaly detection

Target roles: AI Engineer, ML Engineer, Data Engineer, Agent Engineer,
              Autonomous Systems, Fintech Data (Revolut, Quantexa etc.)
Salary: £45,000+ | Location: Manchester UK | Visa: Requires UK sponsorship
"""

DIMENSIONS = [
    ("dim_title_match",        "Role Title Match",       0.15),
    ("dim_skills_match",       "Technical Skills Match", 0.20),
    ("dim_experience_level",   "Experience Level Fit",   0.15),
    ("dim_location_remote",    "Location / Remote",      0.10),
    ("dim_salary_range",       "Salary Range",           0.10),
    ("dim_company_stage",      "Company Stage / Type",   0.10),
    ("dim_growth_potential",   "Growth Potential",       0.05),
    ("dim_visa_sponsorship",   "Visa Sponsorship",       0.10),
    ("dim_industry_relevance", "Industry Relevance",     0.05),
    ("dim_keyword_overlap",    "CV Keyword Overlap",     0.00),
]

PROMPT_TEMPLATE = """You are a senior career advisor evaluating job fit for a candidate.
Score this job across 10 dimensions (each 0-100) and write 6 evaluation blocks.
Be honest and strict.

CANDIDATE PROFILE:
{cv}

JOB LISTING:
Title: {title}
Company: {company}
Location: {location}
Description: {description}

Respond in valid JSON only. No preamble. No markdown.

{{
    "dim_title_match": <0-100>,
    "dim_skills_match": <0-100>,
    "dim_experience_level": <0-100>,
    "dim_location_remote": <0-100, 100 if remote or Manchester/London>,
    "dim_salary_range": <0-100, 100 if above £45k, 50 if unknown, 0 if below>,
    "dim_company_stage": <0-100, fintech/AI/autonomous preferred>,
    "dim_growth_potential": <0-100>,
    "dim_visa_sponsorship": <0-100, 100 if sponsors, 50 if unknown, 0 if no>,
    "dim_industry_relevance": <0-100>,
    "dim_keyword_overlap": <0-100>,
    "match_reasons": ["reason1", "reason2", "reason3"],
    "gaps": ["gap1", "gap2"],
    "apply": <true or false>,
    "priority": "<high or medium or low>",
    "one_line_summary": "<one sentence why this is or isn't a strong match>",
    "block_role_summary": "<2-3 sentences: what this role is>",
    "block_cv_match": "<2-3 sentences: specific CV projects that match>",
    "block_level_strategy": "<1-2 sentences: positioning strategy>",
    "block_comp_research": "<1-2 sentences: estimated salary range>",
    "block_personalisation": "<2-3 sentences: cover letter talking points>",
    "block_interview_prep": "<2-3 sentences: likely interview topics>"
}}"""

def weighted_score_to_grade(ws: float) -> str:
    if ws >= 85: return "A"
    if ws >= 70: return "B"
    if ws >= 55: return "C"
    if ws >= 40: return "D"
    if ws >= 25: return "E"
    return "F"

def parse_json(raw: str) -> dict:
    for marker in ["```json", "```"]:
        raw = raw.replace(marker, "")
    return json.loads(raw.strip())

def call_gemini(prompt: str) -> dict:
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt,
    )
    return parse_json(response.text)

def call_groq(prompt: str) -> dict:
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1200,
        temperature=0.1,
    )
    return parse_json(response.choices[0].message.content)

def call_claude(prompt: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}]
    )
    return parse_json(message.content[0].text)

def call_llm(prompt: str) -> tuple[dict, str]:
    """Try Groq → Gemini → Claude with smart backoff."""

    if GROQ_API_KEY:
        for attempt in range(3):
            try:
                result = call_groq(prompt)
                return result, "groq"
            except Exception as e:
                err = str(e).lower()
                if "429" in err or "rate" in err:
                    wait = 2 ** attempt
                    print(f"[SCORER] Groq rate limit, waiting {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"[SCORER] Groq failed: {e}")
                    break

    if GEMINI_API_KEY:
        for attempt in range(2):
            try:
                result = call_gemini(prompt)
                return result, "gemini"
            except Exception as e:
                err = str(e).lower()
                if "429" in err or "quota" in err:
                    wait = 5 * (attempt + 1)
                    print(f"[SCORER] Gemini quota hit, waiting {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"[SCORER] Gemini failed: {e}")
                    break

    if ANTHROPIC_API_KEY:
        try:
            result = call_claude(prompt)
            return result, "claude"
        except Exception as e:
            print(f"[SCORER] Claude failed: {e}")

    raise Exception("All providers failed.")

class ClaudeScorer:

    def __init__(self, db_path="/root/JobPilot/jobpilot.db"):
        self.db_path = db_path
        self.tokens_used_today = 0

    def _get_unscored_jobs(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.id, r.title, r.company, r.location, r.description, r.url
            FROM jobs_raw r
            LEFT JOIN jobs_scored s ON r.id = s.job_id
            WHERE s.id IS NULL
            ORDER BY r.scraped_at DESC
        """)
        jobs = cursor.fetchall()
        conn.close()
        return jobs

    def _save_score(self, job_id, result, provider):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        ws = 0.0
        for col, label, weight in DIMENSIONS:
            ws += result.get(col, 0) * weight
        grade = weighted_score_to_grade(ws)
        cursor.execute("""
            INSERT INTO jobs_scored (
                job_id, score, grade, weighted_score,
                dim_title_match, dim_skills_match, dim_experience_level,
                dim_location_remote, dim_salary_range, dim_company_stage,
                dim_growth_potential, dim_visa_sponsorship,
                dim_industry_relevance, dim_keyword_overlap,
                block_role_summary, block_cv_match, block_level_strategy,
                block_comp_research, block_personalisation, block_interview_prep,
                match_reasons, gaps, apply, priority, one_line_summary
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            job_id, int(ws), grade, round(ws, 2),
            result.get("dim_title_match", 0),
            result.get("dim_skills_match", 0),
            result.get("dim_experience_level", 0),
            result.get("dim_location_remote", 0),
            result.get("dim_salary_range", 0),
            result.get("dim_company_stage", 0),
            result.get("dim_growth_potential", 0),
            result.get("dim_visa_sponsorship", 0),
            result.get("dim_industry_relevance", 0),
            result.get("dim_keyword_overlap", 0),
            result.get("block_role_summary", ""),
            result.get("block_cv_match", ""),
            result.get("block_level_strategy", ""),
            result.get("block_comp_research", ""),
            result.get("block_personalisation", ""),
            result.get("block_interview_prep", ""),
            json.dumps(result.get("match_reasons", [])),
            json.dumps(result.get("gaps", [])),
            1 if result.get("apply") else 0,
            result.get("priority", "low"),
            result.get("one_line_summary", ""),
        ))
        conn.commit()
        conn.close()
        return grade, round(ws, 2)

    def _track_usage(self, tokens):
        self.tokens_used_today += tokens
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("""
            INSERT INTO api_usage (date, tokens_used, estimated_cost)
            VALUES (?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
            tokens_used = tokens_used + ?,
            estimated_cost = estimated_cost + ?,
            updated_at = CURRENT_TIMESTAMP
        """, (today, tokens, tokens * 0.000003, tokens, tokens * 0.000003))
        conn.commit()
        conn.close()

    def score_job(self, job_id, title, company, location, description):
        prompt = PROMPT_TEMPLATE.format(
            cv=CV_SUMMARY,
            title=title,
            company=company,
            location=location,
            description=description[:2500],
        )
        try:
            result, provider = call_llm(prompt)
            grade, ws = self._save_score(job_id, result, provider)
            result["grade"] = grade
            result["weighted_score"] = ws
            result["provider"] = provider
            return result
        except Exception as e:
            print(f"[SCORER] All providers failed for job {job_id}: {e}")
            return {"grade": "F", "weighted_score": 0, "apply": False, "priority": "low", "provider": "none"}

    def _send_telegram_alert(self, title, company, grade, ws, url, summary, result, provider):
        grade_emoji = {"A": "🏆", "B": "⭐", "C": "👍", "D": "👀", "E": "➖", "F": "❌"}.get(grade, "")
        provider_tag = {"gemini": "🟦 Gemini", "groq": "🟩 Groq", "claude": "🟪 Claude"}.get(provider, provider)
        lines = [
            f"{grade_emoji} GRADE {grade} JOB — {int(ws)}/100",
            f"Scored by {provider_tag}",
            "",
            f"📌 {title}",
            f"🏢 {company}",
            "",
            f"💡 {summary}",
            "",
            "── CV MATCH ──",
            result.get("block_cv_match", ""),
            "",
            "── INTERVIEW PREP ──",
            result.get("block_interview_prep", ""),
            "",
            f"🔗 {url}",
        ]
        try:
            from telegram_notifier import send_message
            # Check notification settings
            import sqlite3 as sq
            conn = sq.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key='notifications_enabled'")
            row = c.fetchone()
            conn.close()
            if row and row[0] == '0':
                print(f"[SCORER] Notifications disabled, skipping Telegram")
                return
            send_message("\n".join(lines))
        except Exception as e:
            print(f"[SCORER] Telegram error: {e}")

    def run(self):
        """Score all unscored jobs — max 50 per run to protect rate limits."""
        jobs = self._get_unscored_jobs()
        print(f"[SCORER] {len(jobs)} unscored jobs found.")

        MAX_PER_RUN = 50
        if len(jobs) > MAX_PER_RUN:
            print(f"[SCORER] Limiting to {MAX_PER_RUN} jobs this run.")
            jobs = jobs[:MAX_PER_RUN]

        apply_list = []

        for job in jobs:
            job_id, title, company, location, description, url = job
            print(f"[SCORER] Scoring: {title} @ {company}...")

            result = self.score_job(job_id, title, company, location, description)

            grade    = result.get("grade", "F")
            ws       = result.get("weighted_score", 0)
            priority = result.get("priority", "low")
            summary  = result.get("one_line_summary", "")
            provider = result.get("provider", "unknown")

            bar = "█" * int(ws // 10) + "░" * (10 - int(ws // 10))
            print(f"         [{provider}] Grade: {grade} | Score: {int(ws)}/100 [{bar}] | {priority.upper()}")
            print(f"         {summary}")

            if grade in ("A", "B"):
                self._send_telegram_alert(title, company, grade, ws, url, summary, result, provider)

            if result.get("apply"):
                apply_list.append({
                    "title":    title,
                    "company":  company,
                    "grade":    grade,
                    "score":    int(ws),
                    "priority": priority,
                    "url":      url,
                    "provider": provider,
                })

        apply_list.sort(key=lambda x: x["score"], reverse=True)

        print(f"\n[SCORER] Done. {len(jobs)} jobs scored.")
        print(f"[SCORER] {len(apply_list)} jobs recommended.")

        if apply_list:
            print("\n── TOP MATCHES ──────────────────────────────────────────")
            for i, job in enumerate(apply_list[:10], 1):
                print(f"{i:2}. [Grade {job['grade']} | {job['score']:3}/100] [{job['provider']}] {job['title']} @ {job['company']}")
                print(f"     {job['url']}")

        return apply_list


if __name__ == "__main__":
    scorer = ClaudeScorer()
    scorer.run()
SCORER_EOF

cd /root/JobPilot && python3 -c "from scoring.claude_scorer import ClaudeScorer; print('Import OK')"
cd /root/JobPilot && python3 -c "
from scoring.claude_scorer import ClaudeScorer
scorer = ClaudeScorer()
result = scorer.score_job(
    job_id=6666,
    title='Data Scientist',
    company='Monzo',
    location='London, UK',
    description='Data Scientist building ML models for fraud detection and credit risk. Python, SQL, PyTorch required.'
)
print('Provider:', result.get('provider'))
print('Grade:', result.get('grade'))
print('Score:', result.get('weighted_score'))
print('Summary:', result.get('one_line_summary'))
"
# Fix Gemini model name
sed -i 's/gemini-1.5-flash/gemini-2.0-flash-lite/g' /root/JobPilot/scoring/claude_scorer.py
# Verify
grep "gemini" /root/JobPilot/scoring/claude_scorer.py | grep "model"
sleep 60 && cd /root/JobPilot && python3 -c "
from scoring.claude_scorer import ClaudeScorer
scorer = ClaudeScorer()
result = scorer.score_job(
    job_id=6665,
    title='Data Scientist',
    company='Monzo',
    location='London, UK',
    description='Data Scientist building ML models for fraud detection. Python, SQL, PyTorch required.'
)
print('Provider:', result.get('provider'))
print('Grade:', result.get('grade'))
print('Score:', result.get('weighted_score'))
"
cd /root/JobPilot && python3 -c "
from groq import Groq
import os
from dotenv import load_dotenv
load_dotenv()
client = Groq(api_key=os.getenv('GROQ_API_KEY'))
try:
    r = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[{'role':'user','content':'OK'}],
        max_tokens=5
    )
    print('Groq OK')
except Exception as e:
    # Check retry-after header
    print('Error:', str(e)[:200])
"
systemctl restart jobpilot.service && systemctl status jobpilot.service
cd /root/JobPilot && git status
cd /root/JobPilot
# Create .gitignore first
cat > .gitignore << 'EOF'
.env
*.db
*.db-journal
cv_engine/tailored/
cv_engine/master_cv.docx
__pycache__/
*.pyc
*.pyo
*.bak
*.save
jobpilot.db
logs/
*.log
dashboard/static/
EOF

# Add everything
git add .
git commit -m "feat: Phase 1-5 complete

- A-F scoring across 10 weighted dimensions
- ATS PDF CV generation per job  
- Portal scanner (31 companies, Greenhouse/Lever/Ashby)
- STAR+R interview bank
- FastAPI dashboard with HTTPS
- Multi-provider LLM chain (Groq/Gemini/Claude fallback)
- Rate limit backoff, 50 jobs/run limit
- Notification settings (on/off/modes)
- Settings table for user preferences"
git push origin main
git remote set-url origin https://Usama1909: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@github.com/Usama1909/JobPilot.git
git push origin main
cat > /root/JobPilot/README.md << 'READMEEOF'
# paste README contents here
READMEEOF

nano /root/JobPilot/README.md
cd /root/JobPilot
git add README.md
git commit -m "docs: add professional README"
git push origin main
cd /root/JobPilot && sqlite3 jobpilot.db "
SELECT COUNT(*) as total_jobs FROM jobs_raw;
SELECT COUNT(*) as duplicate_urls FROM (
    SELECT url, COUNT(*) as cnt FROM jobs_raw
    GROUP BY url HAVING cnt > 1
);
SELECT COUNT(DISTINCT url) as unique_jobs FROM jobs_raw;
"
cd /root/JobPilot && sqlite3 jobpilot.db "
SELECT title, company, grade, weighted_score 
FROM jobs_scored s
JOIN jobs_raw r ON s.job_id = r.id
WHERE s.grade IN ('E','F')
ORDER BY s.scored_at DESC
LIMIT 20;
"
nano /root/JobPilot/scoring/pre_filter.py
cd /root/JobPilot && python3 scoring/pre_filter.py
nano /root/JobPilot/scoring/claude_scorer.py
cd /root/JobPilot && python3 -c "
from scoring.claude_scorer import ClaudeScorer
scorer = ClaudeScorer()
jobs = scorer._get_unscored_jobs()
from scoring.pre_filter import filter_jobs
filtered, skipped = filter_jobs(jobs)
print(f'Total unscored: {len(jobs)}')
print(f'After filter: {len(filtered)}')
print(f'Skipped: {skipped}')
print(f'API calls saved: {skipped}/{len(jobs)} = {int(skipped/max(len(jobs),1)*100)}%')
"
python3 -c "
content = open('/root/JobPilot/scoring/claude_scorer.py').read()
content = content.expandtabs(4)
open('/root/JobPilot/scoring/claude_scorer.py', 'w').write(content)
print('Fixed')
"
python3 -c "from scoring.claude_scorer import ClaudeScorer; print('Import OK')"
python3 << 'EOF'
with open('/root/JobPilot/scoring/claude_scorer.py', 'r') as f:
    content = f.read()

# Find and replace the broken run method
old = content[content.find('    def run(self):'):]
# Get everything after the class definition up to end
new_run = '''    def run(self):
        """Score all unscored jobs — pre-filter + max 50 per run."""
        from scoring.pre_filter import filter_jobs
        jobs = self._get_unscored_jobs()
        print(f"[SCORER] {len(jobs)} unscored jobs found.")

        jobs, skipped = filter_jobs(jobs)
        print(f"[SCORER] Pre-filter: {len(jobs)} relevant | {skipped} skipped")

        MAX_PER_RUN = 50
        if len(jobs) > MAX_PER_RUN:
            print(f"[SCORER] Limiting to {MAX_PER_RUN} jobs this run.")
            jobs = jobs[:MAX_PER_RUN]

        apply_list = []

        for job in jobs:
            job_id, title, company, location, description, url = job
            print(f"[SCORER] Scoring: {title} @ {company}...")
            result = self.score_job(job_id, title, company, location, description)
            grade    = result.get("grade", "F")
            ws       = result.get("weighted_score", 0)
            priority = result.get("priority", "low")
            summary  = result.get("one_line_summary", "")
            provider = result.get("provider", "unknown")
            bar = "█" * int(ws // 10) + "░" * (10 - int(ws // 10))
            print(f"         [{provider}] Grade: {grade} | Score: {int(ws)}/100 [{bar}] | {priority.upper()}")
            print(f"         {summary}")
            if grade in ("A", "B"):
                self._send_telegram_alert(title, company, grade, ws, url, summary, result, provider)
            if result.get("apply"):
                apply_list.append({
                    "title":    title,
                    "company":  company,
                    "grade":    grade,
                    "score":    int(ws),
                    "priority": priority,
                    "url":      url,
                    "provider": provider,
                })

        apply_list.sort(key=lambda x: x["score"], reverse=True)
        print(f"\\n[SCORER] Done. {len(jobs)} jobs scored.")
        print(f"[SCORER] {len(apply_list)} jobs recommended.")

        if apply_list:
            print("\\n── TOP MATCHES ──────────────────────────────────────────")
            for i, job in enumerate(apply_list[:10], 1):
                print(f"{i:2}. [Grade {job['grade']} | {job['score']:3}/100] [{job['provider']}] {job['title']} @ {job['company']}")
                print(f"     {job['url']}")

        return apply_list


if __name__ == "__main__":
    scorer = ClaudeScorer()
    scorer.run()
'''

# Replace from def run onwards
idx = content.find('    def run(self):')
new_content = content[:idx] + new_run

with open('/root/JobPilot/scoring/claude_scorer.py', 'w') as f:
    f.write(new_content)
print('Done')
EOF

python3 -c "from scoring.claude_scorer import ClaudeScorer; print('Import OK')"
cd /root/JobPilot && python3 -c "
from scoring.claude_scorer import ClaudeScorer
from scoring.pre_filter import filter_jobs
scorer = ClaudeScorer()
jobs = scorer._get_unscored_jobs()
filtered, skipped = filter_jobs(jobs)
print(f'Total unscored:  {len(jobs)}')
print(f'After filter:    {len(filtered)}')
print(f'Skipped:         {skipped}')
print(f'API calls saved: {int(skipped/max(len(jobs),1)*100)}%')
"
systemctl restart jobpilot.service && systemctl status jobpilot.service
cd /root/JobPilot
git add scoring/pre_filter.py scoring/claude_scorer.py
git commit -m "feat: two-stage pre-filter — 38% API calls saved"
git push origin main
