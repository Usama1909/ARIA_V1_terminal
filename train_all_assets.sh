#!/bin/bash
cd /root
source /root/aria-env/bin/activate

echo "Starting PPO training for all 6 assets..."

# Train each asset in background
sed 's/SYMBOL      = "BTC"/SYMBOL      = "BTC"/' aria_ppo_trainer.py > trainer_BTC.py
sed 's/SYMBOL      = "BTC"/SYMBOL      = "ETH"/' aria_ppo_trainer.py > trainer_ETH.py
sed 's/SYMBOL      = "BTC"/SYMBOL      = "AAPL"/' aria_ppo_trainer.py > trainer_AAPL.py
sed 's/SYMBOL      = "BTC"/SYMBOL      = "NVDA"/' aria_ppo_trainer.py > trainer_NVDA.py
sed 's/SYMBOL      = "BTC"/SYMBOL      = "TSLA"/' aria_ppo_trainer.py > trainer_TSLA.py
sed 's/SYMBOL      = "BTC"/SYMBOL      = "GLD"/' aria_ppo_trainer.py > trainer_GLD.py

# Also update model paths
sed -i 's/MODEL_PATH  = "aria_ppo_btc.zip"/MODEL_PATH  = "aria_ppo_btc.zip"/' trainer_BTC.py
sed -i 's/MODEL_PATH  = "aria_ppo_btc.zip"/MODEL_PATH  = "aria_ppo_eth.zip"/' trainer_ETH.py
sed -i 's/MODEL_PATH  = "aria_ppo_btc.zip"/MODEL_PATH  = "aria_ppo_aapl.zip"/' trainer_AAPL.py
sed -i 's/MODEL_PATH  = "aria_ppo_btc.zip"/MODEL_PATH  = "aria_ppo_nvda.zip"/' trainer_NVDA.py
sed -i 's/MODEL_PATH  = "aria_ppo_btc.zip"/MODEL_PATH  = "aria_ppo_tsla.zip"/' trainer_TSLA.py
sed -i 's/MODEL_PATH  = "aria_ppo_btc.zip"/MODEL_PATH  = "aria_ppo_gld.zip"/' trainer_GLD.py

# Start all training jobs
nohup python -u trainer_ETH.py  > log_ETH.txt  2>&1 &
nohup python -u trainer_AAPL.py > log_AAPL.txt 2>&1 &
nohup python -u trainer_NVDA.py > log_NVDA.txt 2>&1 &
nohup python -u trainer_TSLA.py > log_TSLA.txt 2>&1 &
nohup python -u trainer_GLD.py  > log_GLD.txt  2>&1 &

echo "All 6 training jobs started!"
echo "Check progress with: grep 'New best' log_ETH.txt"
