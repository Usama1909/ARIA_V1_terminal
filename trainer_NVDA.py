# aria_ppo_trainer.py - ARIA PPO Agent Trainer v2
# 2 Million training steps + improved callbacks

import numpy as np
import os
import requests
from datetime import datetime
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from aria_trading_env import ARIATradingEnv, fetch_training_data, build_features

# ── CONFIG ────────────────────────────────────────────────
ARIA_URL    = "https://web-production-548c0.up.railway.app"
MODEL_PATH  = "aria_ppo_nvda.zip"
SYMBOL      = "NVDA"
TIMESTEPS   = 2000000  # 2 million steps

# ── CALLBACK ──────────────────────────────────────────────
class ARIACallback(BaseCallback):
    def __init__(self, verbose=0):
        super().__init__(verbose)
        self.episode_rewards = []
        self.best_reward     = -np.inf
        self.best_win_rate   = 0.0

    def _on_step(self):
        if self.locals.get('dones', [False])[0]:
            info = self.locals.get('infos', [{}])[0]
            if 'final_balance' in info:
                ret    = info.get('total_return', 0)
                trades = info.get('total_trades', 0)
                wr     = info.get('win_rate', 0)
                self.episode_rewards.append(ret)

                if ret > self.best_reward:
                    self.best_reward = ret
                    print(f"  New best return: {ret:.2f}% | trades: {trades} | win rate: {wr*100:.1f}%")

                if wr > self.best_win_rate:
                    self.best_win_rate = wr

                if len(self.episode_rewards) % 10 == 0:
                    avg_ret = np.mean(self.episode_rewards[-10:])
                    self._report_to_aria(avg_ret, trades, wr)

        return True

    def _report_to_aria(self, avg_return, trades, win_rate):
        try:
            requests.post(f"{ARIA_URL}/agent/report", json={
                'agent_id':   'agent_ppo_btc',
                'agent_type': 'PPO',
                'symbol':     'BTC',
                'action':     'TRAINING',
                'confidence': min(abs(avg_return) / 10, 0.99),
                'reasoning':  f"PPO v2 training: avg={avg_return:.2f}% wr={win_rate*100:.1f}% steps={self.num_timesteps:,}",
                'pnl_today':  avg_return
            }, timeout=5)
        except:
            pass

# ── TRAIN ─────────────────────────────────────────────────
def train():
    print("="*60)
    print(f"ARIA PPO TRAINER v2 - {SYMBOL}")
    print(f"Training steps: {TIMESTEPS:,}")
    print(f"Reward: Sharpe-adjusted + drawdown penalty")
    print("="*60)

    df   = fetch_training_data(SYMBOL, period='2y', interval='1h')
    feat = build_features(df)
    print(f"Training data: {len(feat)} samples")

    split      = int(len(feat) * 0.8)
    train_feat = feat.iloc[:split].reset_index(drop=True)
    test_feat  = feat.iloc[split:].reset_index(drop=True)
    print(f"Train: {len(train_feat)} | Test: {len(test_feat)}")

    env = ARIATradingEnv(train_feat, symbol=SYMBOL)

    model = PPO(
        'MlpPolicy',
        env,
        learning_rate   = 1e-4,
        n_steps         = 2048,
        batch_size      = 128,
        n_epochs        = 15,
        gamma           = 0.99,
        gae_lambda      = 0.95,
        clip_range      = 0.2,
        ent_coef        = 0.01,
        verbose         = 0,
        policy_kwargs   = dict(net_arch=[256, 256, 128])
    )

    print(f"\nStarting PPO v2 training ({TIMESTEPS:,} steps)...")
    print("This will take ~2 hours. Running in background.")
    callback = ARIACallback()
    model.learn(total_timesteps=TIMESTEPS, callback=callback, progress_bar=True)

    model.save(MODEL_PATH)
    print(f"\nModel saved: {MODEL_PATH}")

    print("\nTesting on unseen data...")
    test_env = ARIATradingEnv(test_feat, symbol=SYMBOL)
    obs, _   = test_env.reset()
    done     = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, info = test_env.step(action)
        done = terminated or truncated

    print(f"\n{'='*60}")
    print(f"FINAL TEST RESULTS:")
    print(f"  Final Balance:  ${info.get('final_balance', 0):.2f}")
    print(f"  Total Return:   {info.get('total_return', 0):.2f}%")
    print(f"  Total Trades:   {info.get('total_trades', 0)}")
    print(f"  Win Rate:       {info.get('win_rate', 0)*100:.1f}%")
    print(f"  Best Win Rate During Training: {callback.best_win_rate*100:.1f}%")
    print(f"{'='*60}")

    try:
        final_return = info.get('total_return', 0)
        requests.post(f"{ARIA_URL}/agent/report", json={
            'agent_id':   'agent_ppo_btc',
            'agent_type': 'PPO',
            'symbol':     'BTC',
            'action':     'TRAINED',
            'confidence': 0.90,
            'reasoning':  f"PPO v2 complete. Return={final_return:.2f}% Trades={info.get('total_trades',0)} WinRate={info.get('win_rate',0)*100:.1f}%",
            'pnl_today':  final_return
        }, timeout=5)
    except:
        pass

    return model

if __name__ == "__main__":
    train()
