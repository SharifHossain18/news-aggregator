import urllib.request
import urllib.parse
import re
import datetime
import ssl
import sys
import os
import io
import json
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.utils import parsedate_to_datetime

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

def fetch_url(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENTS[0]})
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=15, context=ctx) as response:
            return response.read()
    except Exception as e:
        return None

def extract_date(html_str):
    soup = BeautifulSoup(html_str, 'html.parser')
    bd_tz = datetime.timezone(datetime.timedelta(hours=6))

    date_patterns = [
        (re.compile(r'"datePublished"\s*:\s*"([^"]+)"'), None),
        (re.compile(r'"published_time"\s*:\s*"([^"]+)"'), None),
        (re.compile(r'"article:published_time"\s+content="([^"]+)"'), None),
        (re.compile(r'content="([^"]+)"\s+itemprop="datePublished"'), None),
        (re.compile(r'itemprop="datePublished"\s+content="([^"]+)"'), None),
        (re.compile(r'datetime="([^"]+)"', re.IGNORECASE), None),
    ]

    for pat, _ in date_patterns:
        m = pat.search(html_str)
        if m:
            try:
                dt = datetime.datetime.fromisoformat(m.group(1).replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=bd_tz)
                dt_bd = dt.astimezone(bd_tz)
                return dt_bd
            except Exception:
                pass

    time_tags = soup.find_all('time')
    for tag in time_tags:
        dt_attr = tag.get('datetime') or tag.get('title') or tag.get('data-timestamp')
        if dt_attr:
            try:
                dt = datetime.datetime.fromisoformat(dt_attr.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=bd_tz)
                dt_bd = dt.astimezone(bd_tz)
                return dt_bd
            except Exception:
                pass

    date_el = soup.find(class_=re.compile(r'publish|date|time|updated|created', re.IGNORECASE))
    if date_el:
        text = date_el.get_text(strip=True)
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%d %B %Y', '%B %d, %Y',
                     '%d %b %Y', '%b %d, %Y', '%Y-%m-%dT%H:%M:%S%z']:
            try:
                dt = datetime.datetime.strptime(text, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=bd_tz)
                return dt.astimezone(bd_tz)
            except Exception:
                pass

    meta_date = soup.find('meta', attrs={'name': re.compile(r'date|publish', re.IGNORECASE)})
    if meta_date:
        content = meta_date.get('content', '')
        try:
            dt = datetime.datetime.fromisoformat(content.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=bd_tz)
            return dt.astimezone(bd_tz)
        except Exception:
            pass

    return None

articles = [
    {"title": "Coal overtakes gas in power generation", "source": "Daily Star", "link": "https://www.thedailystar.net/news/environment/natural-resources/energy/news/coal-overtakes-gas-power-generation-4161546"},
    {"title": "ADB-backed LNG project leaves Bangladesh with $1.14bn stranded asset", "source": "Just Energy News", "link": "https://justenergynews24.com/adb-backed-lng-project-leaves-bangladesh-with-1-14bn-stranded-asset/"},
    {"title": "'Overcapacity in power, shortage of gas: A system built on wrong priorities'", "source": "Just Energy News", "link": "https://justenergynews24.com/we-built-power-not-energy-prof-ijaz-hossain-warns-of-a-gas-crisis-in-bangladesh/"},
    {"title": "ভূপৃষ্ঠের ছয় কিলোমিটার গভীরে গ্যাস অনুসন্ধান শুরু হচ্ছে", "source": "Daily Amardesh", "link": "https://www.dailyamardesh.com/amar-desh-special/special-report/amdy9iehyfype"},
    {"title": "রাত ৯টা পর্যন্ত গ্যাসের চাপ কম থাকবে রাজধানীর যেসব এলাকায়", "source": "Alokito Bangladesh", "link": "https://www.alokitobangladesh.com/capital/330345/"},
    {"title": "কয়লা খনি দুর্নীতি মামলা থেকে অব্যাহতি পেলেন হোসাফের মোয়াজ্জেম", "source": "Daily Sangram", "link": "https://dailysangram.com/bangladesh/court/4Ls2CzeVSQXT/"},
]

bd_tz = datetime.timezone(datetime.timedelta(hours=6))
now_bd = datetime.datetime.now(bd_tz)

print(f"\n{'='*70}")
print(f"  Bangladesh Energy/Mining News — Last 24 Hours")
print(f"  Current BD time: {now_bd.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*70}\n")

results = []
for art in articles:
    print(f"  Fetching: {art['source']} ...")
    data = fetch_url(art['link'])
    pub_time = None
    if data:
        pub_time = extract_date(data.decode('utf-8', errors='ignore'))
    results.append({**art, "time": pub_time})

results_sorted = sorted(results, key=lambda x: x.get('time') or datetime.datetime.max.replace(tzinfo=bd_tz), reverse=True)

for i, art in enumerate(results_sorted, 1):
    time_str = art['time'].strftime('%Y-%m-%d %H:%M:%S BD') if art['time'] else "Time not available"
    print(f"  {i}. [{time_str}]")
    print(f"     {art['title']}")
    print(f"     📌 {art['source']}")
    print(f"     🔗 {art['link']}")
    print()
