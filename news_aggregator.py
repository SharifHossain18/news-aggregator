import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import datetime
import ssl
import re
import html
import time
from email.utils import parsedate_to_datetime
import sys
import io
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging.handlers import RotatingFileHandler
import logging

# --- SETUP ---
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- CREDENTIALS ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("ERROR: Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env file")
    print("Create .env with:\nTELEGRAM_BOT_TOKEN=your_token\nTELEGRAM_CHAT_ID=your_chat_id")
    sys.exit(1)

# --- FILES ---
SENT_LOG_FILE = "sent_articles.json"
STATS_FILE = "source_stats.json"

# --- LOGGING WITH ROTATION ---
logger = logging.getLogger("news_aggregator")
logger.setLevel(logging.INFO)
file_handler = RotatingFileHandler("news_aggregator.log", maxBytes=500000, backupCount=3, encoding="utf-8")
file_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logger.addHandler(file_handler)
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(console_handler)

def log(msg):
    logger.info(msg)
    print(msg)

# --- SOURCES ---
SOURCES = [
    {
        "name": "Prothom Alo", 
        "urls": [
            "https://www.prothomalo.com/", 
            "https://www.prothomalo.com/business", 
            "https://www.prothomalo.com/bangladesh"
        ], 
        "type": "html"
    },
    {
        "name": "Daily Star", 
        "urls": [
            "https://www.thedailystar.net/", 
            "https://www.thedailystar.net/business", 
            "https://www.thedailystar.net/news/bangladesh"
        ], 
        "type": "html"
    },
    {
        "name": "Dhaka Tribune", 
        "urls": [
            "https://www.dhakatribune.com/", 
            "https://www.dhakatribune.com/business", 
            "https://www.dhakatribune.com/bangladesh"
        ], 
        "type": "html"
    },
    {
        "name": "TBS News", 
        "urls": [
            "https://tbsnews.net/", 
            "https://tbsnews.net/economy", 
            "https://tbsnews.net/bangladesh"
        ], 
        "type": "html"
    },
    {
        "name": "Kaler Kantho", 
        "urls": [
            "https://www.kalerkantho.com/", 
            "https://www.kalerkantho.com/online/business", 
            "https://www.kalerkantho.com/online/national"
        ], 
        "type": "html"
    },
    {"name": "Samakal", "url": "https://samakal.com/", "type": "html"},
    {"name": "Desh Rupantor", "url": "https://www.deshrupantor.com/", "type": "html"},
    {"name": "Jugantor", "url": "https://www.jugantor.com/", "type": "html"},
    {"name": "Shomoyer Alo", "url": "https://www.shomoyeralo.com/", "type": "html"},
    {"name": "Just Energy News", "url": "https://justenergynews24.com/", "type": "html"},
    {"name": "Bangla Tribune", "url": "https://www.banglatribune.com/", "type": "html"},
    {"name": "Jago News", "url": "https://www.jagonews24.com/", "type": "html"},
    {"name": "Ittefaq", "url": "https://www.ittefaq.com.bd/", "type": "html"},
    {"name": "Daily Amardesh", "url": "https://www.dailyamardesh.com/", "type": "html"},
    {"name": "Amader Shomoy", "url": "https://www.amadershomoy.com/", "type": "html"},
    {"name": "Alokito Bangladesh", "url": "https://www.alokitobangladesh.com/", "type": "html"},
    {"name": "Daily Sangram", "url": "https://dailysangram.com/", "type": "html"},
    {"name": "Jai Jai Din", "url": "https://www.jaijaidin.news/", "type": "html"},
    {"name": "Sangbad", "url": "https://sangbad.net/", "type": "html"},
    {"name": "Naya Diganta", "url": "https://www.dailynayadiganta.com/", "type": "html"},
    {"name": "Ajker Patrika", "url": "https://www.ajkerpatrika.com/", "type": "html"},
    {"name": "Bonik Barta", "url": "https://www.bonikbarta.com/", "type": "html"},
    {"name": "Kalbela", "url": "https://www.kalbela.com/", "type": "html"},
    {"name": "Protidiner Bangladesh", "url": "https://protidinerbangladesh.com/", "type": "html"},
    {"name": "Rupali Bangladesh", "url": "https://www.rupalibangladesh.com/", "type": "html"},
    {"name": "Protidiner Sangbad", "url": "https://www.protidinersangbad.com/", "type": "html"},
    {"name": "Dinkal", "url": "https://www.dinkaldigital.com/", "type": "html"},
    {"name": "Dainik Bangla", "url": "https://www.dainikbangla.com.bd/", "type": "html"},
    {"name": "Manobkantha", "url": "https://manobkantha.com.bd/", "type": "html"},
    {"name": "Daily Inqilab", "url": "https://dailyinqilab.com/", "type": "html"},
    {"name": "Manab Zamin", "url": "https://www.mzamin.com/", "type": "html"},
    {"name": "BD Pratidin", "url": "https://www.bd-pratidin.com/", "type": "html"},
    {"name": "Bangladesh Today", "url": "https://thebangladeshtoday.com/", "type": "html"},
    {"name": "New Nation", "url": "https://dailynewnation.com/", "type": "html"},
    {"name": "New Age", "url": "https://www.newagebd.net/", "type": "html"},
    {"name": "Observer", "url": "https://observerbd.com/", "type": "html"},
    {"name": "Daily Post", "url": "https://bangladeshpost.net/", "type": "html"},
    {"name": "Daily Sun", "url": "https://www.daily-sun.com/", "type": "html"},
    {"name": "Financial Express", "url": "https://thefinancialexpress.com.bd/", "type": "html"}
]

