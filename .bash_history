lines.append('                    new += 1\n')
lines.append('            print(\"[REED] \" + keyword + \" in \" + location + \": \" + str(new) + \" new jobs\")\n')
lines.append('            return new\n')
lines.append('        except Exception as e:\n')
lines.append('            print(\"[REED] Error: \" + str(e))\n')
lines.append('            return 0\n')
lines.append('\n')
open('scrapers/job_scraper.py', 'a').writelines(lines)
print('chunk 2 done')
"
python3 -c "
lines = []
lines.append('    def scrape_adzuna(self, keyword, location):\n')
lines.append('        if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:\n')
lines.append('            print(\"[ADZUNA] No API keys found\")\n')
lines.append('            return 0\n')
lines.append('        country = \"gb\"\n')
lines.append('        url = \"https://api.adzuna.com/v1/api/jobs/\" + country + \"/search/1\"\n')
lines.append('        params = {\n')
lines.append('            \"app_id\": ADZUNA_APP_ID,\n')
lines.append('            \"app_key\": ADZUNA_APP_KEY,\n')
lines.append('            \"what\": keyword,\n')
lines.append('            \"where\": location,\n')
lines.append('            \"results_per_page\": 50,\n')
lines.append('            \"content-type\": \"application/json\"\n')
lines.append('        }\n')
lines.append('        try:\n')
lines.append('            resp = requests.get(url, params=params, timeout=10)\n')
lines.append('            if resp.status_code != 200:\n')
lines.append('                print(\"[ADZUNA] Status \" + str(resp.status_code))\n')
lines.append('                return 0\n')
lines.append('            jobs = resp.json().get(\"results\", [])\n')
lines.append('            new = 0\n')
lines.append('            for j in jobs:\n')
lines.append('                job = {\n')
lines.append('                    \"title\": j.get(\"title\", \"\"),\n')
lines.append('                    \"company\": j.get(\"company\", {}).get(\"display_name\", \"Unknown\"),\n')
lines.append('                    \"location\": j.get(\"location\", {}).get(\"display_name\", location),\n')
lines.append('                    \"description\": j.get(\"description\", \"\"),\n')
lines.append('                    \"url\": j.get(\"redirect_url\", \"\"),\n')
lines.append('                    \"source\": \"adzuna\",\n')
lines.append('                    \"date_posted\": j.get(\"created\", \"\")[:10]\n')
lines.append('                }\n')
lines.append('                if self._save_job(job):\n')
lines.append('                    new += 1\n')
lines.append('            print(\"[ADZUNA] \" + keyword + \" in \" + location + \": \" + str(new) + \" new jobs\")\n')
lines.append('            return new\n')
lines.append('        except Exception as e:\n')
lines.append('            print(\"[ADZUNA] Error: \" + str(e))\n')
lines.append('            return 0\n')
lines.append('\n')
open('scrapers/job_scraper.py', 'a').writelines(lines)
print('chunk 3 done')
"
python3 -c "
lines = []
lines.append('    def scrape_linkedin_rss(self, keyword, location):\n')
lines.append('        import xml.etree.ElementTree as ET\n')
lines.append('        keyword_enc = keyword.replace(\" \", \"%20\")\n')
lines.append('        location_enc = location.replace(\" \", \"%20\").replace(\",\", \"\")\n')
lines.append('        url = \"https://www.linkedin.com/jobs/search/?keywords=\" + keyword_enc + \"&location=\" + location_enc + \"&f_TPR=r86400\"\n')
lines.append('        try:\n')
lines.append('            resp = requests.get(url, timeout=10, headers={\"User-Agent\": \"Mozilla/5.0\"})\n')
lines.append('            if resp.status_code != 200:\n')
lines.append('                print(\"[LINKEDIN] Status \" + str(resp.status_code))\n')
lines.append('                return 0\n')
lines.append('            root = ET.fromstring(resp.text)\n')
lines.append('            items = root.findall(\".//item\")\n')
lines.append('            new = 0\n')
lines.append('            for item in items:\n')
lines.append('                title = item.findtext(\"title\", \"\").strip()\n')
lines.append('                link = item.findtext(\"link\", \"\").strip()\n')
lines.append('                desc = item.findtext(\"description\", \"\").strip()\n')
lines.append('                job = {\"title\": title, \"company\": \"Unknown\", \"location\": location,\n')
lines.append('                       \"description\": desc, \"url\": link, \"source\": \"linkedin\"}\n')
lines.append('                if self._save_job(job):\n')
lines.append('                    new += 1\n')
lines.append('            print(\"[LINKEDIN] \" + keyword + \" in \" + location + \": \" + str(new) + \" new jobs\")\n')
lines.append('            return new\n')
lines.append('        except Exception as e:\n')
lines.append('            print(\"[LINKEDIN] Error: \" + str(e))\n')
lines.append('            return 0\n')
lines.append('\n')
lines.append('    def scrape(self, keywords, locations):\n')
lines.append('        total = 0\n')
lines.append('        for keyword in keywords:\n')
lines.append('            for location in locations:\n')
lines.append('                print(\"[SCRAPER] \" + keyword + \" in \" + location)\n')
lines.append('                total += self.scrape_reed(keyword, location)\n')
lines.append('                total += self.scrape_adzuna(keyword, location)\n')
lines.append('                total += self.scrape_linkedin_rss(keyword, location)\n')
lines.append('        print(\"[SCRAPER] Done. \" + str(total) + \" new jobs saved.\")\n')
lines.append('        return total\n')
lines.append('\n')
lines.append('if __name__ == \"__main__\":\n')
lines.append('    import sys\n')
lines.append('    sys.path.insert(0, \"/root/JobPilot\")\n')
lines.append('    from profile_manager import get_active_profile\n')
lines.append('    profile = get_active_profile()\n')
lines.append('    if profile:\n')
lines.append('        scraper = JobScraper()\n')
lines.append('        scraper.scrape(profile[\"keywords\"], profile[\"locations\"])\n')
open('scrapers/job_scraper.py', 'a').writelines(lines)
print('chunk 4 done')
"
python3 -c "
with open('main.py', 'r') as f:
    content = f.read()
content = content.replace(
    'from scrapers.rss_scraper import RSSJobScraper',
    'from scrapers.job_scraper import JobScraper'
)
content = content.replace(
    'scraper = RSSJobScraper()',
    'scraper = JobScraper()'
)
with open('main.py', 'w') as f:
    f.write(content)
print('updated')
"
python3 main.py scrape
python3 main.py score
sudo -u postgres psql -d aria_db -c "CREATE UNIQUE INDEX IF NOT EXISTS api_usage_date_idx ON api_usage(date);" 2>/dev/null || sqlite3 jobpilot.db "CREATE UNIQUE INDEX IF NOT EXISTS api_usage_date_idx ON api_usage(date);"
apt install sqlite3 -y
sqlite3 jobpilot.db "CREATE UNIQUE INDEX IF NOT EXISTS api_usage_date_idx ON api_usage(date);"
python3 main.py score
python3 -c "
with open('scoring/claude_scorer.py', 'r') as f:
    content = f.read()

old = 'result = json.loads(message.content[0].text)'
new = '''raw = message.content[0].text.strip()
            for marker in [\"\`\`\`json\", \"\`\`\`\"]:
                raw = raw.replace(marker, \"\")
            result = json.loads(raw.strip())'''

content = content.replace(old, new)
with open('scoring/claude_scorer.py', 'w') as f:
    f.write(content)
print('fixed')
"
python3 main.py score
cd /root/JobPilot
python3 main.py dashboard
cd /root/JobPilot
nano /root/JobPilot/.env
python3 -c "
lines = []
lines.append('import requests\n')
lines.append('import os\n')
lines.append('from dotenv import load_dotenv\n')
lines.append('\n')
lines.append('load_dotenv()\n')
lines.append('\n')
lines.append('BOT_TOKEN = os.getenv(\"TELEGRAM_BOT_TOKEN\", \"\")\n')
lines.append('CHAT_ID = os.getenv(\"TELEGRAM_CHAT_ID\", \"\")\n')
lines.append('\n')
lines.append('def send_message(text):\n')
lines.append('    if not BOT_TOKEN or not CHAT_ID:\n')
lines.append('        print(\"[TELEGRAM] No credentials found\")\n')
lines.append('        return False\n')
lines.append('    url = f\"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage\"\n')
lines.append('    payload = {\"chat_id\": CHAT_ID, \"text\": text, \"parse_mode\": \"HTML\"}\n')
lines.append('    try:\n')
lines.append('        resp = requests.post(url, json=payload, timeout=10)\n')
lines.append('        return resp.status_code == 200\n')
lines.append('    except Exception as e:\n')
lines.append('        print(\"[TELEGRAM] Error: \" + str(e))\n')
lines.append('        return False\n')
lines.append('\n')
lines.append('def send_job_alert(title, company, score, url, summary):\n')
lines.append('    text = (\n')
lines.append('        f\"🎯 <b>HIGH MATCH JOB FOUND</b>\\n\\n\"\n')
lines.append('        f\"<b>{title}</b>\\n\"\n')
lines.append('        f\"🏢 {company}\\n\"\n')
lines.append('        f\"⭐ Score: {score}/100\\n\\n\"\n')
lines.append('        f\"📝 {summary}\\n\\n\"\n')
lines.append('        f\"🔗 {url}\"\n')
lines.append('    )\n')
lines.append('    return send_message(text)\n')
lines.append('\n')
lines.append('def send_daily_summary(jobs_found, jobs_scored, top_matches):\n')
lines.append('    matches_text = \"\"\n')
lines.append('    for i, (title, company, score) in enumerate(top_matches[:5], 1):\n')
lines.append('        matches_text += f\"  {i}. [{score}/100] {title} @ {company}\\n\"\n')
lines.append('    text = (\n')
lines.append('        f\"📊 <b>JOBPILOT DAILY REPORT</b>\\n\\n\"\n')
lines.append('        f\"Jobs found: {jobs_found}\\n\"\n')
lines.append('        f\"Jobs scored: {jobs_scored}\\n\\n\"\n')
lines.append('        f\"<b>TOP MATCHES:</b>\\n{matches_text}\"\n')
lines.append('    )\n')
lines.append('    return send_message(text)\n')
lines.append('\n')
lines.append('if __name__ == \"__main__\":\n')
lines.append('    result = send_message(\"✅ JobPilot Telegram notifications are working!\")\n')
lines.append('    print(\"Sent!\" if result else \"Failed - check your token and chat ID\")\n')
open('telegram_notifier.py', 'w').writelines(lines)
print('done')
"
python3 telegram_notifier.py
python3 -c "
lines = []
lines.append('import requests\n')
lines.append('import os\n')
lines.append('from dotenv import load_dotenv\n')
lines.append('\n')
lines.append('load_dotenv()\n')
lines.append('\n')
lines.append('BOT_TOKEN = os.getenv(\"TELEGRAM_BOT_TOKEN\", \"\")\n')
lines.append('CHAT_ID = os.getenv(\"TELEGRAM_CHAT_ID\", \"\")\n')
lines.append('\n')
lines.append('def send_message(text):\n')
lines.append('    if not BOT_TOKEN or not CHAT_ID:\n')
lines.append('        print(\"[TELEGRAM] No credentials found\")\n')
lines.append('        return False\n')
lines.append('    url = \"https://api.telegram.org/bot\" + BOT_TOKEN + \"/sendMessage\"\n')
lines.append('    payload = {\"chat_id\": CHAT_ID, \"text\": text, \"parse_mode\": \"HTML\"}\n')
lines.append('    try:\n')
lines.append('        resp = requests.post(url, json=payload, timeout=10)\n')
lines.append('        return resp.status_code == 200\n')
lines.append('    except Exception as e:\n')
lines.append('        print(\"[TELEGRAM] Error: \" + str(e))\n')
lines.append('        return False\n')
lines.append('\n')
lines.append('def send_job_alert(title, company, score, url, summary):\n')
lines.append('    text = \"HIGH MATCH JOB FOUND\\n\\n\"\n')
lines.append('    text += \"<b>\" + title + \"</b>\\n\"\n')
lines.append('    text += \"Company: \" + company + \"\\n\"\n')
lines.append('    text += \"Score: \" + str(score) + \"/100\\n\\n\"\n')
lines.append('    text += summary + \"\\n\\n\"\n')
lines.append('    text += url\n')
lines.append('    return send_message(text)\n')
lines.append('\n')
lines.append('def send_daily_summary(jobs_found, jobs_scored, top_matches):\n')
lines.append('    text = \"<b>JOBPILOT DAILY REPORT</b>\\n\\n\"\n')
lines.append('    text += \"Jobs found: \" + str(jobs_found) + \"\\n\"\n')
lines.append('    text += \"Jobs scored: \" + str(jobs_scored) + \"\\n\\n\"\n')
lines.append('    text += \"<b>TOP MATCHES:</b>\\n\"\n')
lines.append('    for i, (title, company, score) in enumerate(top_matches[:5], 1):\n')
lines.append('        text += str(i) + \". [\" + str(score) + \"/100] \" + title + \" @ \" + company + \"\\n\"\n')
lines.append('    return send_message(text)\n')
lines.append('\n')
lines.append('if __name__ == \"__main__\":\n')
lines.append('    result = send_message(\"JobPilot Telegram notifications are working!\")\n')
lines.append('    print(\"Sent!\" if result else \"Failed - check your token and chat ID\")\n')
open('telegram_notifier.py', 'w').writelines(lines)
print('done')
"
python3 telegram_notifier.py
python3 << 'PYEOF'
content = """import requests
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def send_message(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("[TELEGRAM] No credentials found")
        return False
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print("[TELEGRAM] Error: " + str(e))
        return False

def send_job_alert(title, company, score, url, summary):
    lines = ["HIGH MATCH JOB FOUND", "", title, "Company: " + company, "Score: " + str(score) + "/100", "", summary, "", url]
    return send_message("\\n".join(lines))

def send_daily_summary(jobs_found, jobs_scored, top_matches):
    lines = ["JOBPILOT DAILY REPORT", "", "Jobs found: " + str(jobs_found), "Jobs scored: " + str(jobs_scored), "", "TOP MATCHES:"]
    for i, (title, company, score) in enumerate(top_matches[:5], 1):
        lines.append(str(i) + ". [" + str(score) + "/100] " + title + " @ " + company)
    return send_message("\\n".join(lines))

if __name__ == "__main__":
    result = send_message("JobPilot is connected!")
    print("Sent!" if result else "Failed")
"""
with open("telegram_notifier.py", "w") as f:
    f.write(content)
