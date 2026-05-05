import urllib.request
import urllib.parse
import re
import datetime
import ssl
import sys
import io
import json
from bs4 import BeautifulSoup

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def fetch_url(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=15, context=ctx) as response:
            return response.read()
    except Exception as e:
        return None

def extract_date_deep(url, html_str):
    bd_tz = datetime.timezone(datetime.timedelta(hours=6))
    results = []

    # 1. JSON-LD
    for m in re.finditer(r'"datePublished"\s*:\s*"([^"]+)"', html_str):
        try:
            dt = datetime.datetime.fromisoformat(m.group(1).replace('Z', '+00:00'))
            if dt.tzinfo is None: dt = dt.replace(tzinfo=bd_tz)
            results.append(("JSON-LD datePublished", dt.astimezone(bd_tz)))
        except: pass

    for m in re.finditer(r'"dateCreated"\s*:\s*"([^"]+)"', html_str):
        try:
            dt = datetime.datetime.fromisoformat(m.group(1).replace('Z', '+00:00'))
            if dt.tzinfo is None: dt = dt.replace(tzinfo=bd_tz)
            results.append(("JSON-LD dateCreated", dt.astimezone(bd_tz)))
        except: pass

    # 2. Meta tags
    soup = BeautifulSoup(html_str, 'html.parser')
    for meta in soup.find_all('meta'):
        for attr_name in ['article:published_time', 'published_time', 'date', 'publish-date', 'date_published', 'article:modified_time']:
            if meta.get('property') == attr_name or meta.get('name') == attr_name:
                content = meta.get('content', '')
                if content:
                    try:
                        dt = datetime.datetime.fromisoformat(content.replace('Z', '+00:00'))
                        if dt.tzinfo is None: dt = dt.replace(tzinfo=bd_tz)
                        results.append((f"meta {attr_name}", dt.astimezone(bd_tz)))
                    except: pass

    # 3. Time tags
    for tag in soup.find_all('time'):
        for attr in ['datetime', 'title', 'data-time', 'data-timestamp', 'data-published-at']:
            val = tag.get(attr)
            if val:
                try:
                    dt = datetime.datetime.fromisoformat(val.replace('Z', '+00:00'))
                    if dt.tzinfo is None: dt = dt.replace(tzinfo=bd_tz)
                    results.append((f"time[{attr}]", dt.astimezone(bd_tz)))
                except: pass

    # 4. Date in URL
    url_match = re.search(r'(\d{4})[/\-](\d{2})[/\-](\d{2})', url)
    if url_match:
        try:
            dt = datetime.datetime(int(url_match.group(1)), int(url_match.group(2)), int(url_match.group(3)), tzinfo=bd_tz)
            results.append(("URL date", dt))
        except: pass

    # 5. Bengali date text in article
    bengali_date_patterns = [
        re.compile(r'(\d{1,2}\s+(?:জানুয়ারি|ফেব্রুয়ারি|মার্চ|এপ্রিল|মে|জুন|জুলাই|আগস্ট|সেপ্টেম্বর|অক্টোবর|নভেম্বর|ডিসেম্বর)\s+\d{4})'),
        re.compile(r'(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})'),
        re.compile(r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})'),
        re.compile(r'(\d{1,2}\s+\w+\s+\d{4})'),
        re.compile(r'(\d{2}/\d{2}/\d{4})'),
        re.compile(r'(\d{4}-\d{2}-\d{2})'),
    ]
    body_text = soup.get_text()
    for pat in bengali_date_patterns:
        m = pat.search(body_text)
        if m:
            results.append((f"body text pattern", m.group(1)))

    return results

articles = [
    {"title": "Coal overtakes gas in power generation", "source": "Daily Star", "link": "https://www.thedailystar.net/news/environment/natural-resources/energy/news/coal-overtakes-gas-power-generation-4161546"},
    {"title": "ADB-backed LNG project", "source": "Just Energy News", "link": "https://justenergynews24.com/adb-backed-lng-project-leaves-bangladesh-with-1-14bn-stranded-asset/"},
    {"title": "Overcapacity in power, shortage of gas", "source": "Just Energy News", "link": "https://justenergynews24.com/we-built-power-not-energy-prof-ijaz-hossain-warns-of-a-gas-crisis-in-bangladesh/"},
    {"title": "Gas exploration 6km deep", "source": "Daily Amardesh", "link": "https://www.dailyamardesh.com/amar-desh-special/special-report/amdy9iehyfype"},
    {"title": "Gas pressure reduction", "source": "Alokito Bangladesh", "link": "https://www.alokitobangladesh.com/capital/330345/"},
    {"title": "Coal mine corruption case", "source": "Daily Sangram", "link": "https://dailysangram.com/bangladesh/court/4Ls2CzeVSQXT/"},
]

print(f"\n{'='*80}")
print(f"  Deep Date Investigation")
print(f"{'='*80}\n")

for art in articles:
    print(f"\n{'─'*80}")
    print(f"  📰 {art['title']}")
    print(f"  📌 {art['source']}")
    print(f"  🔗 {art['link']}")
    print(f"{'─'*80}")

    data = fetch_url(art['link'])
    if not data:
        print("  ❌ Could not fetch page")
        continue

    html_str = data.decode('utf-8', errors='ignore')
    results = extract_date_deep(art['link'], html_str)

    if results:
        for label, val in results:
            if isinstance(val, datetime.datetime):
                print(f"  ✅ {label:30s} → {val.strftime('%Y-%m-%d %H:%M:%S BD')}")
            else:
                print(f"  🔍 {label:30s} → {val}")
    else:
        print("  ⚠️  No date found on page")

    # Also show any date-like strings in the page
    date_in_page = re.findall(r'(?:প্রকাশিত|Updated|Published|Posted)\s*[:|]\s*(.+?)[<\n]', html_str, re.IGNORECASE)
    if date_in_page:
        for d in date_in_page[:3]:
            clean = re.sub(r'<[^>]+>', '', d).strip()
            print(f"  📝 In page text: {clean}")
