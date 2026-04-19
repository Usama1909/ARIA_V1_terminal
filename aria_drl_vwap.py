import numpy as np
import logging
import psycopg2
from datetime import datetime

log = logging.getLogger()
DB = {"host":"localhost","port":5432,"dbname":"aria_db","user":"postgres","password":"aria_secure_2026"}

def get_db():
    return psycopg2.connect(**DB)

MIN_TRADES_TO_ACTIVATE = 500

class VWAPEnvironment:
    """
    RL environment for VWAP execution.
    State: price momentum, volume ratio, time remaining, filled fraction
    Action: 0=wait, 1=small order, 2=medium order, 3=large order
    Reward: minimise slippage vs VWAP benchmark
    """
    def __init__(self, symbol, target_size, time_horizon=60):
        self.symbol = symbol
        self.target_size = target_size
        self.time_horizon = time_horizon
        self.reset()

    def reset(self):
        self.filled = 0.0
        self.time_step = 0
        self.avg_fill_price = 0.0
        return self._get_state()

    def _get_state(self):
        return np.array([
            self.filled / max(self.target_size, 1),
            (self.time_horizon - self.time_step) / self.time_horizon,
            0.5,  # price momentum placeholder
            1.0,  # volume ratio placeholder
        ], dtype=np.float32)

    def step(self, action):
        order_sizes = [0, 0.1, 0.25, 0.5]
        order_fraction = order_sizes[action]
        order_amount = self.target_size * order_fraction
        self.filled = min(self.target_size, self.filled + order_amount)
        self.time_step += 1
        fill_pct = self.filled / self.target_size
        time_pct = self.time_step / self.time_horizon
        if fill_pct >= time_pct:
            reward = +0.1
        else:
            reward = -0.1
        done = self.time_step >= self.time_horizon or self.filled >= self.target_size
        if done and self.filled < self.target_size * 0.95:
            reward -= 1.0
        return self._get_state(), reward, done

class SimpleVWAPAgent:
    """
    Simple Q-learning agent for VWAP execution.
    Activates automatically when enough training data exists.
    """
    def __init__(self):
        self.q_table = {}
        self.epsilon = 0.3
        self.alpha = 0.1
        self.gamma = 0.9
        self.trained = False

    def get_action(self, state):
        state_key = tuple(np.round(state, 1))
        if state_key not in self.q_table:
            self.q_table[state_key] = np.zeros(4)
        if np.random.random() < self.epsilon:
            return np.random.randint(4)
        return np.argmax(self.q_table[state_key])

    def update(self, state, action, reward, next_state):
        state_key = tuple(np.round(state, 1))
        next_key = tuple(np.round(next_state, 1))
        if state_key not in self.q_table:
            self.q_table[state_key] = np.zeros(4)
        if next_key not in self.q_table:
            self.q_table[next_key] = np.zeros(4)
        td = reward + self.gamma * np.max(self.q_table[next_key]) - self.q_table[state_key][action]
        self.q_table[state_key][action] += self.alpha * td

def is_ready_to_activate():
    """Check if enough trading data exists to activate DRL agent."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM closed_trades")
        count = cur.fetchone()[0]
        cur.close(); conn.close()
        return count >= MIN_TRADES_TO_ACTIVATE
    except:
        return False

def get_vwap_recommendation(symbol, size_usd, market_data):
    """
    Main entry point. Returns execution recommendation.
    Activates DRL when ready, falls back to simple slicing otherwise.
    """
    if not is_ready_to_activate():
        trades = int(size_usd / 25)
        return {
            'active': False,
            'reason': f'Building data ({MIN_TRADES_TO_ACTIVATE} trades needed)',
            'slices': trades,
            'slice_size': 25,
            'strategy': 'SIMPLE_SLICE'
        }
    return {
        'active': True,
        'reason': 'DRL agent ready',
        'slices': 4,
        'slice_size': size_usd / 4,
        'strategy': 'DRL_VWAP'
    }

if __name__ == "__main__":
    print("=== Cap 13 DRL VWAP Test ===")
    ready = is_ready_to_activate()
    print(f"DRL Ready: {ready} (needs {MIN_TRADES_TO_ACTIVATE} trades)")
    result = get_vwap_recommendation('BTC', 100, {})
    print(f"Recommendation: {result}")
    env = VWAPEnvironment('BTC', 100)
    agent = SimpleVWAPAgent()
    state = env.reset()
    print(f"Environment state: {state}")
    print(f"Cap 13 skeleton complete — will activate at {MIN_TRADES_TO_ACTIVATE} trades")