print("done")
PYEOF

python3 telegram_notifier.py
grep "TELEGRAM" /root/JobPilot/.env
nano /root/JobPilot/.env
python3 telegram_notifier.py
python3 -c "
import requests
import os
from dotenv import load_dotenv
load_dotenv()
token = os.getenv('TELEGRAM_BOT_TOKEN', '')
chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
print('Token length:', len(token))
print('Chat ID:', chat_id)
url = 'https://api.telegram.org/bot' + token + '/sendMessage'
resp = requests.post(url, json={'chat_id': chat_id, 'text': 'test'})
print('Status:', resp.status_code)
print('Response:', resp.text)
"
nano /root/JobPilot/.env
python3 telegram_notifier.py
python3 -c "
import requests
import os
from dotenv import load_dotenv
load_dotenv()
token = os.getenv('TELEGRAM_BOT_TOKEN', '')
chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
print('Token:', repr(token))
print('Chat ID:', repr(chat_id))
url = 'https://api.telegram.org/bot' + token + '/sendMessage'
resp = requests.post(url, json={'chat_id': chat_id, 'text': 'test'})
print('Status:', resp.status_code)
print('Response:', resp.text)
"
python3 -c "
import requests
import os
from dotenv import load_dotenv
load_dotenv()
token = os.getenv('TELEGRAM_BOT_TOKEN', '')
url = 'https://api.telegram.org/bot' + token + '/getUpdates'
resp = requests.get(url)
print(resp.text)
"
cd /root/JobPilot
python3 -c "
import requests
import os
from dotenv import load_dotenv
load_dotenv()
token = os.getenv('TELEGRAM_BOT_TOKEN', '')
url = 'https://api.telegram.org/bot' + token + '/getUpdates'
resp = requests.get(url)
print(resp.text)
"
nano /root/JobPilot/.env
python3 -c "
import requests
import os
from dotenv import load_dotenv
load_dotenv()
token = os.getenv('TELEGRAM_BOT_TOKEN', '')
chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
print('Token:', repr(token))
url = 'https://api.telegram.org/bot' + token + '/getUpdates'
resp = requests.get(url)
print(resp.text)
"
python3 -c "
import requests, os
from dotenv import load_dotenv
load_dotenv()
token = os.getenv('TELEGRAM_BOT_TOKEN', '')
resp = requests.get('https://api.telegram.org/bot' + token + '/getUpdates')
print(resp.text)
"
python3 telegram_notifier.py
python3 -c "
with open('scoring/claude_scorer.py', 'r') as f:
    content = f.read()

old = 'import anthropic'
new = 'import anthropic\nimport sys\nsys.path.insert(0, \"/root/JobPilot\")\nfrom telegram_notifier import send_job_alert'

content = content.replace(old, new)

old2 = 'if score >= MIN_SCORE_TO_APPLY:'
new2 = '''if score >= 80:
                try:
                    send_job_alert(title, company, score, url, result.get(\"one_line_summary\", \"\"))
                except:
                    pass
            if score >= MIN_SCORE_TO_APPLY:'''

content = content.replace(old2, new2)

with open('scoring/claude_scorer.py', 'w') as f:
    f.write(content)
print('done')
"
python3 << 'PYEOF'
content = """import sqlite3
import os
from datetime import datetime

def cleanup_database(db_path="jobpilot.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Delete low score jobs older than 7 days
    cursor.execute(\"\"\"
        DELETE FROM jobs_raw WHERE id IN (
            SELECT r.id FROM jobs_raw r
            JOIN jobs_scored s ON r.id = s.job_id
            WHERE s.score < 60
            AND date(r.scraped_at) <= date('now', '-7 days')
        )
    \"\"\")
    low_score_deleted = cursor.rowcount

    # Archive rejected/offered applications - keep only title and company
    cursor.execute(\"\"\"
        INSERT OR IGNORE INTO job_archive (title, company, status, date_archived)
        SELECT r.title, r.company, a.status, date('now')
        FROM applications a
        JOIN jobs_scored s ON a.job_id = s.id
        JOIN jobs_raw r ON s.job_id = r.id
        WHERE a.status IN ('REJECTED', 'OFFER', 'WITHDRAWN')
    \"\"\")

    # Delete full data for archived jobs
    cursor.execute(\"\"\"
        DELETE FROM jobs_raw WHERE id IN (
            SELECT r.id FROM jobs_raw r
            JOIN jobs_scored s ON r.id = s.job_id
            JOIN applications a ON s.id = a.job_id
            WHERE a.status IN ('REJECTED', 'OFFER', 'WITHDRAWN')
        )
    \"\"\")
    archived = cursor.rowcount

    # Delete unscored jobs older than 3 days
    cursor.execute(\"\"\"
        DELETE FROM jobs_raw WHERE id NOT IN (
            SELECT job_id FROM jobs_scored
        )
        AND date(scraped_at) <= date('now', '-3 days')
    \"\"\")
    old_deleted = cursor.rowcount

    conn.commit()
    conn.close()

    print(f"[CLEANUP] Low score deleted: {low_score_deleted}")
    print(f"[CLEANUP] Archived: {archived}")
    print(f"[CLEANUP] Old unscored deleted: {old_deleted}")

def create_archive_table(db_path="jobpilot.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(\"\"\"
        CREATE TABLE IF NOT EXISTS job_archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            company TEXT,
            status TEXT,
            date_archived TEXT DEFAULT CURRENT_DATE
        )
    \"\"\")
    conn.commit()
    conn.close()
    print("[CLEANUP] Archive table ready")

if __name__ == "__main__":
    create_archive_table()
    cleanup_database()
"""
with open("cleanup.py", "w") as f:
    f.write(content)
print("done")
PYEOF

python3 cleanup.py
python3 << 'PYEOF'
content = """[Unit]
Description=JobPilot Autonomous Job Hunter
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/JobPilot
ExecStart=/usr/bin/python3 /root/JobPilot/main.py schedule
Restart=always
RestartSec=60
StandardOutput=append:/var/log/jobpilot.log
StandardError=append:/var/log/jobpilot.log

[Install]
WantedBy=multi-user.target
"""
with open("/etc/systemd/system/jobpilot.service", "w") as f:
    f.write(content)
print("done")
PYEOF

systemctl daemon-reload
systemctl enable jobpilot
systemctl start jobpilot
systemctl status jobpilot
Created symlink /etc/systemd/system/multi-user.target.wants/jobpilot.service → /etc/systemd/system/jobpilot.service.
● jobpilot.service - JobPilot Autonomous Job Hunter
Apr 14 19:34:36 aria-trainer systemd[1]: Started jobpilot.service - JobPilot Autonomous Job Hunter.
root@aria-trainer:~/JobPilot#cd /root/JobPilot
git add .
git commit -m "Initial release - JobPilot Autonomous Career Intelligence System"
git push origin main
echo "jobpilot.db" >> .gitignore
echo "cv_engine/master_cv.docx" >> .gitignore
echo ".active_profile" >> .gitignore
echo "test.py" >> .gitignore
echo "reports/archive/" >> .gitignore
git rm --cached jobpilot.db cv_engine/master_cv.docx .active_profile test.py 2>/dev/null
git add .gitignore
git commit -m "Remove personal files from tracking"
git push origin main
cd /root/JobPilot
cat > architecture.svg << 'SVGEOF'
<svg width="100%" viewBox="0 0 680 620" xmlns="http://www.w3.org/2000/svg">
<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="#888780" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<rect x="40" y="40" width="130" height="44" rx="8" fill="#f1efe8" stroke="#888780" stroke-width="0.5"/>
<text font-family="Arial" font-size="13" font-weight="500" x="105" y="67" text-anchor="middle">Reed API</text>
<rect x="190" y="40" width="130" height="44" rx="8" fill="#f1efe8" stroke="#888780" stroke-width="0.5"/>
<text font-family="Arial" font-size="13" font-weight="500" x="255" y="67" text-anchor="middle">Adzuna API</text>
<rect x="340" y="40" width="130" height="44" rx="8" fill="#f1efe8" stroke="#888780" stroke-width="0.5"/>
<text font-family="Arial" font-size="13" font-weight="500" x="405" y="67" text-anchor="middle">LinkedIn RSS</text>
<line x1="105" y1="84" x2="245" y2="148" stroke="#888780" stroke-width="1" marker-end="url(#arrow)"/>
<line x1="255" y1="84" x2="255" y2="148" stroke="#888780" stroke-width="1" marker-end="url(#arrow)"/>
<line x1="405" y1="84" x2="265" y2="148" stroke="#888780" stroke-width="1" marker-end="url(#arrow)"/>
<rect x="140" y="148" width="230" height="56" rx="8" fill="#e1f5ee" stroke="#0f6e56" stroke-width="0.5"/>
<text font-family="Arial" font-size="13" font-weight="500" x="255" y="176" text-anchor="middle">Job scraper</text>
<text font-family="Arial" font-size="11" x="255" y="194" text-anchor="middle" fill="#0f6e56">Runs at 8am + 6pm daily</text>
<line x1="255" y1="204" x2="255" y2="244" stroke="#888780" stroke-width="1" marker-end="url(#arrow)"/>
<rect x="140" y="244" width="230" height="44" rx="8" fill="#f1efe8" stroke="#888780" stroke-width="0.5"/>
<text font-family="Arial" font-size="13" font-weight="500" x="255" y="271" text-anchor="middle">Deduplicate + normalize</text>
<line x1="255" y1="288" x2="255" y2="328" stroke="#888780" stroke-width="1" marker-end="url(#arrow)"/>
<rect x="120" y="328" width="270" height="56" rx="8" fill="#eeedfe" stroke="#534ab7" stroke-width="0.5"/>
<text font-family="Arial" font-size="13" font-weight="500" x="255" y="356" text-anchor="middle">Claude AI scorer</text>
<text font-family="Arial" font-size="11" x="255" y="374" text-anchor="middle" fill="#534ab7">Scores each job 0-100 vs your CV</text>
<line x1="190" y1="384" x2="100" y2="424" stroke="#888780" stroke-width="1" marker-end="url(#arrow)"/>
<rect x="40" y="424" width="120" height="44" rx="8" fill="#f1efe8" stroke="#888780" stroke-width="0.5"/>
<text font-family="Arial" font-size="12" font-weight="500" x="100" y="451" text-anchor="middle">Score below 60</text>
<line x1="320" y1="384" x2="410" y2="424" stroke="#888780" stroke-width="1" marker-end="url(#arrow)"/>
<rect x="350" y="424" width="120" height="44" rx="8" fill="#faeeda" stroke="#ba7517" stroke-width="0.5"/>
<text font-family="Arial" font-size="12" font-weight="500" x="410" y="451" text-anchor="middle">Score 80+</text>
<line x1="470" y1="446" x2="530" y2="446" stroke="#888780" stroke-width="1" marker-end="url(#arrow)"/>
<rect x="530" y="424" width="120" height="44" rx="8" fill="#e1f5ee" stroke="#0f6e56" stroke-width="0.5"/>
<text font-family="Arial" font-size="12" font-weight="500" x="590" y="451" text-anchor="middle">Telegram alert</text>
<line x1="410" y1="468" x2="410" y2="508" stroke="#888780" stroke-width="1" marker-end="url(#arrow)"/>
<rect x="310" y="508" width="200" height="44" rx="8" fill="#eeedfe" stroke="#534ab7" stroke-width="0.5"/>
<text font-family="Arial" font-size="13" font-weight="500" x="410" y="535" text-anchor="middle">CV tailor</text>
<line x1="255" y1="384" x2="190" y2="508" stroke="#888780" stroke-width="1" marker-end="url(#arrow)"/>
<rect x="130" y="508" width="120" height="44" rx="8" fill="#e1f5ee" stroke="#0f6e56" stroke-width="0.5"/>
<text font-family="Arial" font-size="12" font-weight="500" x="190" y="535" text-anchor="middle">Daily report</text>
</svg>
SVGEOF

