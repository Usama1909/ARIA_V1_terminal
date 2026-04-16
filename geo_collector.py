# geo_collector.py - WorldMonitor-style Geopolitical Intelligence
import requests
import json
import time
from datetime import datetime, timedelta

# ── CONFIG ────────────────────────────────────────────────
ARIA_URL = "https://web-production-548c0.up.railway.app"
ACLED_KEY = ""  # Add when email arrives
COLLECT_INTERVAL = 300  # 5 minutes

# ── ASSET GEO SENSITIVITY ────────────────────────────────
# How much each asset is affected by geopolitical events
ASSET_SENSITIVITY = {
    'BTC':  {'conflict': -0.3, 'disaster': -0.2, 'sanctions': -0.4},
    'ETH':  {'conflict': -0.3, 'disaster': -0.2, 'sanctions': -0.4},
    'AAPL': {'conflict': -0.2, 'disaster': -0.1, 'sanctions': -0.5},
    'NVDA': {'conflict': -0.2, 'disaster': -0.1, 'sanctions': -0.6},
    'TSLA': {'conflict': -0.2, 'disaster': -0.1, 'sanctions': -0.3},
    'GLD':  {'conflict':  0.5, 'disaster':  0.3, 'sanctions':  0.4},
}

# ── GDELT (free, no key needed) ───────────────────────────
def fetch_gdelt_events():
    """
    GDELT monitors every news broadcast globally
    Returns conflict/crisis events from last 24 hours
    """
    try:
        url = "https://api.gdeltproject.org/api/v2/tv/tv"
        params = {
            'query': 'conflict OR war OR sanctions OR military OR crisis',
            'mode': 'clipgallery',
            'maxrecords': 20,
            'format': 'json'
        }
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        clips = data.get('clips', [])
        events = []
        for clip in clips[:10]:
            events.append({
                'source': 'GDELT',
                'title': clip.get('show', '') + ': ' + clip.get('snippet', '')[:100],
                'type': 'conflict',
                'severity': 2
            })
        print(f"  GDELT: {len(events)} events")
        return events
    except Exception as e:
        print(f"  GDELT error: {e}")
        return []

# ── USGS EARTHQUAKES (free, no key) ──────────────────────
def fetch_earthquakes():
    """
    Major earthquakes disrupt supply chains and commodity markets
    """
    try:
        url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson"
        r = requests.get(url, timeout=10)
        data = r.json()
        features = data.get('features', [])
        events = []
        for quake in features[:5]:
            props = quake.get('properties', {})
            mag = props.get('mag', 0)
            place = props.get('place', 'Unknown')
            if mag >= 6.0:
                events.append({
                    'source': 'USGS',
                    'title': f'M{mag} earthquake: {place}',
                    'type': 'disaster',
                    'severity': min(int(mag - 4), 3),
                    'magnitude': mag
                })
        print(f"  USGS: {len(events)} significant earthquakes")
        return events
    except Exception as e:
        print(f"  USGS error: {e}")
        return []

# ── RSS CONFLICT FEEDS (free) ────────────────────────────
def fetch_conflict_rss():
    """
    RSS feeds from conflict monitoring sources
    """
    import xml.etree.ElementTree as ET
    feeds = [
        ('https://feeds.bbci.co.uk/news/world/rss.xml', 'BBC'),
        ('https://rss.nytimes.com/services/xml/rss/nyt/World.xml', 'NYT'),
    ]
    conflict_keywords = [
        'war', 'conflict', 'attack', 'missile', 'troops',
        'sanctions', 'military', 'nuclear', 'invasion', 'airstrike',
        'explosion', 'crisis', 'escalation'
    ]
    events = []
    for url, source in feeds:
        try:
            r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            root = ET.fromstring(r.content)
            items = root.findall('.//item')[:10]
            for item in items:
                title = item.findtext('title', '').lower()
                if any(kw in title for kw in conflict_keywords):
                    events.append({
                        'source': source,
                        'title': item.findtext('title', ''),
                        'type': 'conflict',
                        'severity': 2
                    })
        except Exception as e:
            print(f"  RSS {source} error: {e}")
    print(f"  RSS: {len(events)} conflict headlines")
    return events

