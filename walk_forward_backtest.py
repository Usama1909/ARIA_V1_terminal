# walk_forward_backtest.py - Improved Walk-Forward Backtester
# Uses hourly data for more trades per window
# No lookahead bias - true out-of-sample testing

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

SYMBOLS = ['BTC', 'ETH', 'AAPL', 'NVDA', 'TSLA', 'GLD']
YF_MAP = {
    'BTC': 'BTC-USD', 'ETH': 'ETH-USD',
    'AAPL': 'AAPL', 'NVDA': 'NVDA',
    'TSLA': 'TSLA', 'GLD': 'GLD'
}

def fetch_data(symbol, period='60d', interval='1h', override_interval=None):
    if override_interval:
        interval = override_interval
    ticker = yf.Ticker(YF_MAP[symbol])
    df = ticker.history(period=period, interval=interval)
    df = df.reset_index()
    df.columns = [c.replace(' ', '_') for c in df.columns]
    return df

def build_features(df):
    prices = df['Close']
    volume = df['Volume']

    # RSI
    delta = prices.diff()
    gain  = delta.where(delta > 0, 0).rolling(14).mean()
    loss  = -delta.where(delta < 0, 0).rolling(14).mean()
    rsi   = 100 - (100 / (1 + gain / loss))

    # MACD
    ema_fast = prices.ewm(span=12).mean()
    ema_slow = prices.ewm(span=26).mean()
    macd     = ema_fast - ema_slow
    signal   = macd.ewm(span=9).mean()
    macd_hist = macd - signal

    # Bollinger
    ma_20    = prices.rolling(20).mean()
    std_20   = prices.rolling(20).std()
    bb_upper = ma_20 + std_20 * 2
    bb_lower = ma_20 - std_20 * 2
    bb_pos   = (prices - bb_lower) / (bb_upper - bb_lower + 1e-10)

    # ATR
    high = df['High']
    low  = df['Low']
    tr   = pd.concat([
        high - low,
        (high - prices.shift()).abs(),
        (low  - prices.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    # Volume momentum
    vol_ma = volume.rolling(20).mean()
    vol_ratio = volume / (vol_ma + 1e-10)

    # Returns
    ret_1h  = prices.pct_change(1)
    ret_4h  = prices.pct_change(4)
    ret_24h = prices.pct_change(24)

    feat = pd.DataFrame({
        'price':    prices,
        'rsi':      rsi,
        'macd':     macd,
        'macd_hist': macd_hist,
        'bb_pos':   bb_pos,
        'atr':      atr,
        'vol_ratio': vol_ratio,
        'ret_1h':   ret_1h,
        'ret_4h':   ret_4h,
        'ret_24h':  ret_24h,
    }).dropna()

    return feat

def generate_signal(row):
    score = 0

    # RSI signals
    if row['rsi'] < 30:   score += 2   # oversold - buy
    elif row['rsi'] < 40: score += 1
    elif row['rsi'] > 70: score -= 2   # overbought - sell
    elif row['rsi'] > 60: score -= 1

    # MACD histogram
    if row['macd_hist'] > 0: score += 1
    else:                    score -= 1

    # Bollinger position
    if row['bb_pos'] < 0.2:  score += 2  # near lower band - buy
    elif row['bb_pos'] > 0.8: score -= 2  # near upper band - sell

    # Volume confirmation
    if row['vol_ratio'] > 1.5: score = int(score * 1.3)

    # Momentum
    if row['ret_4h'] > 0.02:  score += 1
    elif row['ret_4h'] < -0.02: score -= 1

    if score >= 2:   return 1   # BUY
    elif score <= -2: return -1  # SELL
    return 0  # HOLD

def walk_forward_backtest(symbol, n_windows=8):
    print(f"\n{'='*50}")
    print(f"Walk-Forward Backtest: {symbol}")

    df   = fetch_data(symbol, period='60d', interval='1h')
    feat = build_features(df)

    if len(feat) < 100:
        print(f"  Not enough data for {symbol}")
        return None

    window_size = len(feat) // n_windows
    all_results = []

    for w in range(n_windows - 1):
        train_end  = (w + 1) * window_size
        test_start = train_end
        test_end   = test_start + window_size

        if test_end > len(feat):
            break

        test_data = feat.iloc[test_start:test_end].copy()

        # Simulate trading
        balance     = 10000.0
        position    = 0.0
        entry_price = 0.0
        trades      = []

        for i in range(len(test_data)):
            row   = test_data.iloc[i]
            price = row['price']
            sig   = generate_signal(row)

            if sig == 1 and position == 0:
                position    = (balance * 0.95) / price
                entry_price = price
                balance    -= position * price

            elif sig == -1 and position > 0:
                proceeds = position * price
                pnl_pct  = (price - entry_price) / entry_price * 100
                balance += proceeds
                trades.append({'pnl_pct': pnl_pct, 'profitable': pnl_pct > 0})
                position = 0.0

        # Close any open position
        if position > 0:
            price    = test_data.iloc[-1]['price']
            pnl_pct  = (price - entry_price) / entry_price * 100
            balance += position * price
            trades.append({'pnl_pct': pnl_pct, 'profitable': pnl_pct > 0})

        if len(trades) < 2:
            continue

        total_return = (balance - 10000) / 10000 * 100
        win_rate     = sum(1 for t in trades if t['profitable']) / len(trades) * 100
        avg_trade    = np.mean([t['pnl_pct'] for t in trades])

        status = "✅" if total_return > 0 else "❌"
        print(f"  Window {w+1}: {total_return:+.2f}% | WR: {win_rate:.0f}% | Trades: {len(trades)} | Avg: {avg_trade:+.2f}% {status}")

        all_results.append({
            'window': w+1,
            'return': total_return,
            'win_rate': win_rate,
            'trades': len(trades)
        })

    if not all_results:
        print(f"  Not enough trades generated")
        return None

    avg_return  = np.mean([r['return'] for r in all_results])
    avg_wr      = np.mean([r['win_rate'] for r in all_results])
    total_trades = sum(r['trades'] for r in all_results)
    profitable_windows = sum(1 for r in all_results if r['return'] > 0)
    edge = avg_wr >= 55 and avg_return > 0

    print(f"  {'─'*44}")
    print(f"  SUMMARY:")
    print(f"  Profitable windows: {profitable_windows}/{len(all_results)}")
    print(f"  Total trades:       {total_trades}")
    print(f"  Average return:     {avg_return:+.2f}%")
    print(f"  Average win rate:   {avg_wr:.1f}%")
    print(f"  Edge confirmed:     {'YES ✅' if edge else 'NO ❌'}")

    return {
        'symbol': symbol,
        'avg_return': avg_return,
        'avg_win_rate': avg_wr,
        'total_trades': total_trades,
        'profitable_windows': profitable_windows,
        'total_windows': len(all_results),
        'edge': edge
    }

if __name__ == '__main__':
    print("="*50)
    print("ARIA WALK-FORWARD BACKTESTER v2")
    print("Hourly data | 8 windows | No lookahead bias")
    print("="*50)

    results = []
    for symbol in SYMBOLS:
        r = walk_forward_backtest(symbol)
        if r:
            results.append(r)

    print(f"\n{'='*50}")
    print("FINAL EDGE ANALYSIS:")
    confirmed = [r for r in results if r['edge']]
    print(f"Assets with confirmed edge: {len(confirmed)}/{len(results)}")
    print()
    for r in results:
        edge_str = "✅" if r['edge'] else "❌"
        print(f"  {r['symbol']:5} | return={r['avg_return']:+.2f}% | wr={r['avg_win_rate']:.1f}% | trades={r['total_trades']} | {edge_str}")

    print(f"\nBuy-and-Hold Benchmark:")
    for symbol in ['BTC', 'TSLA', 'GLD']:
        try:
            df = fetch_data(symbol, period='60d', interval='1d')
            bh = (df['Close'].iloc[-1] - df['Close'].iloc[0]) / df['Close'].iloc[0] * 100
            print(f"  {symbol:5} buy-and-hold: {bh:+.2f}%")
        except:
            pass