echo "Done"
git add README.md architecture.svg
git commit -m "Add README and architecture diagram"
git push origin main
cd /root/JobPilot
sed -i 's/## How It Works/## Architecture\n\n![JobPilot Architecture](architecture.svg)\n\n## How It Works/' README.md
git add README.md
git commit -m "Add architecture diagram to README"
git push origin main
grep -n "open_positions\[d\['symbol'\]\] = d" /root/agent_loop_v5.py
sed -n '455,475p' /root/agent_loop_v5.py
cp /root/agent_loop_v5.py /root/agent_loop_v5.py.bak
python3 -c "
with open('/root/agent_loop_v5.py', 'r') as f:
    content = f.read()

old = '''                    open_positions[d['symbol']] = d
                    log.info(f\"  ORDER: {d['action']} {d['symbol']} \${d['size_usd']:.0f}\")'''

new = '''                    open_positions[d['symbol']] = d
                    try:
                        conn2 = get_db()
                        cur2 = conn2.cursor()
                        cur2.execute(\"\"\"
                            INSERT INTO positions_live (symbol, direction, entry_price, size_usd, regime_at_entry, sentiment_at_entry, fear_greed_at_entry, status)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, 'OPEN')
                            ON CONFLICT (symbol) DO UPDATE SET
                            direction=EXCLUDED.direction, entry_price=EXCLUDED.entry_price,
                            size_usd=EXCLUDED.size_usd, status='OPEN', updated_at=NOW()
                        \"\"\", (d['symbol'], d['direction'], d.get('entry_price', 0),
                               d['size_usd'], d.get('regime','NORMAL'),
                               d.get('sentiment_score', 0), d.get('fear_greed', 21)))
                        conn2.commit()
                        conn2.close()
                    except Exception as pe:
                        log.error(f\"positions_live write failed: {pe}\")
                    log.info(f\"  ORDER: {d['action']} {d['symbol']} \${d['size_usd']:.0f}\")'''

content = content.replace(old, new)
with open('/root/agent_loop_v5.py', 'w') as f:
    f.write(content)
print('done')
"
sed -n '460,485p' /root/agent_loop_v5.py
sed -n '134,185p' /root/agent_loop_v5.py
python3 -c "
with open('/root/agent_loop_v5.py', 'r') as f:
    content = f.read()

old = \"        conn.commit(); cur.close(); conn.close()\"

new = \"\"\"        cur.execute(\\\"UPDATE positions_live SET status='CLOSED', updated_at=NOW() WHERE symbol=%s\\\", [symbol])
        conn.commit(); cur.close(); conn.close()\"\"\"

content = content.replace(old, new, 1)
with open('/root/agent_loop_v5.py', 'w') as f:
    f.write(content)
print('done')
"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h localhost -c "
INSERT INTO positions_live (symbol, direction, entry_price, size_usd, regime_at_entry, sentiment_at_entry, fear_greed_at_entry, status)
VALUES 
('GLD', 'LONG', 0, 100, 'NORMAL', -12.0, 21, 'OPEN'),
('ETH', 'LONG', 0, 100, 'NORMAL', -12.0, 21, 'OPEN'),
('BTC', 'LONG', 0, 100, 'NORMAL', -12.0, 21, 'OPEN')
ON CONFLICT (symbol) DO NOTHING;
"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h localhost -c "SELECT symbol, direction, status FROM positions_live;"
systemctl restart aria_loop_v5
sleep 5
systemctl status aria_loop_v5 --no-pager | grep Active
python3 -c "
with open('/root/aria_db_sync.py', 'r') as f:
    content = f.read()
content = content.replace(
    'SELECT sys_mode, regime, sentiment_score, fear_greed, narrative, liquidity_state, w_mult, portfolio_value, cycle FROM system_health ORDER BY id DESC LIMIT 1',
    'SELECT mode, score FROM system_health ORDER BY id DESC LIMIT 1'
)
content = content.replace(
    'rcur.execute(\"INSERT INTO system_state_sync (id, sys_mode, regime, sentiment, fear_greed, narrative, liquidity, wmult, portfolio_value, cycle, updated_at) VALUES (1,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()) ON CONFLICT (id) DO UPDATE SET sys_mode=EXCLUDED.sys_mode, regime=EXCLUDED.regime, sentiment=EXCLUDED.sentiment, fear_greed=EXCLUDED.fear_greed, narrative=EXCLUDED.narrative, liquidity=EXCLUDED.liquidity, wmult=EXCLUDED.wmult, portfolio_value=EXCLUDED.portfolio_value, cycle=EXCLUDED.cycle, updated_at=NOW()\", row)',
    'rcur.execute(\"INSERT INTO system_state_sync (id, sys_mode, regime, updated_at) VALUES (1,%s,%s,NOW()) ON CONFLICT (id) DO UPDATE SET sys_mode=EXCLUDED.sys_mode, regime=EXCLUDED.regime, updated_at=NOW()\", (row[0], row[0]))'
)
with open('/root/aria_db_sync.py', 'w') as f:
    f.write(content)
print('fixed')
"
python3 /root/aria_db_sync.py
grep -r "positions\|LIVE\|open_pos" /root/main.py | grep -i "select\|fetch\|query" | head -20
grep -n "positions\|live_pos\|open_pos" /root/main.py | head -30
sed -n '1201,1270p' /root/main.py
python3 -c "
with open('/root/aria_db_sync.py', 'r') as f:
    content = f.read()

old = 'if __name__ == \"__main__\":\n    run()'

new = '''import requests

RAILWAY_APP_URL = 'https://web-production-548c0.up.railway.app'

def post_positions_to_frontend(positions):
    try:
        payload = {'positions': [{'symbol': p[0], 'direction': p[1], 'entry_price': p[2], 'size': p[3], 'exchange': 'ARIA Paper'} for p in positions]}
        resp = requests.post(RAILWAY_APP_URL + '/positions/update', json=payload, timeout=10)
        log.info('Posted ' + str(len(positions)) + ' positions to frontend: ' + str(resp.status_code))
    except Exception as e:
        log.error('Frontend POST failed: ' + str(e))

if __name__ == \"__main__\":
    run()'''

content = content.replace(old, new)
with open('/root/aria_db_sync.py', 'w') as f:
    f.write(content)
print('done')
"
python3 -c "
with open('/root/aria_db_sync.py', 'r') as f:
    content = f.read()

old = '            sync_system_state(hcur, rcur)\n            rconn.commit()'

new = '''            sync_system_state(hcur, rcur)
            rconn.commit()
            hcur.execute(\"SELECT symbol, direction, entry_price, size_usd, status FROM positions_live WHERE status='OPEN'\")
            positions = hcur.fetchall()
            post_positions_to_frontend(positions)'''

content = content.replace(old, new)
with open('/root/aria_db_sync.py', 'w') as f:
    f.write(content)