# --- PRE-COMPILED KEYWORD PATTERNS ---
PRIMARY_PATTERNS = []
for kw in ["gas", "lng", "petrobangla", "bapex", "bgfcl", "sgfl", "gtcl", "titas", "bakhrabad",
           "jalalabad", "pashchimanchal", "rpgcl", "bcmcl", "mgmcl",
           "maddhapara", "barapukuria"]:
    PRIMARY_PATTERNS.append(re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE))

PRIMARY_BENGALI = ["গ্যাস", "এলএনজি", "পেট্রোবাংলা", "কয়লা খনি", "পাথর খনি",
                    "তিতাস", "বাপেক্স", "মধ্যপাড়া", "বড়পুকুরিয়া", "জিটিসিএল",
                    "আরপিজিসিএল", "জালালাবাদ", "গ্যাসহীন", "গ্যাস সংকট"]

SECONDARY_PATTERNS = [re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
                       for kw in ["coal", "rock", "karnaphuli", "sundarban"]]
SECONDARY_BENGALI = ["কয়লা", "পাথর", "কর্ণফুলী", "সুন্দরবন"]

ASSOC_PATTERNS = [re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
                   for kw in ["petrobangla", "barapukuria", "maddhapara", "bcmcl", "mgmcl"]]
ASSOC_BENGALI = ["বড়পুকুরিয়া", "মধ্যপাড়া", "পেট্রোবাংলা"]

EXCLUDE_PATTERNS = [re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
                       for kw in ["lpg", "cylinder", "russia", "ukraine", "israel", "gaza",
                                  "palestine", "usa", "europe", "india", "pakistan", "china",
                                  "biden", "putin", "hormuz", "global", "world",
                                  "international", "thermal power plant",
                                  "electricity", "Reset Button", "middle east",
                                  "london", "new york", "washington", "beijing", "tokyo",
                                  "delhi", "dhallywood", "cinema", "movie", "film",
                                  "cricket", "football", "sports", "entertainment",
                                  "celebrity", "actor", "actress", "singer", "song",
                                  "weather", "আবহাওয়া", "খেলা", "ক্রিকেট",
                                  "সংগীত", "চলচ্চিত্র", "নাটক", "গান",
                                  "afghanistan", "syria", "yemen", "libya", "sudan",
                                  "iran", "iraq", "saudi", "dubai", "qatar", "kuwait",
                                  "japan", "korea", "australia", "canada", "brazil",
                                  "germany", "france", "britain", "nato", "eu ",
                                  "united nations", "general assembly", "security council",
                                  "trade war", "tariff", "sanctions", "summit", "g20",
                                  "opec", "wto", "imf", "world bank", "asian development",
                                  "nuclear deal", "peace deal", "ceasefire", "conflict",
                                  "war ", "military aid", "arms deal", "embassy",
                                  "foreign minister", "prime minister of", "president of",
                                  "ambassador", "diplomat", "delegation", "bilateral",
                                  "multilateral", "foreign policy", "geopolitical",
                                  "fifa", "world cup", "olympics", "tennis", "golf",
                                  "stock market", "wall street", "nasdaq", "dow jones",
                                  "inflation", "recession", "fed rate", "interest rate",
                                  "covid", "pandemic", "vaccine", "who ", "coronavirus",
                                  "venezuela", "myanmar", "thailand", "malaysia", "singapore",
                                  "vietnam", "philippines", "indonesia", "srilanka", "sri lanka",
                                  "nepal", "bhutan", "maldives", "turkey", "africa",
                                  "egypt", "nigeria", "kenya", "south africa", "mexico",
                                  "argentina", "chile", "peru", "colombia", "sweden",
                                  "norway", "denmark", "finland", "italy", "spain",
                                  "portugal", "netherlands", "switzerland", "austria",
                                  "poland", "czech", "hungary", "romania", "bulgaria",
                                  "serbia", "croatia", "algeria", "morocco", "tunisia",
                                  "turkmenistan", "kazakhstan", "uzbekistan", "azerbaijan"]]
