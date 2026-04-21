# aria_trading_env.py - Custom ARIA Trading Environment
# Built on Gymnasium + Stable-Baselines3
# Uses ARIA's 27 features + macro + geo signals
# v2 - Improved reward function

import numpy as np
import pandas as pd
import yfinance as yf
import gymnasium as gym
from gymnasium import spaces
import requests
import warnings
warnings.filterwarnings('ignore')

# ── CONFIG ────────────────────────────────────────────────
ARIA_URL = "https://web-production-548c0.up.railway.app"
INITIAL_BALANCE = 10000.0
MAX_POSITION_PCT = 0.20  # max 20% in one trade
TRANSACTION_COST = 0.001  # 0.1% per trade

# ── FETCH TRAINING DATA ───────────────────────────────────
def fetch_training_data(symbol, period='2y', interval='1h'):
    yf_map = {
        'BTC': 'BTC-USD', 'ETH': 'ETH-USD',
        'AAPL': 'AAPL', 'NVDA': 'NVDA',
        'TSLA': 'TSLA', 'GLD': 'GLD'
    }
    print(f"  Fetching {symbol} training data ({period})...")
    ticker = yf.Ticker(yf_map[symbol])
    df = ticker.history(period=period, interval=interval)
    df = df.reset_index()
    df.columns = [c.replace(' ', '_') for c in df.columns]
    print(f"  Got {len(df)} candles for {symbol}")
    return df

# ── BUILD FEATURES ────────────────────────────────────────
def build_features(df):
    prices = df['Close']
    volume = df['Volume']
    high   = df['High']
    low    = df['Low']

    tr1 = high - low
    tr2 = abs(high - prices.shift(1))
    tr3 = abs(low - prices.shift(1))
    atr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean()

    delta = prices.diff()
    gain  = delta.where(delta > 0, 0).rolling(14).mean()
    loss  = -delta.where(delta < 0, 0).rolling(14).mean()
    rsi   = 100 - (100 / (1 + gain / loss))

    ema_fast   = prices.ewm(span=12).mean()
    ema_slow   = prices.ewm(span=26).mean()
    macd       = ema_fast - ema_slow
    macd_signal= macd.ewm(span=9).mean()
    macd_hist  = macd - macd_signal

    ma_20    = prices.rolling(20).mean()
    std_20   = prices.rolling(20).std()
    bb_upper = ma_20 + (std_20 * 2)
    bb_lower = ma_20 - (std_20 * 2)
    ma_50    = prices.rolling(50).mean()

    volatility    = prices.pct_change().rolling(10).std()
    bb_position   = (prices - bb_lower) / (bb_upper - bb_lower)
    ma_distance   = (ma_20 - ma_50) / ma_50
    price_change_5 = prices.pct_change(5)
    price_change_10= prices.pct_change(10)
    price_change_24= prices.pct_change(24)
    rsi_momentum  = rsi.diff()
    volume_ratio  = volume / volume.rolling(20).mean()
    volume_trend  = volume.rolling(5).mean() / volume.rolling(20).mean()

    prices_4h = prices.rolling(4).mean()
    delta_4h  = prices_4h.diff()
    gain_4h   = delta_4h.where(delta_4h > 0, 0).rolling(14).mean()
    loss_4h   = -delta_4h.where(delta_4h < 0, 0).rolling(14).mean()
    rsi_4h    = 100 - (100 / (1 + gain_4h / loss_4h))

    high_24 = prices.rolling(24).max()
    low_24  = prices.rolling(24).min()
    dist_from_high = (prices - high_24) / high_24
    dist_from_low  = (prices - low_24) / low_24
    range_24       = high_24 - low_24
    range_position = np.where(range_24 > 0, (prices - low_24) / range_24, 0.5)

    candle_range     = (high - low) / prices
    candle_close_pos = (prices - low) / (high - low + 1e-9)
    upper_wick = (high - prices) / (high - low + 1e-9)
    lower_wick = (prices - low)  / (high - low + 1e-9)

    adx_proxy  = abs(ma_distance) / volatility.replace(0, np.nan)
    z_score    = (prices - prices.rolling(20).mean()) / prices.rolling(20).std()
    momentum_5 = prices / prices.shift(5) - 1
    momentum_10= prices / prices.shift(10) - 1
    atr_pct    = atr / prices

    pct_change   = prices.pct_change()
    buy_vol_frac = np.where(pct_change > 0.001, 0.9,
                   np.where(pct_change < -0.001, 0.1, 0.5))
    buy_volume   = volume * buy_vol_frac
    ofi          = abs(buy_volume - volume * (1 - buy_vol_frac))
    vpin_raw     = ofi.rolling(50).sum() / volume.rolling(50).sum()
    vpin_10      = vpin_raw.quantile(0.10)
    vpin_90      = vpin_raw.quantile(0.90)
    vpin_norm    = ((vpin_raw - vpin_10) / (vpin_90 - vpin_10 + 1e-9)).clip(0, 1)
    vpin_signal  = np.where(vpin_norm > 0.7, 1, np.where(vpin_norm < 0.3, -1, 0))

    features = pd.DataFrame({
        'rsi': rsi, 'macd': macd, 'macd_hist': macd_hist,
        'volatility': volatility, 'bb_position': bb_position,
        'ma_distance': ma_distance, 'price_change_5': price_change_5,
        'price_change_10': price_change_10, 'price_change_24': price_change_24,
        'rsi_momentum': rsi_momentum, 'volume_ratio': volume_ratio,
        'volume_trend': volume_trend, 'rsi_4h': rsi_4h,
        'dist_from_high': dist_from_high, 'dist_from_low': dist_from_low,
        'range_position': pd.Series(range_position, index=prices.index),
        'candle_range': candle_range,
        'candle_close_pos': pd.Series(candle_close_pos.values, index=prices.index),
        'upper_wick': pd.Series(upper_wick.values, index=prices.index),
        'lower_wick': pd.Series(lower_wick.values, index=prices.index),
        'adx_proxy': adx_proxy, 'z_score': z_score,
        'momentum_5': momentum_5, 'momentum_10': momentum_10,
        'atr_pct': atr_pct, 'vpin_norm': vpin_norm,
        'vpin_signal': pd.Series(vpin_signal, index=prices.index),
        'price': prices
    })

    return features.dropna().reset_index(drop=True)