print('done')
"
systemctl restart aria_db_sync
sleep 5
journalctl -u aria_db_sync -n 20 --no-pager
tail -20 /var/log/aria_db_sync.log
systemctl status aria_loop_v5 aria_market aria_sentiment aria_anomaly aria_world_model aria_positions jobpilot --no-pager | grep -E "Active|●"
journalctl -u aria_loop_v5 -n 30 --no-pager
ps aux | grep python3 | grep -v grep | wc -l
ps aux | grep -E "aria|agent|loop|sentiment|market|world|anomaly|position|watchdog|jobpilot" | grep -v grep
grep -i "database\|postgres\|DB_URL" /root/main.py | head -10
sudo -u postgres psql -d aria_db -h localhost -c "SELECT symbol, side, entry_price, quantity, pnl FROM positions LIMIT 10;" 2>/dev/null || python3 -c "
import psycopg2, os
conn = psycopg2.connect(os.environ.get('DATABASE_URL', ''))
cur = conn.cursor()
cur.execute('SELECT symbol, side, entry_price, quantity FROM positions LIMIT 10')
print(cur.fetchall())
conn.close()
"
python3 -c "
import os, sys
sys.path.insert(0, '/root')
from main import get_db
conn = get_db()
cur = conn.cursor()
cur.execute('SELECT symbol, side, entry_price, quantity FROM positions LIMIT 10')
print(cur.fetchall())
conn.close()
"
python3 -c "
import psycopg2
import subprocess
result = subprocess.run(['grep', 'DATABASE_URL', '/etc/environment', '/root/.env', '/root/.bashrc'], capture_output=True, text=True)
print(result.stdout)
"
grep -r "DATABASE_URL\|postgres" /root/.env /root/aria-env/bin/activate 2>/dev/null | head -5
grep -r "DATABASE_URL\|RAILWAY\|postgres" /root/agent_loop_v5.py | head -10
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h localhost -c "SELECT symbol, side, entry_price, quantity FROM positions LIMIT 10;"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h localhost -c "\dt"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h localhost -c "SELECT symbol, side, entry_price, quantity FROM positions_live LIMIT 10;"
grep -r "DATABASE_URL" /root/main.py | head -3
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h localhost -c "\d positions_live"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h localhost -c "SELECT symbol, direction, entry_price, size_usd, status FROM positions_live;"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h localhost -c "SELECT * FROM positions_live;"
grep -n "positions_live" /root/agent_loop_v5.py | head -20
grep -n "position\|INSERT\|UPDATE" /root/agent_loop_v5.py | head -30
nano /root/.env
python3 -c "
lines = []
lines.append('import psycopg2\n')
lines.append('import os\n')
lines.append('import time\n')
lines.append('import logging\n')
lines.append('from dotenv import load_dotenv\n')
lines.append('\n')
lines.append('load_dotenv(\"/root/.env\")\n')
lines.append('\n')
lines.append('logging.basicConfig(level=logging.INFO, format=\"%(asctime)s [SYNC] %(message)s\")\n')
lines.append('log = logging.getLogger()\n')
lines.append('\n')
lines.append('HETZNER_DB = {\"host\":\"localhost\",\"port\":5432,\"dbname\":\"aria_db\",\"user\":\"postgres\",\"password\":\"aria_secure_2026\"}\n')
lines.append('RAILWAY_URL = os.getenv(\"RAILWAY_DATABASE_URL\", \"\")\n')
lines.append('SYNC_INTERVAL = 60\n')
lines.append('\n')
lines.append('def get_hetzner():\n')
lines.append('    return psycopg2.connect(**HETZNER_DB)\n')
lines.append('\n')
lines.append('def get_railway():\n')
lines.append('    return psycopg2.connect(RAILWAY_URL)\n')
open('/root/aria_db_sync.py', 'w').writelines(lines)
print('chunk 1 done')
"
python3 -c "
lines = []
lines.append('\n')
lines.append('def ensure_railway_tables(rcur):\n')
lines.append('    rcur.execute(\"\"\"\n')
lines.append('        CREATE TABLE IF NOT EXISTS positions_live (\n')
lines.append('            id SERIAL PRIMARY KEY,\n')
lines.append('            symbol VARCHAR(10) UNIQUE,\n')
lines.append('            direction VARCHAR(10),\n')
lines.append('            entry_price FLOAT,\n')
lines.append('            size_usd FLOAT,\n')
lines.append('            status VARCHAR(20) DEFAULT \'OPEN\',\n')
lines.append('            updated_at TIMESTAMP DEFAULT NOW()\n')
lines.append('        )\n')
lines.append('    \"\"\")\n')
lines.append('    rcur.execute(\"\"\"\n')
lines.append('        CREATE TABLE IF NOT EXISTS system_state_sync (\n')
lines.append('            id INTEGER PRIMARY KEY DEFAULT 1,\n')
lines.append('            sys_mode VARCHAR(20),\n')
lines.append('            regime VARCHAR(20),\n')
lines.append('            sentiment FLOAT,\n')
lines.append('            fear_greed INTEGER,\n')
lines.append('            narrative VARCHAR(50),\n')
lines.append('            liquidity VARCHAR(20),\n')
lines.append('            wmult FLOAT,\n')
lines.append('            portfolio_value FLOAT,\n')
lines.append('            cycle INTEGER,\n')
lines.append('            updated_at TIMESTAMP DEFAULT NOW()\n')
lines.append('        )\n')
lines.append('    \"\"\")\n')
open('/root/aria_db_sync.py', 'a').writelines(lines)
print('chunk 2 done')
"python3 -c "
lines = []
lines.append('\n')
lines.append('def ensure_railway_tables(rcur):\n')
lines.append('    rcur.execute(\"\"\"\n')
lines.append('        CREATE TABLE IF NOT EXISTS positions_live (\n')
lines.append('            id SERIAL PRIMARY KEY,\n')
lines.append('            symbol VARCHAR(10) UNIQUE,\n')
lines.append('            direction VARCHAR(10),\n')
lines.append('            entry_price FLOAT,\n')
lines.append('            size_usd FLOAT,\n')
lines.append('            status VARCHAR(20) DEFAULT \'OPEN\',\n')
lines.append('            updated_at TIMESTAMP DEFAULT NOW()\n')
lines.append('        )\n')
lines.append('    \"\"\")\n')
lines.append('    rcur.execute(\"\"\"\n')
lines.append('        CREATE TABLE IF NOT EXISTS system_state_sync (\n')
lines.append('            id INTEGER PRIMARY KEY DEFAULT 1,\n')
lines.append('            sys_mode VARCHAR(20),\n')
lines.append('            regime VARCHAR(20),\n')
lines.append('            sentiment FLOAT,\n')
lines.append('            fear_greed INTEGER,\n')
lines.append('            narrative VARCHAR(50),\n')
lines.append('            liquidity VARCHAR(20),\n')
lines.append('            wmult FLOAT,\n')
lines.append('            portfolio_value FLOAT,\n')
lines.append('            cycle INTEGER,\n')
lines.append('            updated_at TIMESTAMP DEFAULT NOW()\n')
lines.append('        )\n')
lines.append('    \"\"\")\n')
open('/root/aria_db_sync.py', 'a').writelines(lines)
print('chunk 2 done')
"
tail -20 /root/aria_db_sync.py
python3 -c "
lines = []
lines.append('\n')
lines.append('def sync_positions(hcur, rcur):\n')
lines.append('    hcur.execute(\"SELECT symbol, direction, entry_price, size_usd, status FROM positions_live\")\n')
lines.append('    positions = hcur.fetchall()\n')
lines.append('    for p in positions:\n')
lines.append('        rcur.execute(\"INSERT INTO positions_live (symbol, direction, entry_price, size_usd, status, updated_at) VALUES (%s, %s, %s, %s, %s, NOW()) ON CONFLICT (symbol) DO UPDATE SET direction=EXCLUDED.direction, entry_price=EXCLUDED.entry_price, size_usd=EXCLUDED.size_usd, status=EXCLUDED.status, updated_at=NOW()\", p)\n')
lines.append('    log.info(\"Synced \" + str(len(positions)) + \" positions to Railway\")\n')
lines.append('\n')
lines.append('def sync_system_state(hcur, rcur):\n')
lines.append('    try:\n')
lines.append('        hcur.execute(\"SELECT sys_mode, regime, sentiment_score, fear_greed, narrative, liquidity_state, w_mult, portfolio_value, cycle FROM system_health ORDER BY id DESC LIMIT 1\")\n')
lines.append('        row = hcur.fetchone()\n')
lines.append('        if row:\n')
lines.append('            rcur.execute(\"INSERT INTO system_state_sync (id, sys_mode, regime, sentiment, fear_greed, narrative, liquidity, wmult, portfolio_value, cycle, updated_at) VALUES (1,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()) ON CONFLICT (id) DO UPDATE SET sys_mode=EXCLUDED.sys_mode, regime=EXCLUDED.regime, sentiment=EXCLUDED.sentiment, fear_greed=EXCLUDED.fear_greed, narrative=EXCLUDED.narrative, liquidity=EXCLUDED.liquidity, wmult=EXCLUDED.wmult, portfolio_value=EXCLUDED.portfolio_value, cycle=EXCLUDED.cycle, updated_at=NOW()\", row)\n')
lines.append('            log.info(\"Synced system state\")\n')
lines.append('    except Exception as e:\n')
lines.append('        log.warning(\"system state sync skipped: \" + str(e))\n')
open('/root/aria_db_sync.py', 'a').writelines(lines)
print('chunk 3 done')
"
python3 -c "
lines = []
lines.append('\n')
lines.append('def run():\n')
lines.append('    log.info(\"DB Sync Bridge starting...\")\n')
lines.append('    if not RAILWAY_URL:\n')
lines.append('        log.error(\"RAILWAY_DATABASE_URL not set\")\n')
lines.append('        return\n')
lines.append('    while True:\n')
lines.append('        try:\n')
lines.append('            hconn = get_hetzner()\n')
lines.append('            rconn = get_railway()\n')
lines.append('            hcur = hconn.cursor()\n')
lines.append('            rcur = rconn.cursor()\n')
lines.append('            ensure_railway_tables(rcur)\n')
lines.append('            sync_positions(hcur, rcur)\n')
lines.append('            sync_system_state(hcur, rcur)\n')
lines.append('            rconn.commit()\n')
lines.append('            hcur.close(); hconn.close()\n')
lines.append('            rcur.close(); rconn.close()\n')
lines.append('            log.info(\"Sync complete. Next in \" + str(SYNC_INTERVAL) + \"s\")\n')
lines.append('        except Exception as e:\n')
lines.append('            log.error(\"Sync error: \" + str(e))\n')
lines.append('        time.sleep(SYNC_INTERVAL)\n')
lines.append('\n')
lines.append('if __name__ == \"__main__\":\n')
lines.append('    run()\n')
open('/root/aria_db_sync.py', 'a').writelines(lines)
print('chunk 4 done')
"
cd /root && python3 aria_db_sync.py
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h localhost -c "\d system_health"
cat > /etc/systemd/system/aria_db_sync.service << 'EOF'
[Unit]
Description=ARIA DB Sync Bridge - Hetzner to Railway
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=/usr/bin/python3 /root/aria_db_sync.py
Restart=always
RestartSec=30
StandardOutput=append:/var/log/aria_db_sync.log
StandardError=append:/var/log/aria_db_sync.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable aria_db_sync
systemctl start aria_db_sync
systemctl status aria_db_sync --no-pager | grep Active
systemctl status aria_loop_v5 aria_market aria_sentiment aria_anomaly aria_world_model aria_positions jobpilot aria_db_sync --no-pager | grep -E "Active|●"
grep -n "system_prompt\|system_message\|SYSTEM\|context" /root/main.py | head -30
sed -n '839,865p' /root/main.py
python3 -c "
with open('/root/main.py', 'r') as f:
    content = f.read()
content = content.replace('for sym in symbols_to_analyse[:2]:', 'for sym in symbols_to_analyse[:6]:')
with open('/root/main.py', 'w') as f:
    f.write(content)
print('fixed')
"
cd /root
git add main.py
git commit -m "Fix chat context to include all 6 assets"
git push origin master
grep "symbols_to_analyse\[:6\]" /root/main.py
curl -s https://web-production-548c0.up.railway.app/health | head -20
grep -n "CRITICAL\|risk_score\|Advanced Retail\|swarm_balance\|portfolio_value\|open_positions\|of 5 max\|of 20 total" /root/main.py | head -30
grep -n "swarm_balance\|of 5 max\|of 20 total\|SWARM ACTIVE\|Storm Protocol\|20 AGENTS" /root/main.py | head -20
find /root -name "*.html" | head -5
grep -l "SWARM ACTIVE\|of 5 max\|Storm Protocol" /root/frontend.html /root/aria_terminal.html 2>/dev/null
grep -n "SWARM ACTIVE\|of 5 max\|of 20 total\|Storm Protocol\|20 AGENTS\|Advanced Retail\|Autonomous Reasoning" /root/aria_terminal.html | head -20
python3 -c "
with open('/root/aria_terminal.html', 'r') as f:
    content = f.read()

# Fix name
content = content.replace('Advanced Retail Intelligence & Analytics', 'Autonomous Reasoning & Intelligence Architecture')
content = content.replace('Advanced Retail Intelligence and Analytics', 'Autonomous Reasoning & Intelligence Architecture')

# Fix agent count to match reality
content = content.replace('20 AGENTS RUNNING', '12 AGENTS RUNNING')
content = content.replace('of 20 total', 'of 12 total')
content = content.replace('V4 — 20 AGENTS', 'V5 — 12 AGENTS')

# Fix max positions to match reality
content = content.replace('of 5 max', 'of 6 max')

with open('/root/aria_terminal.html', 'w') as f:
    f.write(content)
