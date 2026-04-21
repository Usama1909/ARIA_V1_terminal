import requests
import json
import time

ARIA_URL = "https://web-production-548c0.up.railway.app"
USERS = ["aria-agent-system", "aria-agent-v4"]
BACKUP_FILE = "/root/portfolio_state.json"

def backup():
    state = {}
    for user in USERS:
        try:
            r = requests.get(f"{ARIA_URL}/paper/portfolio/{user}", timeout=10)
            state[user] = r.json()
        except:
            pass
    with open(BACKUP_FILE, 'w') as f:
        json.dump(state, f, indent=2)
    print(f"Backed up at {time.strftime('%H:%M:%S')}")

def restore():
    try:
        with open(BACKUP_FILE) as f:
            state = json.load(f)
        for user, portfolio in state.items():
            if portfolio.get('open_count', 0) > 0:
                print(f"Restoring {user}: {portfolio['open_count']} trades")
    except:
        pass

while True:
    backup()
    time.sleep(300)
