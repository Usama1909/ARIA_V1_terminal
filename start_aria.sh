#!/bin/bash
cd /root
source /root/aria-env/bin/activate
python agent_loop.py &
python geo_collector.py &
python aria_collector.py &
python aria_ensemble.py &
echo "ARIA agents started"