print('done')
"
grep -n "swarm_balance\|portfolio\|8,77\|9,98" /root/main.py | head -20
cd /root
git add aria_terminal.html main.py
git commit -m "Fix ARIA name, agent count, position max, chat context"
git push origin master
curl -s https://web-production-548c0.up.railway.app/health
grep -n "production_models" /root/main.py | head -10
grep -n "SYMBOLS\|symbols\s*=\|model_files\|pickle.load" /root/main.py | head -15
sed -n '120,142p' /root/main.py
cd /root
echo "# force redeploy $(date)" >> main.py
git add main.py aria_terminal.html
git commit -m "Force redeploy - fix chat context and frontend name"
git push origin master
ps aux | grep python3 | grep -v grep | awk '{print $11, $12}'
curl -s https://web-production-548c0.up.railway.app/terminal 2>&1 | head -50
curl -s https://web-production-548c0.up.railway.app/api/chat/history 2>&1
grep -n "chat\|messages\|context\|history" /root/main.py | head -40
sed -n '906,960p' /root/main.py
grep -n "messages\|chat\|fetch.*chat\|user_id" /root/main.py | grep -i "frontend\|html\|js\|fetch" | head -20
grep -n "fetch\|messages\|chat\|user_id" /root/main.py | tail -60
grep -n "user_id\|fetch.*chat\|/chat\|messages" /root/main.py | grep -v "def \|cur\.\|portfolio\|paper\|history\|save_\|get_\|check_\|track" | head -30grep -n "user_id\|fetch.*chat\|/chat\|messages" /root/main.py | grep -v "def \|cur\.\|portfolio\|paper\|history\|save_\|get_\|check_\|track" | head -3
grep -n "user_id\|fetch.*chat\|/chat\|messages" /root/main.py | grep -v "def \|cur\.\|portfolio\|paper\|history\|save_\|get_\|check_\|track" | head -30
grep -n "HTMLResponse\|html_content\|return HTML\|index.html\|sendMessage\|chatInput\|userId" /root/main.py | head -20
grep -n "sendMessage\|userId\|user_id\|fetch.*chat\|/chat" /root/aria_terminal.html | head -30
grep -n "currentUserId\|userId\|generateId\|localStorage" /root/aria_terminal.html | head -30
curl -s -X POST https://web-production-548c0.up.railway.app/chat   -H "Content-Type: application/json"   -d '{"message":"what did I just say to you?","user_id":"aria-agent-system","symbol":"BTC","user_level":"intermediate"}' | python3 -m json.tool
curl -s -X POST https://web-production-548c0.up.railway.app/chat   -H "Content-Type: application/json"   -d '{"message":"hello ARIA, my name is Alee","user_id":"aria-agent-system","symbol":"BTC","user_level":"intermediate"}' | python3 -m json.tool
curl -s -X POST https://web-production-548c0.up.railway.app/chat   -H "Content-Type: application/json"   -d '{"message":"what is my name?","user_id":"aria-agent-system","symbol":"BTC","user_level":"intermediate"}' | python3 -m json.tool
grep -n "ARIA\|logo\|title\|Autonomous\|Financial Intelligence\|header" /root/aria_terminal.html | head -20
sed -n '269,278p' /root/aria_terminal.html
sed -i 's/ADVANCED RETAIL INTELLIGENCE \& ANALYTICS/AUTONOMOUS REASONING \& INTELLIGENCE ARCHITECTURE/' /root/aria_terminal.html
sed -n '269,271p' /root/aria_terminal.html
sed -i 's/ARIA Terminal - Financial Intelligence/ARIA - Autonomous Reasoning \& Intelligence Architecture/' /root/aria_terminal.html
cd /root && git add aria_terminal.html && git commit -m "fix: ARIA full name corrected in header and title" && git push origin master
grep -n "agent\|swarm\|20\|12\|count" /root/aria_terminal.html | grep -i "count\|total\|length\|agent" | head -20
grep -n "agent_name\|agentName\|agents\[]\|agent_list\|renderAgent\|AGENTS\|agents =" /root/aria_terminal.html | head -20
curl -s https://web-production-548c0.up.railway.app/api/agents 2>&1
psql -U postgres -d aria_db -c "SELECT COUNT(DISTINCT agent_id) FROM agent_decisions WHERE created_at > NOW() - INTERVAL '1 hour';"
psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT COUNT(DISTINCT agent_id) FROM agent_decisions WHERE created_at > NOW() - INTERVAL '1 hour';"
psql -U postgres -d aria_db -h 127.0.0.1 -W -c "SELECT COUNT(DISTINCT agent_id) FROM agent_decisions WHERE created_at > NOW() - INTERVAL '1 hour';"
grep -r "postgresql\|postgres.*password\|DB_PASS\|db_pass" /root/.env /root/agent_loop_v5.py 2>/dev/null | head -10
curl -s -X POST https://web-production-548c0.up.railway.app/chat   -H "Content-Type: application/json"   -d '{"message":"hello ARIA, my name is Alee","user_id":"aria-agent-system","symbol":"BTC","user_level":"intermediate"}' | python3 -m json.tool
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT COUNT(DISTINCT agent_id) FROM agent_decisions WHERE created_at > NOW() - INTERVAL '1 hour';"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "\d agent_decisions"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT COUNT(DISTINCT agent_id) FROM agent_decisions WHERE timestamp > NOW() - INTERVAL '1 hour';"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT agent_id, action, timestamp FROM agent_decisions ORDER BY timestamp DESC LIMIT 10;"
journalctl -u agent_loop -n 50 --no-pager
grep -n "Approved\|approve\|threshold\|confidence.*0\.\|min_conf\|HOLD" /root/agent_loop_v5.py | head -20
grep -n "MIN_CONFIDENCE\|min_confidence\|0\.6\|0\.7\|0\.8" /root/agent_loop_v5.py | head -20
grep -n "agent_tech\|agent_gold\|agent_aapl\|agent_tsla\|def run_agent\|def agent_" /root/agent_loop_v5.py | head -20
grep -n "agent_btc\|agent_eth\|AGENTS\|agent_list\|for.*agent\|agents\[" /root/agent_loop_v5.py | head -30
sed -n '400,500p' /root/agent_loop_v5.py
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT symbol, direction, entry_price, size_usd, status FROM positions_live;"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT symbol, direction, entry_price, size_usd, updated_at FROM positions_live ORDER BY updated_at;"
grep -n "MAX_OPEN_TRADES\|MAX_POSITIONS\|open_positions" /root/agent_loop_v5.py | head -10
journalctl -u agent_loop -n 200 --no-pager | grep -i "positions_live\|write failed\|ERROR\|error\|GLD\|ETH\|BTC" | head -30
journalctl -u agent_loop --no-pager | grep -i "ORDER.*GLD\|ORDER.*ETH\|ORDER.*BTC\|entry.*GLD\|entry.*ETH\|entry.*BTC" | head -20
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "
INSERT INTO positions_live (symbol, direction, entry_price, size_usd, regime_at_entry, sentiment_at_entry, fear_greed_at_entry, status)
VALUES 
  ('GLD',  'LONG', (SELECT price FROM market_data WHERE symbol='GLD'  ORDER BY updated_at DESC LIMIT 1), 100, 'SIDEWAYS', 0, 23, 'OPEN'),
  ('ETH',  'LONG', (SELECT price FROM market_data WHERE symbol='ETH'  ORDER BY updated_at DESC LIMIT 1), 100, 'SIDEWAYS', 0, 23, 'OPEN'),
  ('BTC',  'LONG', (SELECT price FROM market_data WHERE symbol='BTC'  ORDER BY updated_at DESC LIMIT 1), 100, 'SIDEWAYS', 0, 23, 'OPEN')
ON CONFLICT (symbol) DO NOTHING;
"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "\dt"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT symbol, close, updated_at FROM price_data WHERE symbol IN ('GLD','ETH','BTC') ORDER BY updated_at DESC LIMIT 6;"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "\d price_data"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "
INSERT INTO positions_live (symbol, direction, entry_price, size_usd, regime_at_entry, sentiment_at_entry, fear_greed_at_entry, status)
VALUES 
  ('GLD', 'LONG', (SELECT price FROM price_data WHERE symbol='GLD' ORDER BY timestamp DESC LIMIT 1), 100, 'SIDEWAYS', 0, 23, 'OPEN'),
  ('ETH', 'LONG', (SELECT price FROM price_data WHERE symbol='ETH' ORDER BY timestamp DESC LIMIT 1), 100, 'SIDEWAYS', 0, 23, 'OPEN'),
  ('BTC', 'LONG', (SELECT price FROM price_data WHERE symbol='BTC' ORDER BY timestamp DESC LIMIT 1), 100, 'SIDEWAYS', 0, 23, 'OPEN')
ON CONFLICT (symbol) DO NOTHING;
"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT symbol, direction, entry_price, size_usd, status FROM positions_live;"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT COUNT(*) FROM positions_live;"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT symbol, price FROM price_data WHERE symbol IN ('GLD','ETH','BTC') ORDER BY timestamp DESC LIMIT 3;"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "
INSERT INTO positions_live (symbol, direction, entry_price, size_usd, regime_at_entry, sentiment_at_entry, fear_greed_at_entry, status)
VALUES 
  ('GLD', 'LONG', 3230.00, 100, 'SIDEWAYS', 0, 23, 'OPEN'),
  ('ETH', 'LONG', 2185.16, 100, 'SIDEWAYS', 0, 23, 'OPEN'),
  ('BTC', 'LONG', 84500.00, 100, 'SIDEWAYS', 0, 23, 'OPEN')
ON CONFLICT (symbol) DO NOTHING;
"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT symbol, direction, entry_price, status FROM positions_live ORDER BY symbol;"
systemctl restart agent_loop && sleep 5 && journalctl -u agent_loop -n 20 --no-pager
systemctl restart agent_loop_v5 2>/dev/null || systemctl list-units | grep agent
cat /etc/systemd/system/agent_loop.service
sed -i 's|ExecStart=/root/aria-env/bin/python -u /root/agent_loop.py|ExecStart=/root/aria-env/bin/python -u /root/agent_loop_v5.py|' /etc/systemd/system/agent_loop.service
systemctl daemon-reload
systemctl restart agent_loop
sleep 5
journalctl -u agent_loop -n 20 --no-pager
grep -n "12 AGENTS\|of 12 total\|12 total\|AGENTS RUNNING" /root/aria_terminal.html
sed -i 's/SWARM ACTIVE — 12 AGENTS RUNNING/SWARM ACTIVE — 6 AGENTS RUNNING/' /root/aria_terminal.html
sed -i 's/of 12 total/of 6 total/' /root/aria_terminal.html
sed -i 's/V5 — 12 AGENTS/V5 — 6 AGENTS/' /root/aria_terminal.html
grep -n "12 AGENTS\|of 12 total\|AGENTS RUNNING" /root/aria_terminal.html
grep -n "CRITICAL RISK\|riskBadge\|risk-critical\|risk_badge" /root/aria_terminal.html | head -10
curl -s https://web-production-548c0.up.railway.app/riskscore/BTC 2>&1 | python3 -m json.tool | head -20
psql -U postgres -d aria_db -h 127.0.0.1 -p 5432 -c "SELECT COUNT(DISTINCT agent_id) FROM agent_decisions WHERE created_at > NOW() - INTERVAL '1 hour';" -W
curl -s https://web-production-548c0.up.railway.app/riskscore/BTC | python3 -m json.tool | grep -i "risk\|level\|score\|overall"
grep -n "loadRisk\|riskBadge\|risk_score\|updateRisk\|fetchRisk" /root/aria_terminal.html | head -15
sed -n '468,530p' /root/aria_terminal.html
grep -n "var score\|scoreColor\|riskBadge" /root/aria_terminal.html
sed -i 's/var scoreColor = score>70?"var(--accent-red)":score>40?"var(--accent-gold)":"var(--accent-green)";/var scoreColor = score>70?"var(--accent-red)":score>40?"var(--accent-gold)":"var(--accent-green)";\n    var badge = document.getElementById("riskBadge");\n    if(badge){ badge.textContent = score>70?"HIGH RISK":score>40?"MODERATE":("LOW RISK"); badge.className = "risk-badge " + (score>70?"risk-critical":score>40?"risk-warning":"risk-safe"); }/' /root/aria_terminal.html
sed -n '490,496p' /root/aria_terminal.html
sed -i 's/.risk-critical { background:rgba(239,68,68,0.12); color:var(--accent-red); border:1px solid rgba(239,68,68,0.4); }/.risk-critical { background:rgba(239,68,68,0.12); color:var(--accent-red); border:1px solid rgba(239,68,68,0.4); }\n.risk-warning { background:rgba(245,158,11,0.12); color:var(--accent-gold); border:1px solid rgba(245,158,11,0.4); }\n.risk-safe { background:rgba(34,197,94,0.12); color:var(--accent-green); border:1px solid rgba(34,197,94,0.4); }/' /root/aria_terminal.html
cd /root && git add aria_terminal.html && git commit -m "fix: dynamic risk badge, agent count 6, ARIA full name" && git push origin master
grep -n "window.onload\|DOMContentLoaded\|loadPortfolio\|init\(\|onload" /root/aria_terminal.html | head -15
grep -n "window.onload\|DOMContentLoaded\|loadPortfolio\|onload" /root/aria_terminal.html | head -15
sed -n '378,392p' /root/aria_terminal.html
sed -n '355,380p' /root/aria_terminal.html
grep -n "loadMarket\|loadSwarm\|loadNews\|setTimeout\|setInterval\|startUp\|start()" /root/aria_terminal.html | head -20
sed -n '1050,1075p' /root/aria_terminal.html
sed -i 's/async function init() {/async function init() {\n  await loadRiskPanel();/' /root/aria_terminal.html
sed -n '1053,1062p' /root/aria_terminal.html
cd /root && git add aria_terminal.html && git commit -m "fix: risk badge updates on page load" && git push origin master
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "\dt" | wc -l
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT symbol, COUNT(*) as records, MAX(timestamp) as latest FROM price_data GROUP BY symbol ORDER BY latest DESC;"
grep -n "price_data\|INSERT.*price" /root/aria_market_updater.py | head -10
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT symbol, price, updated_at FROM market_state_latest ORDER BY updated_at DESC LIMIT 10;"
sed -i 's|async function init() {|async function updateRiskBadge() {\n  try {\n    var r = await fetch(API + "/riskscore/BTC?direction=LONG\&amount_usd=100\&user_id=aria-agent-system");\n    var d = await r.json();\n    var score = d.risk_metrics.risk_score;\n    var badge = document.getElementById("riskBadge");\n    if (!badge) return;\n    if (score > 70) { badge.textContent = "CRITICAL RISK"; badge.className = "risk-badge risk-critical"; }\n    else if (score > 40) { badge.textContent = "MODERATE RISK"; badge.className = "risk-badge risk-warning"; }\n    else { badge.textContent = "LOW RISK"; badge.className = "risk-badge risk-safe"; }\n  } catch(e) {}\n}\nasync function init() {|' /root/aria_terminal.html
sed -i 's|await Promise.all(\[loadAssets(), loadIntelligence(), loadRightPanel()\]);|updateRiskBadge();\n  setInterval(updateRiskBadge, 300000);\n  await Promise.all([loadAssets(), loadIntelligence(), loadRightPanel()]);|' /root/aria_terminal.html
sed -n '1053,1068p' /root/aria_terminal.html
sed -i 's|  await loadRiskPanel();\n  updateRiskBadge();|  updateRiskBadge();|' /root/aria_terminal.html
sed -n '1065,1075p' /root/aria_terminal.html
sed -i '/await loadRiskPanel();/d' /root/aria_terminal.html
sed -n '1065,1075p' /root/aria_terminal.html
cd /root && git add aria_terminal.html && git commit -m "fix: independent risk badge updater on page load" && git push origin master
python3 aria_nlp_service.py 2>&1 | tail -5
pip install praw requests feedparser --break-system-packages 2>&1 | tail -3
python3 -c "from transformers import pipeline; print('pipeline ready')"
cat > /root/aria_nlp_service.py << 'EOF'
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
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=BTC-USD,ETH-USD,AAPL,NVDA,TSLA&region=US&lang=en-US",
    "https://www.investing.com/rss/news.rss",
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
EOF