EXCLUDE_BENGALI = ["এলপিজি", "সিলিন্ডার", "পুতিন", "বাইডেন", "ইউক্রেন", "রাশিয়া",
                     "ভারত", "ইসরায়েল", "আশা ভোঁসলে", "সঙ্গীত", "চলচ্চিত্র",
                     "রিসেট বাটন", "হরমুজ", "পারস্য উপসাগর", "বিশ্ব",
                     "বিদ্যুৎ কেন্দ্র", "তাপ বিদ্যুৎ কেন্দ্র", "বিদ্যুৎ",
                     "আফগানিস্তান", "সিরিয়া", "ইয়েমেন", "লিবিয়া", "সুদান",
                     "ইরান", "ইরাক", "সৌদি", "দুবাই", "কাতার", "কুয়েত",
                     "জাপান", "কোরিয়া", "অস্ট্রেলিয়া", "কানাডা", "ব্রাজিল",
                     "জার্মানি", "ফ্রান্স", "ব্রিটেন", "ন্যাটো", "ইইউ",
                     "জাতিসংঘ", "সাধারণ পরিষদ", "নিরাপত্তা পরিষদ",
                     "বাণিজ্য যুদ্ধ", "শুল্ক", "নিষেধাজ্ঞা", "শীর্ষ সম্মেলন",
                     "ওপেক", "ডব্লিউটিও", "আইএমএফ", "বিশ্বব্যাংক",
                     "পারমাণবিক চুক্তি", "শান্তি চুক্তি", "যুদ্ধবিরতি", "সংঘাত",
                     "যুদ্ধ", "সামরিক সহায়তা", "অস্ত্র চুক্তি", "দূতাবাস",
                     "পররাষ্ট্রমন্ত্রী", "রাষ্ট্রদূত", "প্রতিনিধি দল",
                     "দ্বিপাক্ষিক", "বহুপাক্ষিক", "পররাষ্ট্র নীতি",
                     "ফিফা", "বিশ্বকাপ", "অলিম্পিক", "টেনিস", "গলফ",
                     "শেয়ার বাজার", "ওয়াল স্ট্রিট", "মুদ্রাস্ফীতি",
                     "কোভিড", "মহামারি", "টিকা", "হু"]

# --- HTML PARSER (replaces regex) ---
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    log("WARNING: beautifulsoup4 not installed. Install with: pip install beautifulsoup4")

# --- SOURCE STATS ---
SOURCE_STATS = {}

def load_stats():
    global SOURCE_STATS
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                SOURCE_STATS = json.load(f)
        except Exception:
            SOURCE_STATS = {}

def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(SOURCE_STATS, f, ensure_ascii=False, indent=2)

def track_source(name, success, count=0):
    if name not in SOURCE_STATS:
        SOURCE_STATS[name] = {"success": 0, "fail": 0, "articles": 0, "last_check": ""}
    stats = SOURCE_STATS[name]
    if success:
        stats["success"] += 1
        stats["articles"] += count
        stats["last_fail_streak"] = 0
    else:
        stats["fail"] += 1
        stats["last_fail_streak"] = stats.get("last_fail_streak", 0) + 1
    stats["last_check"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# --- STORAGE ---
def load_sent_articles():
    if os.path.exists(SENT_LOG_FILE):
        try:
            with open(SENT_LOG_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_sent_articles(sent_set):
    list_to_save = list(sent_set)[-1000:]
    with open(SENT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(list_to_save, f)

# --- TELEGRAM ---
def send_telegram(text, parse_mode="HTML"):
    text = "".join(ch for ch in text if ch.isprintable() or ch in "\n\r\t")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": True}
    if parse_mode:
        data["parse_mode"] = parse_mode
    payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, payload, headers={'Content-Type': 'application/json'})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        resp = urllib.request.urlopen(req, timeout=15, context=ctx)
        result = json.loads(resp.read())
        if not result.get("ok"):
            log(f"Telegram error: {result.get('description', 'unknown')}")
        return result.get("ok", False)
    except Exception as e:
        log(f"Telegram send failed: {e}")
        return False

def send_telegram_retry(text, retries=3):
    for i in range(retries):
        if send_telegram(text):
            return True
        time.sleep(2)
    return False

# --- FETCH ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

try:
    import cloudscraper
    # Initialize a global cloudscraper session to bypass Cloudflare
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )
except ImportError:
    scraper = None
    log("WARNING: cloudscraper not installed. Some sites may return 403. Run: pip install cloudscraper")

def fetch_url(url, retries=3):
    from urllib.parse import quote, urlparse, urlunparse
    parsed = urlparse(url)
    safe_path = quote(parsed.path, safe='/:')
    encoded_url = urlunparse((parsed.scheme, parsed.netloc, safe_path, parsed.params, parsed.query, parsed.fragment))
    
    for i in range(retries + 1):
        try:
            if scraper:
                response = scraper.get(encoded_url, timeout=15)
                if response.status_code == 200:
                    return response.content
                else:
                    log(f"HTTP {response.status_code} for {url}")
                    return None
            else:
                # Fallback to urllib if cloudscraper isn't installed
                headers = {
                    "User-Agent": USER_AGENTS[i % len(USER_AGENTS)],
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9,bn;q=0.8",
                    "Upgrade-Insecure-Requests": "1"
                }
                req = urllib.request.Request(encoded_url, headers=headers)
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, timeout=15, context=ctx) as response:
                    return response.read()
        except Exception as e:
            if hasattr(e, 'code') and e.code == 403:
                log(f"HTTP 403 for {url}")
                return None
            if i == retries:
                log(f"Fetch error for {url}: {e}")
            else:
                time.sleep(1)
    return None

