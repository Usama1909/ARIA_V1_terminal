# aria_collector.py - ARIA Live Data Collector
# Collects real-time price data into PostgreSQL
# Binance WebSocket for crypto, Yahoo Finance for stocks

import asyncio
import json
import time
import websockets
import psycopg2
import yfinance as yf
import requests
import threading
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# ── DATABASE CONFIG ───────────────────────────────────────
DB_CONFIG = {
    'host':     'localhost',
    'database': 'aria_db',
    'user':     'aria',
    'password': 'aria_secure_2026',
    'port':     5432
}

# ── CONNECT TO DATABASE ───────────────────────────────────
def get_db():
    return psycopg2.connect(**DB_CONFIG)

def save_price(symbol, price, volume, source):
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO price_data (symbol, price, volume, source) VALUES (%s, %s, %s, %s)",
            (symbol, price, volume, source)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"  DB error: {e}")

# ── BINANCE WEBSOCKET (BTC + ETH real-time) ───────────────
async def binance_collector():
    uri = "wss://stream.binance.com:9443/stream?streams=btcusdt@trade/ethusdt@trade"
    print("  Binance WebSocket connecting...")
    reconnect_delay = 5
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print("  Binance WebSocket connected!")
                reconnect_delay = 5
                while True:
                    msg  = await ws.recv()
                    data = json.loads(msg)
                    stream = data.get('stream', '')
                    trade  = data.get('data', {})
                    price  = float(trade.get('p', 0))
                    volume = float(trade.get('q', 0))
                    if 'btcusdt' in stream:
                        save_price('BTC', price, volume, 'binance')
                    elif 'ethusdt' in stream:
                        save_price('ETH', price, volume, 'binance')
        except Exception as e:
            print(f"  Binance error: {e}. Reconnecting in {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 60)

# ── YAHOO FINANCE COLLECTOR (stocks every 1 min) ──────────
def yahoo_collector():
    symbols = {
        'AAPL': 'AAPL',
        'NVDA': 'NVDA',
        'TSLA': 'TSLA',
        'GLD':  'GLD'
    }
    print("  Yahoo Finance collector starting...")
    while True:
        for symbol, ticker in symbols.items():
            try:
                t    = yf.Ticker(ticker)
                data = t.history(period='1d', interval='1m')
                if len(data) > 0:
                    price  = float(data['Close'].iloc[-1])
                    volume = float(data['Volume'].iloc[-1])
                    save_price(symbol, price, volume, 'yahoo')
                    print(f"  Yahoo: {symbol} = ${price:.2f}")
            except Exception as e:
                print(f"  Yahoo {symbol} error: {e}")
        time.sleep(60)

# ── FRED MACRO COLLECTOR (every hour) ────────────────────
def macro_collector():
    print("  FRED macro collector starting...")
    while True:
        try:
            # VIX
            vix = yf.Ticker('^VIX')
            vix_data = vix.history(period='1d', interval='1m')
            if len(vix_data) > 0:
                vix_price = float(vix_data['Close'].iloc[-1])
                save_price('VIX', vix_price, 0, 'yahoo_macro')
                print(f"  Macro: VIX = {vix_price:.2f}")

            # DXY
            dxy = yf.Ticker('DX-Y.NYB')
            dxy_data = dxy.history(period='1d', interval='1m')
            if len(dxy_data) > 0:
                dxy_price = float(dxy_data['Close'].iloc[-1])
                save_price('DXY', dxy_price, 0, 'yahoo_macro')
                print(f"  Macro: DXY = {dxy_price:.2f}")

        except Exception as e:
            print(f"  Macro error: {e}")
        time.sleep(3600)

# ── STATS REPORTER ────────────────────────────────────────
def stats_reporter():
    while True:
        try:
            conn = get_db()
            cur  = conn.cursor()
            cur.execute("SELECT symbol, COUNT(*), MAX(timestamp) FROM price_data GROUP BY symbol ORDER BY symbol")
            rows = cur.fetchall()
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Database stats:")
            for row in rows:
                print(f"  {row[0]}: {row[1]} records, last: {row[2]}")
            cur.close()
            conn.close()
        except Exception as e:
            print(f"  Stats error: {e}")
        time.sleep(300)

# ── MAIN ──────────────────────────────────────────────────
def main():
    print("="*60)
    print("ARIA LIVE DATA COLLECTOR")
    print("Sources: Binance WebSocket + Yahoo Finance + FRED")
    print("="*60)

    # Start Yahoo + macro in background threads
    threading.Thread(target=yahoo_collector, daemon=True).start()
    threading.Thread(target=macro_collector, daemon=True).start()
    threading.Thread(target=stats_reporter,  daemon=True).start()

    # Run Binance WebSocket in main event loop
    print("Starting collectors...")
    asyncio.run(binance_collector())

if __name__ == "__main__":
    main()
