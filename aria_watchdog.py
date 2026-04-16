#!/usr/bin/env python3
"""ARIA Self-Healing Watchdog — monitors correct v5 services only"""
import subprocess, time, psycopg2, logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [WATCHDOG] %(message)s')
log = logging.getLogger()
DB = {'host':'localhost','port':5432,'dbname':'aria_db','user':'postgres','password':'aria_secure_2026'}

# Only monitor these exact scripts
SERVICES = {
    'agent_loop_v5':        '/root/agent_loop_v5.py',
    'aria_sentiment':       '/root/aria_sentiment_service.py',
    'aria_market':          '/root/aria_market_updater.py',
    'aria_execution':       '/root/aria_execution_worker.py',
    'aria_positions':       '/root/aria_positions_service.py',
    'aria_meta':            '/root/aria_meta_controller.py',
    'aria_learning':        '/root/aria_learning_loop.py',
}

restart_counts = {}

def is_running(script_path):
    result = subprocess.run(['pgrep', '-f', script_path], capture_output=True)
    return result.returncode == 0

def start_service(name, script_path):
    import os
    os.makedirs('/root/logs', exist_ok=True)
    log_file = f'/root/logs/{name}.log'
    subprocess.Popen(['python3', script_path],
                    stdout=open(log_file, 'a'),
                    stderr=open(log_file, 'a'))
    log.info(f"Started {name}")

def main():
    log.info("ARIA Watchdog started — monitoring v5 services only")
    while True:
        for name, script in SERVICES.items():
            if not is_running(script):
                count = restart_counts.get(name, 0)
                if count < 3:
                    log.warning(f"{name} down — restarting ({count+1}/3)")
                    start_service(name, script)
                    restart_counts[name] = count + 1
                else:
                    log.error(f"{name} max restarts reached")
            else:
                restart_counts[name] = 0
        time.sleep(60)

if __name__ == '__main__':
    main()