# --- KEYWORD MATCHING ---
def is_keyword_match(text):
    text_lower = text.lower()
    for pat in PRIMARY_PATTERNS:
        if pat.search(text_lower):
            return True
    for kw in PRIMARY_BENGALI:
        if kw in text_lower:
            return True

    has_secondary = False
    for pat in SECONDARY_PATTERNS:
        if pat.search(text_lower):
            has_secondary = True
            break
    if not has_secondary:
        for kw in SECONDARY_BENGALI:
            if kw in text_lower:
                has_secondary = True
                break
    if has_secondary:
        for pat in ASSOC_PATTERNS:
            if pat.search(text_lower):
                return True
        for kw in ASSOC_BENGALI:
            if kw in text_lower:
                return True
    return False

def is_excluded(text):
    text_lower = text.lower()
    for pat in EXCLUDE_PATTERNS:
        if pat.search(text_lower):
            return True
    for kw in EXCLUDE_BENGALI:
        if kw in text_lower:
            return True

    # Smart check: foreign country + deal/partnership words
    foreign_countries = [
        "venezuela", "myanmar", "thailand", "malaysia", "singapore",
        "vietnam", "philippines", "indonesia", "nepal", "bhutan",
        "maldives", "turkey", "turkiye", "algeria", "morocco", "tunisia",
        "turkmenistan", "kazakhstan", "uzbekistan", "azerbaijan",
        "norway", "denmark", "finland", "italy", "spain",
        "portugal", "netherlands", "switzerland", "austria",
        "poland", "czech", "hungary", "romania", "bulgaria",
        "serbia", "croatia", "mexico", "argentina", "chile",
        "peru", "colombia", "kenya", "nigeria", "egypt", "russia"
    ]
    deal_words = [
        "signs deal", "signs agreement", "signs pact", "signs mou",
        "signed deal", "signed agreement", "signed pact", "signed mou",
        "inked deal", "inked agreement", "inked pact",
        "deal with", "agreement with", "pact with",
        "partnership with", "joint venture", "collaboration with",
        "import from", "export to", "supply from", "supply to"
    ]
    has_foreign = any(country in text_lower for country in foreign_countries)
    has_deal = any(dw in text_lower for dw in deal_words)
    if has_foreign and has_deal:
        return True

    # Also check for "with us" / "with bangladesh" + foreign country
    if has_foreign and re.search(r'\b(with us|with bangladesh)\b', text_lower):
        return True

    return False