wc -l /root/aria_nlp_service.py && tail -5 /root/aria_nlp_service.py
cd /root && python3 aria_nlp_service.py 2>&1 | head -20
grep -n "loadAgents\|api/agents\|agent_decisions\|/agents" /root/aria_terminal.html | head -15
sed -n '710,775p' /root/aria_terminal.html
curl -s https://web-production-548c0.up.railway.app/agent/reports | python3 -m json.tool | head -20
grep -n "agent/reports\|agent_reports\|agent_decisions" /root/main.py | head -20
grep -n "POST\|requests\|agent\|decisions\|reports" /root/aria_db_sync.py | head -20
sed -n '1,110p' /root/aria_db_sync.py
cat >> /root/aria_db_sync.py << 'EOF'

def post_agent_reports(reports):
    try:
        payload = {'reports': reports}
        resp = requests.post(RAILWAY_APP_URL + '/agent/reports/sync', json=payload, timeout=10)
        log.info('Posted ' + str(len(reports)) + ' agent reports to frontend: ' + str(resp.status_code))
    except Exception as e:
        log.error('Agent reports POST failed: ' + str(e))

def sync_agent_decisions(hcur):
    try:
        hcur.execute("""
            SELECT agent_id, symbol, action, confidence, reasoning, timestamp 
            FROM agent_decisions 
            ORDER BY timestamp DESC LIMIT 100
        """)
        rows = hcur.fetchall()
        reports = [{'agent_id': r[0], 'symbol': r[1], 'action': r[2], 
                    'confidence': float(r[3]) if r[3] else 0.5, 
                    'reasoning': r[4], 'timestamp': r[5].isoformat(),
                    'agent_type': 'SPECIALIST'} for r in rows]
        post_agent_reports(reports)
        log.info('Synced ' + str(len(reports)) + ' agent decisions')
    except Exception as e:
        log.warning('Agent decisions sync skipped: ' + str(e))
EOF

grep -n "sync_system_state\|sync_positions" /root/aria_db_sync.py
sed -i 's/            sync_system_state(hcur, rcur)/            sync_system_state(hcur, rcur)\n            sync_agent_decisions(hcur)/' /root/aria_db_sync.py
sed -n '78,84p' /root/aria_db_sync.py
grep -n "def get_agent_reports\|agent/reports" /root/main.py
sed -n '1196,1202p' /root/main.py
sed -i 's|@app.get("/agent/reports")\ndef get_agent_reports():\n    return {"reports": _agent_reports\[:50\], "count": len(_agent_reports), "timestamp": datetime.now().isoformat()}|@app.get("/agent/reports")\ndef get_agent_reports():\n    return {"reports": _agent_reports[:50], "count": len(_agent_reports), "timestamp": datetime.now().isoformat()}\n\n@app.post("/agent/reports/sync")\ndef sync_agent_reports(data: dict):\n    global _agent_reports\n    reports = data.get("reports", [])\n    _agent_reports = reports\n    save_agent_reports(_agent_reports)\n    return {"success": True, "count": len(_agent_reports)}|' /root/main.py
grep -n "agent/reports/sync\|sync_agent_reports" /root/main.py
python3 << 'EOF'
with open('/root/main.py', 'r') as f:
    content = f.read()

new_endpoint = '''
@app.post("/agent/reports/sync")
def sync_agent_reports(data: dict):
    global _agent_reports
    reports = data.get("reports", [])
    _agent_reports = reports
    save_agent_reports(_agent_reports)
    return {"success": True, "count": len(_agent_reports)}
'''

content = content.replace(
    '@app.get("/agent/reports")',
    new_endpoint + '@app.get("/agent/reports")'
)

with open('/root/main.py', 'w') as f:
    f.write(content)

print("Done")
EOF

grep -n "agent/reports/sync\|sync_agent_reports" /root/main.py
cd /root && git add main.py aria_db_sync.py && git commit -m "fix: agent decisions sync Hetzner->Railway via /agent/reports/sync" && git push origin master && systemctl restart aria_db_sync
journalctl -u aria_db_sync -n 20 --no-pager
sleep 60 && journalctl -u aria_db_sync -n 30 --no-pager
journalctl -u aria_db_sync -n 50 --no-pager | grep -i "error\|failed\|exception\|traceback"
systemctl status aria_db_sync
cd /root && python3 aria_db_sync.py 2>&1 | head -30
python3 << 'EOF'
with open('/root/aria_db_sync.py', 'r') as f:
    content = f.read()

# Extract the two new functions we appended
new_funcs = """
def post_agent_reports(reports):
    try:
        payload = {'reports': reports}
        resp = requests.post(RAILWAY_APP_URL + '/agent/reports/sync', json=payload, timeout=10)
        log.info('Posted ' + str(len(reports)) + ' agent reports to frontend: ' + str(resp.status_code))
    except Exception as e:
        log.error('Agent reports POST failed: ' + str(e))

def sync_agent_decisions(hcur):
    try:
        hcur.execute(\"\"\"
            SELECT agent_id, symbol, action, confidence, reasoning, timestamp 
            FROM agent_decisions 
            ORDER BY timestamp DESC LIMIT 100
        \"\"\")
        rows = hcur.fetchall()
        reports = [{'agent_id': r[0], 'symbol': r[1], 'action': r[2], 
                    'confidence': float(r[3]) if r[3] else 0.5, 
                    'reasoning': r[4], 'timestamp': r[5].isoformat(),
                    'agent_type': 'SPECIALIST'} for r in rows]
        post_agent_reports(reports)
        log.info('Synced ' + str(len(reports)) + ' agent decisions')
    except Exception as e:
        log.warning('Agent decisions sync skipped: ' + str(e))
"""

# Remove appended functions from end
content = content.replace(new_funcs, '')

# Insert before def run()
content = content.replace('def run():', new_funcs + '\ndef run():')

with open('/root/aria_db_sync.py', 'w') as f:
    f.write(content)

print("Done")
EOF

python3 aria_db_sync.py 2>&1 | head -20
systemctl restart aria_db_sync
ls /root/aria_nlp* 2>/dev/null || echo "No NLP files yet"
df -h / && free -h && python3 -c "import transformers; print('transformers ready')" 2>/dev/null || echo "transformers not installed"
pip install transformers torch --break-system-packages 2>&1 | tail -5
ls -lh ~/.cache/huggingface/hub/
nohup python3 /root/aria_nlp_service.py > /root/nlp_service.log 2>&1 &
echo "PID: $!"
sleep 30 && tail -20 /root/nlp_service.log
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT symbol, score, label, fomc_signal, timestamp FROM nlp_sentiment ORDER BY timestamp DESC LIMIT 10;"
python3 << 'EOF'
with open('/root/aria_nlp_service.py', 'r') as f:
    content = f.read()

old_feeds = '''NEWS_FEEDS = [
    "https://feeds.feedburner.com/CoinTelegraph",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=BTC-USD,ETH-USD,AAPL,NVDA,TSLA&region=US&lang=en-US",
    "https://www.investing.com/rss/news.rss",
]'''

new_feeds = '''NEWS_FEEDS = [
    "https://feeds.feedburner.com/CoinTelegraph",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=BTC-USD,ETH-USD,AAPL,NVDA,TSLA,GLD&region=US&lang=en-US",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC%3DF&region=US&lang=en-US",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cryptonews.com/news/feed/",
]'''

content = content.replace(old_feeds, new_feeds)

with open('/root/aria_nlp_service.py', 'w') as f:
    f.write(content)

print("Done")
EOF

pkill -f aria_nlp_service && sleep 2 && nohup python3 /root/aria_nlp_service.py > /root/nlp_service.log 2>&1 & && sleep 60 && tail -10 /root/nlp_service.log
pkill -f aria_nlp_service
sleep 2
nohup python3 /root/aria_nlp_service.py > /root/nlp_service.log 2>&1 &
sleep 60 && tail -10 /root/nlp_service.log
cat > /etc/systemd/system/aria_nlp.service << 'EOF'
[Unit]
Description=ARIA NLP Sentiment Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=/usr/bin/python3 /root/aria_nlp_service.py
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable aria_nlp
systemctl start aria_nlp
systemctl status aria_nlp --no-pager
grep -n "def generate_signal" /root/agent_loop_v5.py
sed -n '206,330p' /root/agent_loop_v5.py
python3 << 'EOF'
with open('/root/agent_loop_v5.py', 'r') as f:
    content = f.read()

nlp_function = '''
def get_nlp_sentiment(symbol):
    """Read latest NLP sentiment score from DB for this symbol."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT score, label, fomc_signal 
            FROM nlp_sentiment 
            WHERE symbol=%s 
            ORDER BY timestamp DESC LIMIT 1
        """, (symbol,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            return {'score': float(row[0]), 'label': row[1], 'fomc': row[2]}
    except Exception as e:
        pass
    return {'score': 0.0, 'label': 'NEUTRAL', 'fomc': 'NEUTRAL'}

'''

content = content.replace('def generate_signal(', nlp_function + 'def generate_signal(')

with open('/root/agent_loop_v5.py', 'w') as f:
    f.write(content)

print("Done")
EOF

grep -n "def get_nlp_sentiment\|def generate_signal" /root/agent_loop_v5.py
python3 << 'EOF'
with open('/root/agent_loop_v5.py', 'r') as f:
    content = f.read()

old = "    if final_dir is None:\n        return 'HOLD', final_conf, None\n\n    return ('BUY' if final_dir == 'LONG' else 'SELL'), final_conf, final_dir"

new = """    if final_dir is None:
        return 'HOLD', final_conf, None

    # ── Step 4: NLP sentiment modifier ───────────────────
    try:
        nlp = get_nlp_sentiment(symbol)
        nlp_score = nlp['score']
        nlp_label = nlp['label']
        fomc      = nlp['fomc']

        # NLP agrees with direction → boost confidence
        if final_dir == 'LONG' and nlp_score > 0.1:
            final_conf = min(0.92, final_conf + 0.05)
            log.info(f"  {symbol} NLP BOOST: {nlp_label} ({nlp_score:+.3f}) → conf:{final_conf:.3f}")
        elif final_dir == 'SHORT' and nlp_score < -0.1:
            final_conf = min(0.92, final_conf + 0.05)
            log.info(f"  {symbol} NLP BOOST: {nlp_label} ({nlp_score:+.3f}) → conf:{final_conf:.3f}")
        # NLP disagrees → reduce confidence
        elif final_dir == 'LONG' and nlp_score < -0.15:
            final_conf = max(0.45, final_conf - 0.03)
            log.info(f"  {symbol} NLP DRAG: {nlp_label} ({nlp_score:+.3f}) → conf:{final_conf:.3f}")
        elif final_dir == 'SHORT' and nlp_score > 0.15:
            final_conf = max(0.45, final_conf - 0.03)
            log.info(f"  {symbol} NLP DRAG: {nlp_label} ({nlp_score:+.3f}) → conf:{final_conf:.3f}")

        # FOMC hawkish → risk-off, reduce confidence on risky assets
        if fomc == 'HAWKISH' and symbol in ['BTC','ETH','NVDA','TSLA']:
            final_conf = max(0.45, final_conf - 0.05)
            log.info(f"  {symbol} FOMC HAWKISH penalty → conf:{final_conf:.3f}")
        elif fomc == 'DOVISH' and symbol == 'GLD':
            final_conf = max(0.45, final_conf - 0.03)
            log.info(f"  {symbol} FOMC DOVISH GLD drag → conf:{final_conf:.3f}")
    except Exception as e:
        log.warning(f"NLP modifier failed for {symbol}: {e}")

    return ('BUY' if final_dir == 'LONG' else 'SELL'), final_conf, final_dir"""

