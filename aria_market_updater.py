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
_funding_rates = {}
_oi_changes = {}


def get_open_interest_signal(symbol):
    """
    Returns OI signal: BULLISH, BEARISH, SQUEEZE, or NEUTRAL
    Rising OI + Rising Price = BULLISH
    Rising OI + Falling Price = BEARISH  
    Falling OI + Rising Price = SQUEEZE (short squeeze)
    Falling OI + Falling Price = WEAK
    """
    try:
        r = requests.get("https://fapi.binance.com/futures/data/openInterestHist",
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

def write_market_state(symbol, price, change, signal, funding_rate=0.0, oi_change_pct=0.0):
    try:
        conn = psycopg2.connect(**DB); cur = conn.cursor()
        cur.execute("DELETE FROM market_state_latest WHERE symbol=%s", [symbol])
        cur.execute("INSERT INTO market_state_latest (symbol, price, change_24h, signal, funding_rate, oi_change_pct, updated_at) VALUES (%s,%s,%s,%s,%s,%s,NOW())", [symbol, price, change, signal, funding_rate, oi_change_pct])
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
                fr = _funding_rates.get(symbol, 0.0)
                oi = _oi_changes.get(symbol, 0.0)
                write_market_state(symbol, price, change, 'HOLD', fr, oi)
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
                    oi_change = get_open_interest_signal(symbol)
                    _oi_changes[symbol] = oi_change
                    log.info(f"{symbol} OI change: {oi_change:.4f}%")
                except Exception as e:
                    log.warning(f"OI {symbol}: {e}")
            for symbol in CRYPTO:
                try:
                    fr = get_funding_rate(symbol)
                    if fr != 0:
                        _funding_rates[symbol] = fr
                        conn = psycopg2.connect(**DB); cur = conn.cursor()
                        cur.execute("UPDATE market_state_latest SET funding_rate=%s WHERE symbol=%s", [fr, symbol])
                        conn.commit(); cur.close(); conn.close()
                        log.info(f"{symbol} funding rate: {fr:.4f}%")
                except Exception as e:
                    log.warning(f"Funding rate {symbol}: {e}")
            stock_timer = 60
        stock_timer -= 5
        time.sleep(5)

if __name__ == '__main__':
    main()