# --- PARSING ---
def parse_rss(data, source_name, start_time, end_time):
    articles = []
    try:
        xml_str = data.decode('utf-8', errors='ignore').strip()
        root = ET.fromstring(xml_str)
        ns = {'atom': 'http://www.w3.org/2005/Atom', 'dc': 'http://purl.org/dc/elements/1.1/'}
        items = list(root.iter('item')) or list(root.iter('entry')) or list(root.iter('{http://www.w3.org/2005/Atom}entry'))
        for item in items:
            title_node = item.find('title')
            if title_node is None:
                title_node = item.find('atom:title', ns)
            link_node = item.find('link')
            if link_node is None:
                link_node = item.find('atom:link', ns)
            date_node = item.find('pubDate')
            if date_node is None:
                date_node = item.find('atom:published', ns)
            if date_node is None:
                date_node = item.find('dc:date', ns)
            if title_node is None:
                continue
            title = title_node.text or ""
            link = (link_node.text or link_node.get('href') or "") if link_node is not None else ""
            if not is_keyword_match(title) or is_excluded(title):
                continue
            is_in_timeframe = True
            if date_node is not None and date_node.text:
                try:
                    pub_date = parsedate_to_datetime(date_node.text)
                    if pub_date.tzinfo is None:
                        pub_date = pub_date.replace(tzinfo=datetime.timezone.utc)
                    pub_date_bd = pub_date.astimezone(datetime.timezone(datetime.timedelta(hours=6)))
                    if not (start_time <= pub_date_bd <= end_time):
                        is_in_timeframe = False
                except Exception:
                    pass
            if is_in_timeframe:
                articles.append({"title": title.strip(), "link": link.strip(), "source": source_name})
    except Exception as e:
        log(f"RSS parse error ({source_name}): {e}")
    return articles

def parse_html(data, source_name, base_url):
    articles = []
    seen_links = set()
    try:
        if HAS_BS4:
            soup = BeautifulSoup(data, 'html.parser')
            for tag in soup.find_all('a', href=True):
                link = tag['href']
                if link in seen_links:
                    continue
                text = tag.get_text(strip=True)
                if not text or len(text) < 20:
                    continue
                parent_classes = ' '.join(tag.parent.get('class', [])) if tag.parent else ''
                parent_tag = tag.parent.name if tag.parent else ''
                if parent_tag in ('footer', 'nav', 'header', 'aside'):
                    continue
                skip_zones = ['footer', 'sidebar', 'widget', 'nav', 'menu',
                              'header-bar', 'breaking-news-ticker', 'social',
                              'advertisement', 'ad-', 'comment', 'tag-cloud',
                              'related-articles', 'most-read', 'popular']
                if any(z in parent_classes.lower() for z in skip_zones):
                    continue
                if not is_keyword_match(text) or is_excluded(text):
                    continue
                if text.count(' ') < 3:
                    continue
                if '://' in text or text.startswith('/'):
                    continue
                full_link = urllib.parse.urljoin(base_url, link) if not link.startswith('http') else link
                skip_url_zones = ['/tag/', '/category/', '/archive/', '/search/', '/author/',
                                  '/login', '/register', '/about', '/contact', '/privacy',
                                  '/terms', '/sitemap', '/feed', '/rss', '/atom',
                                  '/wp-admin', '/wp-content', '/wp-includes', '/cdn-cgi',
                                  'petrobangla.org', 'facebook.com', 'twitter.com', 'youtube.com',
                                  'instagram.com', 'wa.me', 't.me']
                if any(z in full_link.lower() for z in skip_url_zones):
                    continue
                seen_links.add(link)
                articles.append({"title": text, "link": full_link, "source": source_name})
        else:
            html_str = data.decode('utf-8', errors='ignore')
            link_pattern = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.DOTALL)
            for match in link_pattern.finditer(html_str):
                link, raw_text = match.groups()
                text = html.unescape(re.sub(r'<[^>]+>', '', raw_text)).strip()
                if not text or len(text) < 20:
                    continue
                if text.count(' ') < 3:
                    continue
                if not is_keyword_match(text) or is_excluded(text):
                    continue
                full_link = urllib.parse.urljoin(base_url, link) if not link.startswith('http') else link
                articles.append({"title": text, "link": full_link, "source": source_name})
    except Exception as e:
        log(f"HTML parse error ({source_name}): {e}")
    return articles

def parse_bengali_date(text):
    """Parse Bengali date strings like '২৯ এপ্রিল ২০২৬' or '০৩ মে ২০২৬'."""
    bd_tz = datetime.timezone(datetime.timedelta(hours=6))
    bengali_months = {
        'জানুয়ারি': 1, 'ফেব্রুয়ারি': 2, 'মার্চ': 3, 'এপ্রিল': 4, 'মে': 5,
        'জুন': 6, 'জুলাই': 7, 'আগস্ট': 8, 'সেপ্টেম্বর': 9, 'অক্টোবর': 10,
        'নভেম্বর': 11, 'ডিসেম্বর': 12
    }
    bengali_digits = {'০': '0', '১': '1', '২': '2', '৩': '3', '৪': '4', '৫': '5', '৬': '6', '৭': '7', '৮': '8', '৯': '9'}

    def to_eng(s):
        return ''.join(bengali_digits.get(c, c) for c in s)

    for month_bn, month_num in bengali_months.items():
        pat = re.compile(r'(\d{1,2}|[০-৯]{1,2})\s*' + re.escape(month_bn) + r'\s+(\d{4}|[০-৯]{4})')
        m = pat.search(text)
        if m:
            try:
                day = int(to_eng(m.group(1)))
                year = int(to_eng(m.group(2)))
                return datetime.datetime(year, month_num, day, tzinfo=bd_tz)
            except Exception:
                pass
    return None