# ── TRADING ENVIRONMENT ───────────────────────────────────
class ARIATradingEnv(gym.Env):
    def __init__(self, features_df, symbol='BTC'):
        super().__init__()
        self.features_df = features_df
        self.symbol      = symbol
        self.n_features  = 27
        self.feature_cols= [c for c in features_df.columns if c != 'price'][:27]

        self.action_space = spaces.Discrete(3)
        self.observation_space = spaces.Box(
            low=-10, high=10,
            shape=(self.n_features + 3,),
            dtype=np.float32
        )
        self.reset()

    def reset(self, seed=None):
        super().reset(seed=seed)
        self.current_step   = 50
        self.balance        = INITIAL_BALANCE
        self.position       = 0.0
        self.entry_price    = 0.0
        self.total_trades   = 0
        self.winning_trades = 0
        self.max_balance    = INITIAL_BALANCE
        self.returns        = []
        self.trade_pnls     = []
        return self._get_obs(), {}

    def _get_obs(self):
        row      = self.features_df.iloc[self.current_step]
        features = row[self.feature_cols].values.astype(np.float32)
        features = np.nan_to_num(features, nan=0.0, posinf=1.0, neginf=-1.0)
        features = np.clip(features, -10, 10)

        portfolio_state = np.array([
            self.position,
            (self.balance / INITIAL_BALANCE) - 1,
            (self.entry_price / self.features_df.iloc[self.current_step]['price'] - 1)
            if self.entry_price > 0 else 0.0
        ], dtype=np.float32)

        return np.concatenate([features, portfolio_state])

    def step(self, action):
        current_price = float(self.features_df.iloc[self.current_step]['price'])
        reward        = 0.0
        info          = {}

        if action == 1 and self.position == 0:  # BUY
            trade_amount    = self.balance * MAX_POSITION_PCT
            cost            = trade_amount * TRANSACTION_COST
            self.position   = (trade_amount - cost) / current_price
            self.balance   -= trade_amount
            self.entry_price= current_price
            self.total_trades += 1

        elif action == 2 and self.position > 0:  # SELL
            proceeds      = self.position * current_price
            cost          = proceeds * TRANSACTION_COST
            pnl           = proceeds - cost - (self.position * self.entry_price)
            self.balance += proceeds - cost
            pnl_pct       = pnl / (self.position * self.entry_price) * 100

            # ── IMPROVED REWARD FUNCTION ──
            if pnl > 0:
                self.winning_trades += 1
                reward = pnl_pct * 2.0   # double reward for wins
            else:
                reward = pnl_pct * 1.5   # 1.5x penalty for losses

            # Sharpe-style bonus
            self.trade_pnls.append(pnl_pct)
            if len(self.trade_pnls) > 10:
                mean_r = np.mean(self.trade_pnls)
                std_r  = np.std(self.trade_pnls) + 1e-9
                sharpe_bonus = mean_r / std_r
                reward += sharpe_bonus * 0.5

            # Drawdown penalty
            if self.balance > self.max_balance:
                self.max_balance = self.balance
            drawdown = (self.max_balance - self.balance) / self.max_balance
            if drawdown > 0.15:
                reward -= 20  # heavy penalty
            elif drawdown > 0.10:
                reward -= 10
            elif drawdown > 0.05:
                reward -= 3

            self.returns.append(reward)
            self.position    = 0.0
            self.entry_price = 0.0

        elif action == 0 and self.position > 0:  # HOLD with position
            unrealised_pnl = self.position * (current_price - self.entry_price)
            unrealised_pct = unrealised_pnl / (self.position * self.entry_price) * 100
            # Small reward for holding winners, small penalty for holding losers
            reward = unrealised_pct * 0.001

        self.current_step += 1
        terminated = self.current_step >= len(self.features_df) - 1
        truncated  = False

        if terminated:
            total_value  = self.balance + (self.position * current_price)
            final_return = (total_value - INITIAL_BALANCE) / INITIAL_BALANCE * 100
            win_rate     = self.winning_trades / max(self.total_trades, 1)

            # Final bonus based on overall performance
            reward += final_return * 0.5
            reward += win_rate * 20

            # Sharpe ratio bonus at end
            if len(self.trade_pnls) > 5:
                sharpe = np.mean(self.trade_pnls) / (np.std(self.trade_pnls) + 1e-9)
                reward += sharpe * 5

            info = {
                'final_balance': total_value,
                'total_return':  final_return,
                'total_trades':  self.total_trades,
                'win_rate':      win_rate
            }

        return self._get_obs(), reward, terminated, truncated, info

    def render(self):
        current_price = float(self.features_df.iloc[self.current_step]['price'])
        total_value   = self.balance + (self.position * current_price)
        print(f"Step {self.current_step} | Price ${current_price:.2f} | "
              f"Balance ${self.balance:.2f} | Total ${total_value:.2f}")


if __name__ == "__main__":
    print("Testing ARIA Trading Environment v2...")
    df   = fetch_training_data('BTC', period='60d', interval='1h')
    feat = build_features(df)
    print(f"Features shape: {feat.shape}")
    env  = ARIATradingEnv(feat, symbol='BTC')
    obs, _ = env.reset()
    print(f"Observation shape: {obs.shape}")
    print(f"Action space: {env.action_space}")
    print("Environment v2 OK!")
