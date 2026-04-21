#!/usr/bin/env python3
"""
ARIA Market Data Updater
Fetches prices from Binance + Yahoo, writes to market_state_latest.
Agent loop reads from this table — never calls external APIs directly.
PATCH: Added DXY collection. Fixed stock change_24h scale (now correct %).
"""
import time, psycopg2, logging, requests
from datetime import datetime
logging.basicConfig(level=logging.INFO, format='%(asctime)s [MARKET] %(message)s')
log = logging.getLogger()
DB = {'host':'localhost','port':5432,'dbname':'aria_db',
      'user':'postgres','password':'aria_secure_2026'}
BINANCE_TESTNET = "https://testnet.binance.vision/api"
CRYPTO  = ['BTC', 'ETH']
STOCKS  = ['AAPL', 'NVDA', 'TSLA', 'GLD']

def get_crypto_price(symbol):
    try:
        r = requests.get(f"{BINANCE_TESTNET}/v3/ticker/24hr",
                        params={'symbol': f'{symbol}USDT'}, timeout=5)
        d = r.json()
        return float(d.get('lastPrice', 0)), float(d.get('priceChangePercent', 0))
    except:
        return 0.0, 0.0

def get_stock_price(symbol):
    """
    Returns (price, change_pct) where change_pct is a proper percentage.
    e.g. -0.38% not -0.00383
    Uses fast_info for speed, falls back to history.
    """
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        # Try fast_info first — single HTTP call
        fi = t.fast_info
        price = float(fi.get('last_price') or fi.get('previousClose') or 0)
        prev  = float(fi.get('previous_close') or fi.get('regularMarketPreviousClose') or 0)
        if price > 0 and prev > 0:
            change = ((price - prev) / prev) * 100  # correct percentage
            return price, round(change, 4)
    except:
        pass
    # Fallback to history
    try:
        import yfinance as yf
        hist = yf.Ticker(symbol).history(period='2d')
        if len(hist) >= 2:
            price = float(hist['Close'].iloc[-1])
            prev  = float(hist['Close'].iloc[-2])
            change = ((price - prev) / prev * 100) if prev > 0 else 0.0
            return price, round(change, 4)
        elif len(hist) == 1:
            return float(hist['Close'].iloc[-1]), 0.0
    except:
        pass
    return 0.0, 0.0

def get_dxy():
    """
    Fetch DXY (US Dollar Index) from Yahoo Finance.
    Ticker: DX-Y.NYB
    Returns (price, change_pct)
    """
    try:
        import yfinance as yf
        t    = yf.Ticker('DX-Y.NYB')
        hist = t.history(period='2d')
        if len(hist) >= 2:
            price  = float(hist['Close'].iloc[-1])
            prev   = float(hist['Close'].iloc[-2])
            change = ((price - prev) / prev * 100) if prev > 0 else 0.0
            return price, round(change, 4)
        elif len(hist) == 1:
            return float(hist['Close'].iloc[-1]), 0.0
    except Exception as e:
        log.warning(f"DXY fetch failed: {e}")
    return 0.0, 0.0

def write_market_state(symbol, price, change, signal):
    conn = psycopg2.connect(**DB)
    cur  = conn.cursor()
    cur.execute("DELETE FROM market_state_latest WHERE symbol=%s", [symbol])
    cur.execute("""INSERT INTO market_state_latest
        (symbol, price, change_24h, signal, updated_at)
        VALUES (%s,%s,%s,%s,NOW())""",
        [symbol, price, change, signal])
    conn.commit(); cur.close(); conn.close()

def write_price_data(symbol, price, change):
    """Write to price_data table for DB health monitor and DXY tracking."""
    try:
        conn = psycopg2.connect(**DB)
        cur  = conn.cursor()
        cur.execute("""INSERT INTO price_data (symbol, price, volume, source)
            VALUES (%s,%s,%s,%s)""", [symbol, price, 0, 'yahoo_macro'])
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.warning(f"write_price_data failed for {symbol}: {e}")

def main():
    log.info("ARIA Market Updater started")
    log.info("PATCH: DXY collection added, stock change_24h fixed")
    while True:
        # ── Crypto ──────────────────────────────────────────
        for symbol in CRYPTO:
            try:
                price, change = get_crypto_price(symbol)
                if price > 0:
                    write_market_state(symbol, price, change, 'HOLD')
                    log.info(f"{symbol}: ${price:.2f} ({change:+.2f}%)")
            except Exception as e:
                log.error(f"{symbol}: {e}")

        # ── Stocks ──────────────────────────────────────────
        for symbol in STOCKS:
            try:
                price, change = get_stock_price(symbol)
                if price > 0:
                    write_market_state(symbol, price, change, 'HOLD')
                    log.info(f"{symbol}: ${price:.2f} ({change:+.2f}%)")
            except Exception as e:
                log.error(f"{symbol}: {e}")

        # ── DXY ─────────────────────────────────────────────
        try:
            dxy_price, dxy_change = get_dxy()
            if dxy_price > 0:
                write_market_state('DXY', dxy_price, dxy_change, 'HOLD')
                write_price_data('DXY', dxy_price, dxy_change)
                log.info(f"DXY: {dxy_price:.2f} ({dxy_change:+.2f}%)")
            else:
                log.warning("DXY fetch returned 0 — skipping write")
        except Exception as e:
            log.error(f"DXY: {e}")

        log.info("Market state updated — sleeping 60s")
        time.sleep(60)

if __name__ == '__main__':
    main()