def parse_html_date(html_str):
    """Extract publication date from article HTML. Returns earliest reliable date found."""
    bd_tz = datetime.timezone(datetime.timedelta(hours=6))

    # 1. JSON-LD structured data (most reliable)
    for pat_key in [r'"datePublished"\s*:\s*"([^"]+)"', r'"dateCreated"\s*:\s*"([^"]+)"']:
        m = re.search(pat_key, html_str)
        if m:
            try:
                dt = datetime.datetime.fromisoformat(m.group(1).replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=bd_tz)
                return dt.astimezone(bd_tz)
            except Exception:
                pass

    # 2. Meta tags
    soup = BeautifulSoup(html_str, 'html.parser')
    for meta in soup.find_all('meta'):
        prop = meta.get('property', '') or meta.get('name', '')
        if prop in ('article:published_time', 'published_time', 'date', 'publish-date'):
            content = meta.get('content', '')
            if content:
                try:
                    dt = datetime.datetime.fromisoformat(content.replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=bd_tz)
                    return dt.astimezone(bd_tz)
                except Exception:
                    pass

    # 3. Time tags with datetime attribute (only first/relevant one)
    for tag in soup.find_all('time'):
        dt_attr = tag.get('datetime')
        if dt_attr:
            try:
                dt = datetime.datetime.fromisoformat(dt_attr.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=bd_tz)
                dt_bd = dt.astimezone(bd_tz)
                # Only return if it looks like a real article date (not sidebar dates)
                if dt_bd.year >= 2024:
                    return dt_bd
            except Exception:
                pass

    # 4. Bengali date text in article body
    body_text = soup.get_text()
    bengali_date = parse_bengali_date(body_text)
    if bengali_date:
        return bengali_date

    # 5. English date patterns in body text
    for fmt in ['%d %B %Y', '%B %d, %Y', '%d %b %Y', '%b %d, %Y', '%Y-%m-%d', '%d/%m/%Y']:
        for pat in [
            re.compile(r'(\d{1,2}\s+' + r'(?:January|February|March|April|May|June|July|August|September|October|November|December)' + r'\s+\d{4})'),
            re.compile(r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})'),
        ]:
            m = pat.search(body_text)
            if m:
                try:
                    dt = datetime.datetime.strptime(m.group(1), fmt)
                    dt = dt.replace(tzinfo=bd_tz)
                    return dt
                except Exception:
                    pass

    return None

def extract_article_body(html_str):
    """Extract the main article text from the page."""
    soup = BeautifulSoup(html_str, 'html.parser')

    # Try common article content selectors
    for selector in [
        {'class_': re.compile(r'article-body|article-content|story-content|post-content|entry-content|article-text|full-text', re.IGNORECASE)},
        {'class_': re.compile(r'^content$|^article$|^story$|^post$', re.IGNORECASE)},
        {'id': re.compile(r'article-body|article-content|story-content|post-content|entry-content', re.IGNORECASE)},
        {'itemprop': 'articleBody'},
    ]:
        el = soup.find(**selector)
        if el:
            return el.get_text(separator=' ', strip=True)

    # Fallback: find the largest paragraph container
    main = soup.find('main') or soup.find('article') or soup.find('div', class_=re.compile(r'content|article|story|post', re.IGNORECASE))
    if main:
        # Remove scripts, styles, ads, sidebars, comments
        for tag in main.find_all(['script', 'style', 'aside', 'nav', 'footer', 'header', 'form']):
            tag.decompose()
        return main.get_text(separator=' ', strip=True)

    return ""

