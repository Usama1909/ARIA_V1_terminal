import time
import logging
import psycopg2
import feedparser
import requests
from transformers import pipeline
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [NLP] %(message)s")
log = logging.getLogger()

DB = {"host":"localhost","port":5432,"dbname":"aria_db","user":"postgres","password":"aria_secure_2026"}

NEWS_FEEDS = [
    "https://feeds.feedburner.com/CoinTelegraph",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=BTC-USD,ETH-USD,AAPL,NVDA,TSLA,GLD&region=US&lang=en-US",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC%3DF&region=US&lang=en-US",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cryptonews.com/news/feed/",
]

FOMC_HAWKISH = ["rate hike","tighten","inflation","restrictive","hawkish","reduce balance sheet","quantitative tightening"]
FOMC_DOVISH  = ["rate cut","pause","pivot","dovish","accommodative","easing","quantitative easing","support growth"]

SYMBOL_KEYWORDS = {
    "BTC":  ["bitcoin","btc","crypto","coinbase"],
    "ETH":  ["ethereum","eth","defi","smart contract"],
    "AAPL": ["apple","iphone","tim cook","aapl"],
    "NVDA": ["nvidia","nvda","gpu","jensen huang","chips"],
    "TSLA": ["tesla","tsla","elon","ev","electric vehicle"],
    "GLD":  ["gold","gld","safe haven","precious metal"],
}

def get_db():
    return psycopg2.connect(**DB)

def ensure_table():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS nlp_sentiment (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10),
            score FLOAT,
            label VARCHAR(20),
            fomc_signal VARCHAR(20),
            headline_count INTEGER,
            timestamp TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    log.info("NLP table ready")

def fetch_headlines():
    headlines = []
    for feed_url in NEWS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:20]:
                headlines.append(entry.title)
        except Exception as e:
            log.warning(f"Feed error {feed_url}: {e}")
    log.info(f"Fetched {len(headlines)} headlines")
    return headlines

def score_fomc(headlines):
    text = " ".join(headlines).lower()
    hawkish = sum(1 for w in FOMC_HAWKISH if w in text)
    dovish  = sum(1 for w in FOMC_DOVISH  if w in text)
    if hawkish > dovish:   return "HAWKISH"
    elif dovish > hawkish: return "DOVISH"
    else:                  return "NEUTRAL"

def score_symbol(symbol, headlines, finbert):
    keywords = SYMBOL_KEYWORDS.get(symbol, [])
    relevant = [h for h in headlines if any(k in h.lower() for k in keywords)]
    if not relevant:
        return 0.0, "NEUTRAL", 0
    scores = []
    for h in relevant[:10]:
        try:
            result = finbert(h[:512])[0]
            label = result['label'].upper()
            score = result['score']
            if label == "POSITIVE":   scores.append(score)
            elif label == "NEGATIVE": scores.append(-score)
            else:                     scores.append(0.0)
        except Exception as e:
            log.warning(f"FinBERT error: {e}")
    if not scores:
        return 0.0, "NEUTRAL", 0
    avg = sum(scores) / len(scores)
    label = "POSITIVE" if avg > 0.1 else "NEGATIVE" if avg < -0.1 else "NEUTRAL"
    return round(avg, 4), label, len(relevant)

def run():
    ensure_table()
    log.info("Loading FinBERT model...")
    finbert = pipeline("text-classification", model="ProsusAI/finbert", device=-1)
    log.info("FinBERT loaded. Starting NLP loop...")
    while True:
        try:
            headlines = fetch_headlines()
            fomc     = score_fomc(headlines)
            conn     = get_db()
            cur      = conn.cursor()
            for symbol in ["BTC","ETH","AAPL","NVDA","TSLA","GLD"]:
                score, label, count = score_symbol(symbol, headlines, finbert)
                cur.execute("""
                    INSERT INTO nlp_sentiment (symbol, score, label, fomc_signal, headline_count)
                    VALUES (%s, %s, %s, %s, %s)
                """, (symbol, score, label, fomc, count))
                log.info(f"  {symbol}: {label} ({score:+.3f}) | {count} headlines | FOMC:{fomc}")
            conn.commit()
            cur.close()
            conn.close()
            log.info("NLP cycle complete. Sleeping 5 minutes.")
        except Exception as e:
            log.error(f"NLP cycle error: {e}")
        time.sleep(300)

if __name__ == "__main__":
    run()