content = content.replace(old, new)

with open('/root/agent_loop_v5.py', 'w') as f:
    f.write(content)

print("Done")
EOF

grep -n "NLP BOOST\|NLP DRAG\|FOMC HAWKISH" /root/agent_loop_v5.py
systemctl restart agent_loop && sleep 10 && journalctl -u agent_loop -n 30 --no-pager | grep -E "NLP|FOMC|conf:|Cycle"
grep -n "get_nlp_sentiment" /root/agent_loop_v5.py | head -5
cd /root && git add agent_loop_v5.py aria_nlp_service.py && git commit -m "feat: Cap 1 NLP complete - FinBERT sentiment wired into generate_signal" && git push origin master
systemctl status jobpilot && journalctl -u jobpilot -n 20 --no-pager
cat /root/.env
cat /root/JobPilot/.env 2>/dev/null || cat /root/JobPilot/config.py 2>/dev/null || grep -r "API_KEY\|api_key\|secret\|token" /root/JobPilot/*.py 2>/dev/null | grep -v "^Binary" | head -20
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "\d closed_trades"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT COUNT(*), outcome FROM closed_trades GROUP BY outcome;"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT symbol, direction, pnl_pct, regime_at_entry, fear_greed_at_entry, outcome FROM closed_trades ORDER BY id DESC LIMIT 10;"
cat > /root/aria_episodic_memory.py << 'EOF'
import psycopg2
import logging

log = logging.getLogger()

DB = {"host":"localhost","port":5432,"dbname":"aria_db","user":"postgres","password":"aria_secure_2026"}

def get_db():
    return psycopg2.connect(**DB)

def ensure_table():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS episodic_memory (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10),
            direction VARCHAR(10),
            regime VARCHAR(20),
            fear_greed_bucket VARCHAR(10),
            nlp_label VARCHAR(20),
            fomc_signal VARCHAR(20),
            outcome VARCHAR(10),
            pnl_pct FLOAT,
            timestamp TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def recall(symbol, direction, regime, fear_greed, nlp_label='NEUTRAL', fomc='NEUTRAL'):
    """
    Query similar past episodes and return win rate + avg pnl.
    Similarity: same symbol + direction + regime + fear_greed bucket
    """
    try:
        fg_bucket = 'EXTREME_FEAR' if fear_greed < 25 else \
                    'FEAR' if fear_greed < 45 else \
                    'NEUTRAL' if fear_greed < 55 else \
                    'GREED' if fear_greed < 75 else 'EXTREME_GREED'

        conn = get_db()
        cur = conn.cursor()

        # Query similar episodes from closed_trades
        cur.execute("""
            SELECT outcome, pnl_pct FROM closed_trades
            WHERE symbol=%s
            AND direction=%s
            AND regime_at_entry=%s
            AND ABS(fear_greed_at_entry - %s) <= 15
        """, (symbol, direction, regime, fear_greed))

        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            return {'win_rate': None, 'avg_pnl': None, 'sample_size': 0, 'confidence_modifier': 0.0}

        wins = sum(1 for r in rows if r[0] == 'WIN')
        win_rate = wins / len(rows)
        avg_pnl = sum(r[1] for r in rows) / len(rows)

        # Confidence modifier based on historical win rate
        if win_rate >= 0.70 and len(rows) >= 3:
            modifier = +0.05
        elif win_rate >= 0.60 and len(rows) >= 3:
            modifier = +0.03
        elif win_rate <= 0.40 and len(rows) >= 3:
            modifier = -0.05
        elif win_rate <= 0.30 and len(rows) >= 3:
            modifier = -0.08
        else:
            modifier = 0.0

        return {
            'win_rate': round(win_rate, 3),
            'avg_pnl': round(avg_pnl, 4),
            'sample_size': len(rows),
            'confidence_modifier': modifier,
            'fg_bucket': fg_bucket
        }

    except Exception as e:
        log.warning(f"Episodic recall failed for {symbol}: {e}")
        return {'win_rate': None, 'avg_pnl': None, 'sample_size': 0, 'confidence_modifier': 0.0}

if __name__ == "__main__":
    ensure_table()
    print("Episodic memory table ready")
    # Test recall
    result = recall('NVDA', 'LONG', 'NORMAL', 23)
    print(f"NVDA LONG NORMAL F&G:23 → {result}")
EOF

python3 /root/aria_episodic_memory.py
python3 << 'EOF'
with open('/root/agent_loop_v5.py', 'r') as f:
    content = f.read()

# Add import at top of generate_signal area
old = "def get_nlp_sentiment(symbol):"

new = """def get_episodic_modifier(symbol, direction, regime, fear_greed):
    \"\"\"Query episodic memory for historical win rate in similar conditions.\"\"\"
    try:
        from aria_episodic_memory import recall
        result = recall(symbol, direction, regime, fear_greed)
        if result['sample_size'] >= 3:
            log.info(f"  {symbol} EPISODIC: wr:{result['win_rate']:.0%} n:{result['sample_size']} modifier:{result['confidence_modifier']:+.2f}")
        return result['confidence_modifier']
    except Exception as e:
        log.warning(f"Episodic memory failed: {e}")
        return 0.0

def get_nlp_sentiment(symbol):"""

content = content.replace(old, new)

with open('/root/agent_loop_v5.py', 'w') as f:
    f.write(content)

print("Done")
EOF

python3 << 'EOF'
with open('/root/agent_loop_v5.py', 'r') as f:
    content = f.read()

old = "    return ('BUY' if final_dir == 'LONG' else 'SELL'), final_conf, final_dir"

new = """    # ── Step 5: Episodic memory modifier ─────────────────
    try:
        ep_modifier = get_episodic_modifier(symbol, final_dir, regime, fg)
        final_conf = min(0.92, max(0.45, final_conf + ep_modifier))
    except Exception as e:
        log.warning(f"Episodic modifier failed: {e}")

    return ('BUY' if final_dir == 'LONG' else 'SELL'), final_conf, final_dir"""

content = content.replace(old, new)

with open('/root/agent_loop_v5.py', 'w') as f:
    f.write(content)

print("Done")
EOF

grep -n "EPISODIC\|get_episodic_modifier\|Step 5" /root/agent_loop_v5.py
systemctl restart agent_loop && sleep 10 && journalctl -u agent_loop -n 20 --no-pager
python3 << 'EOF'
import sys
sys.path.insert(0, '/root')

# Test NLP sentiment is reading correctly
import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='aria_db', user='postgres', password='aria_secure_2026')
cur = conn.cursor()
cur.execute("SELECT symbol, score, label, fomc_signal, timestamp FROM nlp_sentiment ORDER BY timestamp DESC LIMIT 6")
rows = cur.fetchall()
print("=== Latest NLP Scores ===")
for r in rows:
    print(f"{r[0]}: {r[2]} ({r[1]:+.3f}) FOMC:{r[3]} @ {r[4]}")
cur.close()
conn.close()
EOF

python3 << 'EOF'
from aria_episodic_memory import recall

symbols = ['BTC','ETH','AAPL','NVDA','TSLA','GLD']
directions = ['LONG','SHORT']
regimes = ['NORMAL','CRISIS']

print("=== Episodic Memory Recall Test ===")
for symbol in symbols:
    for direction in directions:
        for regime in regimes:
            result = recall(symbol, direction, regime, 23)
            if result['sample_size'] > 0:
                print(f"{symbol} {direction} {regime}: wr:{result['win_rate']:.0%} n:{result['sample_size']} modifier:{result['confidence_modifier']:+.2f} avg_pnl:{result['avg_pnl']:+.3f}")
EOF

python3 << 'EOF'
import sys
sys.path.insert(0, '/root')
from agent_loop_v5 import get_nlp_sentiment, get_episodic_modifier

print("=== NLP Sentiment Test ===")
for symbol in ['BTC','ETH','AAPL','NVDA','TSLA','GLD']:
    nlp = get_nlp_sentiment(symbol)
    print(f"{symbol}: {nlp['label']} ({nlp['score']:+.3f}) FOMC:{nlp['fomc']}")

print("\n=== Episodic Modifier Test ===")
for symbol in ['BTC','ETH','AAPL','NVDA','TSLA','GLD']:
    mod = get_episodic_modifier(symbol, 'LONG', 'NORMAL', 23)
    print(f"{symbol} LONG NORMAL F&G:23: modifier={mod:+.2f}")
EOF

cd /root && git add agent_loop_v5.py aria_episodic_memory.py aria_nlp_service.py && git commit -m "feat: Cap 1 NLP + Cap 3 Episodic Memory - tested and integrated" && git push origin master
grep -n "def get_features\|features\|feature_vector\|build_features" /root/aria_model_inference.py | head -15
sed -n '133,230p' /root/aria_model_inference.py
cat > /root/aria_ood_detector.py << 'EOF'
import numpy as np
import psycopg2
import logging

log = logging.getLogger()

DB = {"host":"localhost","port":5432,"dbname":"aria_db","user":"postgres","password":"aria_secure_2026"}

FEATURE_NAMES = [
    'rsi','macd','macd_hist','volatility','bb_position','ma_distance',
    'price_change_5','price_change_10','price_change_24',
    'rsi_momentum','volume_ratio','volume_trend',
    'rsi_4h','dist_from_high','dist_from_low','range_position',
    'candle_range','candle_close_pos','upper_wick','lower_wick',
    'adx_proxy','z_score','momentum_5','momentum_10',
    'atr_pct','vpin_norm','vpin_signal'
]
EOF

wc -l /root/aria_ood_detector.py
cat >> /root/aria_ood_detector.py << 'EOF'

FEATURE_STATS = {
    'rsi':            {'mean': 50.0,  'std': 15.0},
    'macd':           {'mean': 0.0,   'std': 100.0},
    'macd_hist':      {'mean': 0.0,   'std': 50.0},
    'volatility':     {'mean': 0.02,  'std': 0.01},
    'bb_position':    {'mean': 0.5,   'std': 0.25},
    'ma_distance':    {'mean': 0.0,   'std': 3.0},
    'price_change_5': {'mean': 0.0,   'std': 2.0},
    'price_change_10':{'mean': 0.0,   'std': 3.0},
    'price_change_24':{'mean': 0.0,   'std': 5.0},
    'rsi_momentum':   {'mean': 0.0,   'std': 5.0},
    'volume_ratio':   {'mean': 1.0,   'std': 0.5},
    'volume_trend':   {'mean': 0.0,   'std': 0.3},
    'rsi_4h':         {'mean': 50.0,  'std': 15.0},
    'dist_from_high': {'mean': 5.0,   'std': 4.0},
    'dist_from_low':  {'mean': 5.0,   'std': 4.0},
    'range_position': {'mean': 0.5,   'std': 0.25},
    'candle_range':   {'mean': 0.5,   'std': 0.4},
    'candle_close_pos':{'mean': 0.5,  'std': 0.1},
    'upper_wick':     {'mean': 0.0,   'std': 0.001},
    'lower_wick':     {'mean': 0.0,   'std': 0.001},
    'adx_proxy':      {'mean': 1.0,   'std': 0.8},
    'z_score':        {'mean': 0.0,   'std': 1.5},
    'momentum_5':     {'mean': 0.0,   'std': 0.02},
    'momentum_10':    {'mean': 0.0,   'std': 0.03},
    'atr_pct':        {'mean': 1.5,   'std': 1.0},
    'vpin_norm':      {'mean': 0.5,   'std': 0.2},
    'vpin_signal':    {'mean': 0.0,   'std': 1.0},
}
EOF

wc -l /root/aria_ood_detector.py
cat >> /root/aria_ood_detector.py << 'EOF'

def detect_ood(symbol, features):
    try:
        if features is None:
            return {'ood_score': 0.0, 'is_ood': False, 'size_multiplier': 1.0, 'reason': 'no_features'}

        fvec = features[0]
        z_scores = []

        for i, fname in enumerate(FEATURE_NAMES):
            if fname in FEATURE_STATS:
                mean = FEATURE_STATS[fname]['mean']
                std  = FEATURE_STATS[fname]['std']
                if std > 0:
                    z = abs((fvec[i] - mean) / std)
                    z_scores.append((fname, z))

        if not z_scores:
            return {'ood_score': 0.0, 'is_ood': False, 'size_multiplier': 1.0, 'reason': 'no_stats'}

        outliers = [(f, z) for f, z in z_scores if z > 2.0]
        ood_score = len(outliers) / len(z_scores)

        if ood_score > 0.4:
            is_ood = True
            size_multiplier = 0.25
            reason = f"EXTREME_OOD: {len(outliers)}/{len(z_scores)} features outlying"
        elif ood_score > 0.25:
            is_ood = True
            size_multiplier = 0.50
            reason = f"MODERATE_OOD: {len(outliers)}/{len(z_scores)} features outlying"
        elif ood_score > 0.15:
            is_ood = False
            size_multiplier = 0.75
            reason = f"MILD_OOD: {len(outliers)}/{len(z_scores)} features outlying"
        else:
            is_ood = False
            size_multiplier = 1.0
            reason = "IN_DISTRIBUTION"

        return {
            'ood_score': round(ood_score, 3),
            'is_ood': is_ood,
            'size_multiplier': size_multiplier,
            'reason': reason,
            'outlier_features': [f for f, z in outliers[:3]]
        }

    except Exception as e:
        log.warning(f"OOD detection failed for {symbol}: {e}")
        return {'ood_score': 0.0, 'is_ood': False, 'size_multiplier': 1.0, 'reason': 'error'}
EOF

wc -l /root/aria_ood_detector.py
cat >> /root/aria_ood_detector.py << 'EOF'

if __name__ == "__main__":
    import sys
    sys.path.insert(0, '/root')
    from aria_model_inference import build_feature_vector
    print("=== OOD Detection Test ===")
    for symbol in ['BTC','ETH','AAPL','NVDA','TSLA','GLD']:
        features = build_feature_vector(symbol)
        result = detect_ood(symbol, features)
        print(f"{symbol}: {result['reason']} | size_mult:{result['size_multiplier']} | ood_score:{result['ood_score']}")
EOF

python3 /root/aria_ood_detector.py
grep -n "def kelly_size" /root/agent_loop_v5.py
sed -n '186,206p' /root/agent_loop_v5.py
python3 << 'EOF'
with open('/root/agent_loop_v5.py', 'r') as f:
    content = f.read()

old = "    max_pct={'BTC':0.15,'ETH':0.12,'GLD':0.15,'NVDA':0.10,'AAPL':0.10,'TSLA':0.08}.get(symbol,0.10)"

new = """    # OOD check — reduce size if conditions are unusual
    ood_mult = 1.0
    try:
        from aria_ood_detector import detect_ood
        from aria_model_inference import build_feature_vector
        features = build_feature_vector(symbol)
        ood = detect_ood(symbol, features)
        ood_mult = ood['size_multiplier']
        if ood_mult < 1.0:
            log.info(f"  {symbol} OOD: {ood['reason']} size_mult:{ood_mult}")
    except Exception as e:
        pass
    max_pct={'BTC':0.15,'ETH':0.12,'GLD':0.15,'NVDA':0.10,'AAPL':0.10,'TSLA':0.08}.get(symbol,0.10)"""

content = content.replace(old, new)

old2 = "    adjusted=kelly*regime_mult*fg_mult*vol_mult*vel_mult*world_mult"
new2 = "    adjusted=kelly*regime_mult*fg_mult*vol_mult*vel_mult*world_mult*ood_mult"

content = content.replace(old2, new2)

with open('/root/agent_loop_v5.py', 'w') as f:
    f.write(content)

print("Done")
EOF

grep -n "ood_mult\|OOD" /root/agent_loop_v5.py | head -10
systemctl restart agent_loop && sleep 10 && journalctl -u agent_loop -n 15 --no-pager
cd /root && git add agent_loop_v5.py aria_ood_detector.py aria_episodic_memory.py && git commit -m "feat: Cap 4 OOD Detection - position size reduction in unknown regimes" && git push origin master
systemctl status agent_loop aria_nlp aria_db_sync --no-pager | grep -E "Active|Main PID"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT COUNT(*) FROM episodic_memory;"
grep -n "def close_position" /root/agent_loop_v5.py
sed -n '134,175p' /root/agent_loop_v5.py
sed -n '175,185p' /root/agent_loop_v5.py
python3 << 'EOF'
with open('/root/agent_loop_v5.py', 'r') as f:
    content = f.read()

old = '        cur.execute("UPDATE positions_live SET status=\'CLOSED\', updated_at=NOW() WHERE symbol=%s", [symbol])\n        conn.commit(); cur.close(); conn.close()'

new = '''        cur.execute("UPDATE positions_live SET status='CLOSED', updated_at=NOW() WHERE symbol=%s", [symbol])
        # Write to episodic memory with full context
        try:
            from aria_nlp_service import get_nlp_sentiment
            nlp = get_nlp_sentiment(symbol) if hasattr(__builtins__, '__import__') else {'label':'NEUTRAL','fomc':'NEUTRAL'}
        except:
            nlp = {'label':'NEUTRAL','fomc':'NEUTRAL'}
        fg_bucket = 'EXTREME_FEAR' if sentiment.get('fear_greed',50)<25 else 'FEAR' if sentiment.get('fear_greed',50)<45 else 'NEUTRAL' if sentiment.get('fear_greed',50)<55 else 'GREED' if sentiment.get('fear_greed',50)<75 else 'EXTREME_GREED'
        cur.execute("""INSERT INTO episodic_memory (symbol, direction, regime, fear_greed_bucket, nlp_label, fomc_signal, outcome, pnl_pct)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            [symbol, direction, regime, fg_bucket, nlp.get('label','NEUTRAL'), nlp.get('fomc','NEUTRAL'), outcome, round(pnl_pct,6)])
        conn.commit(); cur.close(); conn.close()'''

content = content.replace(old, new)

with open('/root/agent_loop_v5.py', 'w') as f:
    f.write(content)

print("Done")
EOF

grep -n "episodic_memory\|fg_bucket\|nlp_label" /root/agent_loop_v5.py | head -10
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "
INSERT INTO episodic_memory (symbol, direction, regime, fear_greed_bucket, nlp_label, fomc_signal, outcome, pnl_pct)
SELECT 
    symbol, direction, regime_at_entry,
    CASE 
        WHEN fear_greed_at_entry < 25 THEN 'EXTREME_FEAR'
        WHEN fear_greed_at_entry < 45 THEN 'FEAR'
        WHEN fear_greed_at_entry < 55 THEN 'NEUTRAL'
        WHEN fear_greed_at_entry < 75 THEN 'GREED'
        ELSE 'EXTREME_GREED'
    END,
    'NEUTRAL', 'NEUTRAL', outcome, pnl_pct
FROM closed_trades;
"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "\d episodic_memory"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "ALTER TABLE episodic_memory ALTER COLUMN fear_greed_bucket TYPE character varying(20);"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "
INSERT INTO episodic_memory (symbol, direction, regime, fear_greed_bucket, nlp_label, fomc_signal, outcome, pnl_pct)
SELECT symbol, direction, regime_at_entry,
    CASE 
        WHEN fear_greed_at_entry < 25 THEN 'EXTREME_FEAR'
        WHEN fear_greed_at_entry < 45 THEN 'FEAR'
        WHEN fear_greed_at_entry < 55 THEN 'NEUTRAL'
        WHEN fear_greed_at_entry < 75 THEN 'GREED'
        ELSE 'EXTREME_GREED'
    END,
    'NEUTRAL', 'NEUTRAL', outcome, pnl_pct
FROM closed_trades;
"
PGPASSWORD=aria_secure_2026 psql -U postgres -d aria_db -h 127.0.0.1 -c "SELECT symbol, outcome, COUNT(*) FROM episodic_memory GROUP BY symbol, outcome ORDER BY symbol;"
python3 << 'EOF'
from aria_episodic_memory import recall

print("=== Episodic Memory Test (populated) ===")
for symbol in ['BTC','ETH','AAPL','NVDA','TSLA','GLD']:
    for direction in ['LONG','SHORT']:
        result = recall(symbol, direction, 'NORMAL', 23)
        if result['sample_size'] > 0:
            print(f"{symbol} {direction} NORMAL: wr:{result['win_rate']:.0%} n:{result['sample_size']} modifier:{result['confidence_modifier']:+.2f}")
EOF

systemctl restart agent_loop && sleep 5 && journalctl -u agent_loop -n 5 --no-pager
cd /root && git add agent_loop_v5.py aria_episodic_memory.py && git commit -m "feat: Cap 3 complete - episodic memory writes on trade close, 618 trades backfilled" && git push origin master
pip install newsapi-python --break-system-packages 2>&1 | tail -3
echo "NEWSAPI_KEY=79812f8bd44a444ea9d6627d13d69368" >> /root/.env
grep "NEWSAPI_KEY" /root/.env
grep -n "NEWS_FEEDS\|SYMBOL_KEYWORDS\|newsapi\|NEWSAPI" /root/aria_nlp_service.py | head -10
python3 << 'EOF'
with open('/root/aria_nlp_service.py', 'r') as f:
    content = f.read()

old = "def fetch_headlines():"

new = '''def fetch_newsapi_headlines(symbol):
    """Fetch headlines from NewsAPI for a specific symbol."""
    try:
        import os
        from newsapi import NewsApiClient
        key = os.getenv('NEWSAPI_KEY', '79812f8bd44a444ea9d6627d13d69368')
        newsapi = NewsApiClient(api_key=key)
        query_map = {
            'BTC': 'bitcoin OR crypto', 'ETH': 'ethereum OR ether',
            'AAPL': 'Apple stock', 'NVDA': 'Nvidia GPU chips',
            'TSLA': 'Tesla Elon', 'GLD': 'gold price safe haven'
        }
        q = query_map.get(symbol, symbol)
        articles = newsapi.get_everything(q=q, language='en', sort_by='publishedAt', page_size=10)
        headlines = [a['title'] for a in articles.get('articles', []) if a.get('title')]
        log.info(f"NewsAPI: {len(headlines)} headlines for {symbol}")
        return headlines
    except Exception as e:
        log.warning(f"NewsAPI failed for {symbol}: {e}")
        return []

def fetch_headlines():'''

content = content.replace(old, new)

with open('/root/aria_nlp_service.py', 'w') as f:
    f.write(content)

print("Done")
EOF

python3 << 'EOF'
with open('/root/aria_nlp_service.py', 'r') as f:
    content = f.read()

old = "    keywords = SYMBOL_KEYWORDS.get(symbol, [])\n    relevant = [h for h in headlines if any(k in h.lower() for k in keywords)]"

new = "    keywords = SYMBOL_KEYWORDS.get(symbol, [])\n    relevant = [h for h in headlines if any(k in h.lower() for k in keywords)]\n    # Add NewsAPI headlines for better coverage\n    relevant += fetch_newsapi_headlines(symbol)"

content = content.replace(old, new)

with open('/root/aria_nlp_service.py', 'w') as f:
    f.write(content)

print("Done")
EOF

grep -n "NewsAPI\|fetch_newsapi" /root/aria_nlp_service.py | head -10
pkill -f aria_nlp_service && sleep 2 && nohup python3 /root/aria_nlp_service.py > /root/nlp_service.log 2>&1 & && sleep 30 && tail -15 /root/nlp_service.log
pkill -f aria_nlp_service
sleep 2
nohup python3 /root/aria_nlp_service.py > /root/nlp_service.log 2>&1 &
sleep 30 && tail -15 /root/nlp_service.log
systemctl restart aria_nlp && sleep 5 && systemctl status aria_nlp --no-pager | grep Active
cd /root && git add aria_nlp_service.py && git commit -m "feat: Cap 1 complete - NewsAPI integrated, FOMC hawkish detection live" && git push origin master