def verify_article(article, start_time, end_time):
    """Visit article page and verify: 1) date, 2) relevance, 3) not already sent."""
    try:
        url = article['link']
        if not url.startswith('http'):
            url = 'https://' + url
        data = fetch_url(url)
        if data is None:
            log(f"  ⏭ Skipped (unreachable): {article['title'][:60]}...")
            return None
        soup = BeautifulSoup(data, 'html.parser')
        html_str = str(soup)

        # Check date
        pub_date = parse_html_date(html_str)
        if pub_date is not None:
            if pub_date < start_time or pub_date > end_time:
                log(f"  ⏭ Old ({pub_date.strftime('%Y-%m-%d %H:%M')}): {article['title'][:60]}...")
                return None
        else:
            # No structured date found — check body text for Bengali date
            soup_fallback = BeautifulSoup(html_str, 'html.parser')
            body_text = soup_fallback.get_text()
            bd_tz = datetime.timezone(datetime.timedelta(hours=6))
            body_date = parse_bengali_date(body_text)
            if body_date:
                if body_date < start_time:
                    log(f"  ⏭ Old (Bengali date {body_date.strftime('%Y-%m-%d')}): {article['title'][:60]}...")
                    return None
            # If still no date found, check for date-like patterns in URL or page
            url_date = re.search(r'(\d{4})/(\d{2})/(\d{2})', article['link'])
            if url_date:
                try:
                    url_dt = datetime.datetime(int(url_date.group(1)), int(url_date.group(2)), int(url_date.group(3)), tzinfo=bd_tz)
                    if url_dt < start_time:
                        log(f"  ⏭ Old (URL date {url_dt.strftime('%Y-%m-%d')}): {article['title'][:60]}...")
                        return None
                except: pass

        # Extract article body and check relevance
        body = extract_article_body(html_str)
        full_text = article['title'] + " " + body

        if len(body) > 50:
            # Only check keyword relevance on body (not exclusions, those apply to title only)
            if not is_keyword_match(full_text):
                log(f"  ⏭ Irrelevant (no keyword in body): {article['title'][:60]}...")
                return None

            # Extra smart check for foreign deals using full body
            foreign_countries = [
                "venezuela", "myanmar", "thailand", "malaysia", "singapore",
                "vietnam", "philippines", "indonesia", "nepal", "bhutan",
                "maldives", "turkey", "turkiye", "algeria", "morocco", "tunisia",
                "turkmenistan", "kazakhstan", "uzbekistan", "azerbaijan",
                "norway", "denmark", "finland", "italy", "spain",
                "portugal", "netherlands", "switzerland", "austria",
                "poland", "czech", "hungary", "romania", "bulgaria",
                "serbia", "croatia", "mexico", "argentina", "chile",
                "peru", "colombia", "kenya", "nigeria", "egypt", "russia"
            ]
            deal_words = [
                "signs deal", "signs agreement", "signs pact", "signs mou",
                "signed deal", "signed agreement", "signed pact", "signed mou",
                "inked deal", "inked agreement", "inked pact",
                "deal with", "agreement with", "pact with",
                "partnership with", "joint venture", "collaboration with",
                "import from", "export to", "supply from", "supply to"
            ]
            body_lower = body.lower()
            has_foreign = any(country in body_lower for country in foreign_countries)
            has_deal = any(dw in body_lower for dw in deal_words)
            if has_foreign and has_deal:
                log(f"  ⏭ Foreign deal: {article['title'][:60]}...")
                return None
            if has_foreign and re.search(r'\b(with us|with bangladesh)\b', body_lower):
                log(f"  ⏭ Foreign deal (with BD): {article['title'][:60]}...")
                return None

        date_str = pub_date.strftime('%Y-%m-%d %H:%M') if pub_date else "no date"
        log(f"  ✅ {date_str} — {article['title'][:80]}...")
        return article
    except Exception as e:
        log(f"  ⏭ Error verifying: {article['title'][:60]}... ({e})")
        return None

def scrape_source(source, start_time, end_time):
    name = source['name']
    urls_to_scan = source.get('urls', [source.get('url')] if source.get('url') else [])
    all_articles = []
    any_success = False

    log(f"  Scanning {name} ({len(urls_to_scan)} pages)...")
    
    for url in urls_to_scan:
        if not url: continue
        try:
            data = fetch_url(url)
            if data is None:
                continue
            
            any_success = True
            if source.get('type', 'html') == 'rss':
                articles = parse_rss(data, name, start_time, end_time)
            else:
                articles = parse_html(data, name, url)
                articles = [a for a in articles if a is not None]
                # Visit each article page to verify date + relevance
                if articles:
                    verified = []
                    for art in articles:
                        result = verify_article(art, start_time, end_time)
                        if result is not None:
                            verified.append(result)
                        time.sleep(0.3)  # polite delay between requests
                    articles = verified
            
            all_articles.extend(articles)
        except Exception as e:
            log(f"  Error ({name} - {url}): {e}")

    if any_success:
        track_source(name, True, len(all_articles))
    else:
        track_source(name, False)
        
    return all_articles