# ── ACLED (when key arrives) ─────────────────────────────
def fetch_acled_events():
    if not ACLED_KEY:
        return []
    try:
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        url = "https://api.acleddata.com/acled/read"
        params = {
            'key':        ACLED_KEY,
            'email':      'your-email@gmail.com',
            'event_date': yesterday,
            'event_date_where': 'BETWEEN',
            'event_date2': datetime.now().strftime('%Y-%m-%d'),
            'limit':      50,
            'format':     'json'
        }
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        events = []
        for event in data.get('data', [])[:20]:
            events.append({
                'source':   'ACLED',
                'title':    f"{event.get('event_type','')}: {event.get('country','')} - {event.get('notes','')[:80]}",
                'type':     'conflict',
                'severity': 3,
                'country':  event.get('country', ''),
                'fatalities': event.get('fatalities', 0)
            })
        print(f"  ACLED: {len(events)} conflict events")
        return events
    except Exception as e:
        print(f"  ACLED error: {e}")
        return []

# ── CALCULATE GEO RISK SCORE ─────────────────────────────
def calculate_geo_risk(all_events):
    """
    Score 0-100 based on number and severity of events
    """
    if not all_events:
        return 10, {}

    total_severity = sum(e.get('severity', 1) for e in all_events)
    conflict_count = sum(1 for e in all_events if e.get('type') == 'conflict')
    disaster_count = sum(1 for e in all_events if e.get('type') == 'disaster')

    # Base score
    score = min(100, (conflict_count * 8) + (disaster_count * 5) + (total_severity * 3))

    # Asset impacts
    asset_impacts = {}
    for symbol, sensitivity in ASSET_SENSITIVITY.items():
        impact = 0
        impact += conflict_count * sensitivity['conflict'] * 0.1
        impact += disaster_count * sensitivity['disaster'] * 0.1
        asset_impacts[symbol] = round(impact, 3)

    return score, asset_impacts

# ── SEND TO ARIA ──────────────────────────────────────────
def send_geo_to_aria(score, asset_impacts, events):
    try:
        # Report as geo agent
        top_events = [e['title'] for e in events[:3]]
        reasoning = f"Geo risk {score}/100. Events: {len(events)}. Top: {'; '.join(top_events[:2])}"

        requests.post(f"{ARIA_URL}/agent/report", json={
            'agent_id':   'agent_geo',
            'agent_type': 'GEO',
            'symbol':     None,
            'action':     'RISK_HIGH' if score > 60 else 'RISK_MEDIUM' if score > 30 else 'RISK_LOW',
            'confidence': min(score / 100, 0.95),
            'reasoning':  reasoning[:200],
            'pnl_today':  0.0
        }, timeout=5)
        print(f"  Sent geo report to ARIA: score={score}")
    except Exception as e:
        print(f"  ARIA send error: {e}")

# ── MAIN LOOP ─────────────────────────────────────────────
def main():
    print("="*60)
    print("ARIA GEO INTELLIGENCE COLLECTOR - STARTING")
    print(f"Sources: GDELT, USGS, RSS feeds" + (", ACLED" if ACLED_KEY else " (ACLED pending key)"))
    print(f"Interval: {COLLECT_INTERVAL}s")
    print("="*60)

    cycle = 0
    while True:
        cycle += 1
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Geo Cycle {cycle}")

        all_events = []
        all_events += fetch_gdelt_events()
        all_events += fetch_earthquakes()
        all_events += fetch_conflict_rss()
        all_events += fetch_acled_events()

        score, asset_impacts = calculate_geo_risk(all_events)
        print(f"  Geo Risk Score: {score}/100")
        print(f"  Asset impacts: GLD={asset_impacts.get('GLD',0):+.3f} BTC={asset_impacts.get('BTC',0):+.3f}")

        send_geo_to_aria(score, asset_impacts, all_events)

        print(f"  Sleeping {COLLECT_INTERVAL}s...")
        time.sleep(COLLECT_INTERVAL)

if __name__ == "__main__":
    main()
