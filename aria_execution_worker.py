#!/usr/bin/env python3
"""
ARIA Execution Worker
Reads PENDING orders from orders_outbox, sends to exchange.
"""
import time, requests, psycopg2, logging, hmac, hashlib
from datetime import datetime
from urllib.parse import urlencode

logging.basicConfig(level=logging.INFO, format='%(asctime)s [EXECUTOR] %(message)s')
log = logging.getLogger()

DB = {'host':'localhost','port':5432,'dbname':'aria_db',
      'user':'postgres','password':'aria_secure_2026'}

BINANCE_API_KEY    = "AMMWwf7NYmSh02xjGbLu5nZv7CaW9B6IyG8Ghx2NNv4AwDIA5eSPpM2wzSjvgcif"
BINANCE_SECRET_KEY = "ATp5pNBYTPD8w84q8Dss0eAS7UVBSWxmK7jZ0w7pH5IPx5Cb2VEVE8lLf0WGTqTf"
BINANCE_TESTNET    = "https://testnet.binance.vision/api"
ARIA_URL           = "https://web-production-548c0.up.railway.app"
PAPER_USER         = "aria-agent-system"
CRYPTO_SYMBOLS     = ['BTC', 'ETH']

def get_db(): return psycopg2.connect(**DB)

def binance_request(method, endpoint, params=None):
    params = params or {}
    params['timestamp'] = int(time.time() * 1000)
    query = urlencode(params)
    sig = hmac.new(BINANCE_SECRET_KEY.encode(), query.encode(), hashlib.sha256).hexdigest()
    params['signature'] = sig
    headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
    url = f"{BINANCE_TESTNET}{endpoint}"
    try:
        if method == 'POST':
            r = requests.post(url, headers=headers, params=params, timeout=10)
        else:
            r = requests.get(url, headers=headers, params=params, timeout=10)
        return r.json()
    except Exception as e:
        log.error(f"Binance request failed: {e}")
        return {}

def get_binance_price(symbol):
    try:
        r = requests.get(f"{BINANCE_TESTNET}/v3/ticker/price",
                        params={'symbol': f'{symbol}USDT'}, timeout=5)
        return float(r.json().get('price', 0))
    except:
        return 0.0

def execute_crypto(symbol, direction, size_usd):
    price = get_binance_price(symbol)
    if price == 0: return False, 0, 0
    quantity = round(size_usd / price, 3)
    if symbol == 'BTC': quantity = round(quantity, 5)
    side = 'BUY' if direction == 'LONG' else 'SELL'
    result = binance_request('POST', '/v3/order', {
        'symbol': f'{symbol}USDT', 'side': side,
        'type': 'MARKET', 'quantity': quantity
    })
    if result.get('orderId'):
        fill_price = float(result.get('fills', [{}])[0].get('price', price))
        return True, fill_price, quantity
    log.error(f"Binance order failed: {result}")
    return False, 0, 0

def execute_paper(symbol, direction, size_usd):
    price = 0.0
    try:
        import yfinance as yf
        price = float(yf.Ticker(symbol).fast_info['last_price'])
    except: pass
    try:
        r = requests.post(f"{ARIA_URL}/paper/trade", json={
            'user_id': PAPER_USER, 'symbol': symbol,
            'direction': direction, 'amount_usd': size_usd,
            'entry_price': price
        }, timeout=5)
        if r.json().get('success'):
            log.info(f"Paper trade confirmed: {symbol} @ ${price:.2f}")
            return True, price, size_usd / price if price > 0 else 0
    except Exception as e:
        log.warning(f"Paper trade Railway call failed: {e}")
    return True, price, size_usd / price if price > 0 else 0

def update_order_status(order_id, status, fill_price=0, quantity=0):
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE orders_outbox SET status=%s, executed_at=NOW(), entry_price=CASE WHEN %s>0 THEN %s ELSE entry_price END WHERE id=%s",
                [status, fill_price, fill_price, order_id])
    if fill_price > 0:
        cur.execute("INSERT INTO signal_log (signal_name,signal_value,symbol,triggered_action) VALUES (%s,%s,%s,%s)",
                   ['execution_fill', fill_price, 'SYSTEM', f'{status}_qty:{quantity:.4f}'])
    conn.commit(); cur.close(); conn.close()

def get_pending_orders():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id,symbol,side,direction,size_usd,confidence FROM orders_outbox WHERE status='PENDING' ORDER BY created_at ASC LIMIT 10")
    rows = cur.fetchall(); cur.close(); conn.close()
    return rows

def main():
    log.info("ARIA Execution Worker started")
    log.info("Watching orders_outbox for PENDING orders...")
    while True:
        try:
            orders = get_pending_orders()
            if orders:
                log.info(f"Found {len(orders)} pending orders")
                for order in orders:
                    oid, symbol, side, direction, size_usd, confidence = order
                    log.info(f"Executing: {side} {symbol} ${size_usd:.0f} ({direction}) conf:{confidence:.2f}")
                    if symbol in CRYPTO_SYMBOLS:
                        success, price, qty = execute_crypto(symbol, direction, size_usd)
                    else:
                        success, price, qty = execute_paper(symbol, direction, size_usd)
                    if success:
                        update_order_status(oid, 'EXECUTED', price, qty)
                        log.info(f"✅ EXECUTED: {side} {symbol} @ ${price:.2f} qty:{qty:.4f}")
                    else:
                        update_order_status(oid, 'FAILED')
                        log.error(f"❌ FAILED: {side} {symbol}")
                    time.sleep(2)
            else:
                log.info("No pending orders — watching...")
        except Exception as e:
            log.error(f"Executor error: {e}")
        time.sleep(30)

if __name__ == '__main__':
    main()