# --- MAIN SCRAPE ---
def scrape_all():
    log("=" * 50)
    log("News Aggregator Started")
    log("=" * 50)
    load_stats()
    start_time, end_time = get_target_timeframe()
    sent_articles = load_sent_articles()
    all_new = []

    log(f"Scanning {len(SOURCES)} sources (parallel)...")
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(scrape_source, src, start_time, end_time): src for src in SOURCES}
        for future in as_completed(futures):
            source = futures[future]
            try:
                articles = future.result()
                for art in articles:
                    if art['link'] not in sent_articles:
                        all_new.append(art)
                        sent_articles.add(art['link'])
            except Exception as e:
                log(f"  Unexpected error: {e}")

    save_stats()

    if not all_new:
        log("No new articles found.")
        return

    log(f"Found {len(all_new)} new articles to send.")
    save_sent_articles(sent_articles)

    source_counts = {}
    for art in all_new:
        source_counts[art['source']] = source_counts.get(art['source'], 0) + 1
    source_summary = " | ".join([f"{k}: {v}" for k, v in sorted(source_counts.items(), key=lambda x: -x[1])])
    log(f"Breakdown: {source_summary}")

    now_str = datetime.datetime.now().strftime("%H:%M")
    header = f"📰 <b>News Update — {now_str}</b>\n🔍 {len(all_new)} new article(s) found\n\n📊 <i>{source_summary}</i>"
    if send_telegram_retry(header):
        log("Header sent to Telegram")
    else:
        log("ERROR: Failed to send header")
    time.sleep(0.5)

    all_new.sort(key=lambda x: (x['source'], x['title']))

    chunks = []
    current_chunk = []
    current_len = 0
    for i, art in enumerate(all_new, 1):
        item = f"{i}. <a href='{html.escape(art['link'])}'>{html.escape(art['title'])}</a>\n   📌 {art['source']}\n\n"
        item_len = len(item)
        if current_len + item_len > 4000 and current_chunk:
            chunks.append("".join(current_chunk))
            current_chunk = []
            current_len = 0
        current_chunk.append(item)
        current_len += item_len
    if current_chunk:
        chunks.append("".join(current_chunk))

    ok_count = sum(1 for s in SOURCE_STATS.values() if s.get("success", 0) > 0)
    fail_count = len(SOURCES) - ok_count

    for j, chunk in enumerate(chunks):
        if send_telegram_retry(chunk):
            log(f"Chunk {j+1}/{len(chunks)} sent to Telegram")
        else:
            log(f"ERROR: Chunk {j+1}/{len(chunks)} FAILED")
        if j < len(chunks) - 1:
            time.sleep(0.5)

    log(f"Done! {ok_count} sources OK, {fail_count} had errors.")
    log("=" * 50)

# --- ADMIN COMMANDS ---
def handle_command(cmd):
    load_stats()
    if cmd == "stats":
        total_ok = sum(s.get("success", 0) for s in SOURCE_STATS.values())
        total_fail = sum(s.get("fail", 0) for s in SOURCE_STATS.values())
        total_articles = sum(s.get("articles", 0) for s in SOURCE_STATS.values())
        failing = [n for n, s in SOURCE_STATS.items() if s.get("last_fail_streak", 0) >= 3]
        msg = f"📊 <b>Source Statistics</b>\n\n"
        msg += f"Total scrapes: {total_ok} success, {total_fail} failed\n"
        msg += f"Total articles sent: {total_articles}\n"
        if failing:
            msg += f"\n⚠️ Failing sources ({len(failing)}):\n"
            for f in failing:
                streak = SOURCE_STATS[f].get("last_fail_streak", 0)
                msg += f"  • {f} ({streak} fails in a row)\n"
        send_telegram_retry(msg)
    elif cmd == "sources":
        msg = "📋 <b>All Sources</b>\n\n"
        for src in SOURCES:
            s = SOURCE_STATS.get(src['name'], {})
            status = "✅" if s.get("last_fail_streak", 0) < 3 else "❌"
            articles = s.get("articles", 0)
            last = s.get("last_check", "Never")
            msg += f"{status} <b>{src['name']}</b> — {articles} articles | {last}\n"
        send_telegram_retry(msg)
    elif cmd == "trigger":
        scrape_all()
    else:
        send_telegram_retry("Unknown command. Use: /stats, /sources, /trigger")

# --- HELPERS ---
def get_target_timeframe():
    bd_tz = datetime.timezone(datetime.timedelta(hours=6))
    now_bd = datetime.datetime.now(bd_tz)
    start_time = now_bd - datetime.timedelta(hours=24)
    return start_time, now_bd

# --- ENTRY ---
if __name__ == "__main__":
    args = sys.argv[1:]
    if args:
        cmd = args[0].lstrip("-/").lower()
        handle_command(cmd)
    else:
        scrape_all()
