import urllib.request
import urllib.parse
import urllib.error
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
SELF_CHECK_MODE = os.environ.get("SELF_CHECK", "").strip().lower() in ("1", "true", "yes", "on")
EXTRA_ARTICLE_URLS = [u.strip() for u in os.environ.get("EXTRA_ARTICLE_URLS", "").split(",") if u.strip()]
STRICT_CORE_ONLY = os.environ.get("STRICT_CORE_ONLY", "false").strip().lower() in ("1", "true", "yes", "on")
DIGEST_HOUR_BD = int(os.environ.get("DIGEST_HOUR_BD", "7"))
DIGEST_CATCHUP_HOURS = int(os.environ.get("DIGEST_CATCHUP_HOURS", "5"))
SCAN_DAYS = int(os.environ.get("SCAN_DAYS", "0"))
SCAN_SOURCES = [s.strip().lower() for s in os.environ.get("SCAN_SOURCES", "").split(",") if s.strip()]
if (not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID) and not SELF_CHECK_MODE:
    print("ERROR: Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env file")
    print("Create .env with:\nTELEGRAM_BOT_TOKEN=your_token\nTELEGRAM_CHAT_ID=your_chat_id")
    sys.exit(1)

# --- GEMINI AI SETUP ---
try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
AI_FILTER_ENABLED = os.environ.get("AI_FILTER_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
AI_SUMMARIZE_ENABLED = os.environ.get("AI_SUMMARIZE_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")

if HAS_GENAI and GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        # Use flash for speed and cost efficiency
        gemini_model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        print(f"WARNING: Gemini AI initialization failed: {e}")
        HAS_GENAI = False

# --- FILES ---
SENT_LOG_FILE = "sent_articles.json"
WEB_DATA_FILE = os.path.join("docs", "news_data.json")
STATS_FILE = os.path.join("docs", "source_stats.json")
DIGEST_STATE_FILE = "digest_state.json"
BAD_SECTION_FILE = "bad_sections.json"

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
        "url": "https://www.dhakatribune.com/rss.xml", 
        "type": "rss"
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
        "url": "https://www.kalerkantho.com/rss.xml", 
        "type": "rss"
    },
    {
        "name": "Samakal",
        "url": "https://samakal.com/feed",
        "type": "rss"
    },
    {"name": "Desh Rupantor", "url": "https://www.deshrupantor.com/news_sitemap.xml", "type": "sitemap"},
    {"name": "Jugantor", "url": "https://www.jugantor.com/", "type": "html"},
    {"name": "Shomoyer Alo", "url": "https://www.shomoyeralo.com/", "type": "html"},
    {"name": "Just Energy News", "url": "https://justenergynews24.com/", "type": "html"},
    {"name": "Bangla Tribune", "url": "https://www.banglatribune.com/rss/all", "type": "rss"},
    {"name": "Jago News", "url": "https://www.jagonews24.com/", "type": "html"},
    {"name": "Ittefaq", "url": "https://www.ittefaq.com.bd/rss.xml", "type": "rss"},
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
    {
        "name": "BD Pratidin",
        "urls": [
            "https://www.bd-pratidin.com/",
            "https://www.bd-pratidin.com/last-page",
            "https://www.bd-pratidin.com/national"
        ],
        "type": "html"
    },
    {"name": "Bangladesh Today", "url": "https://thebangladeshtoday.com/", "type": "html"},
    {"name": "New Nation", "url": "https://dailynewnation.com/", "type": "html"},
    {"name": "New Age", "url": "https://www.newagebd.net/", "type": "html"},
    {"name": "Observer", "url": "https://www.observerbd.com/rss.php", "type": "rss"},
    {"name": "Daily Post", "url": "https://bangladeshpost.net/", "type": "html"},
    {
        "name": "Daily Sun",
        "urls": [
            "https://www.daily-sun.com/",
            "https://www.daily-sun.com/business",
            "https://www.daily-sun.com/business/latest"
        ],
        "type": "html"
    },
    {
        "name": "Daily Sun News Sitemap",
        "url": "https://www.daily-sun.com/news_sitemap.xml",
        "type": "sitemap"
    },
    {
        "name": "Financial Express (Sitemap)", 
        "url": "https://thefinancialexpress.com.bd/sitemap.xml", 
        "type": "html"
    },
    {
        "name": "Financial Express Today",
        "urls": [
            "https://thefinancialexpress.com.bd/",
            "https://thefinancialexpress.com.bd/trade",
            "https://thefinancialexpress.com.bd/economy"
        ],
        "type": "html"
    },
    {
        "name": "Financial Express Search",
        "urls": [
            "https://thefinancialexpress.com.bd/search?search=gas",
            "https://thefinancialexpress.com.bd/search?search=petrobangla"
        ],
        "type": "html"
    }
]

# Extra section pages to scan per domain so important articles do not get missed
# when publishers post to category/last-page routes instead of homepage.
DOMAIN_SECTION_HINTS = {
    "bd-pratidin.com": ["/last-page", "/national", "/news"],
    "kalerkantho.com": ["/online/national", "/online/business", "/print-edition/last-page"],
    "prothomalo.com": ["/bangladesh", "/business", "/topic/energy"],
    "thedailystar.net": ["/news/bangladesh", "/business", "/tags/energy"],
    "dhakatribune.com": ["/bangladesh", "/business", "/climate"],
    "tbsnews.net": ["/bangladesh", "/economy", "/topics/energy"],
    "daily-sun.com": ["/business", "/business/latest", "/news"],
    "thefinancialexpress.com.bd": ["/trade", "/economy", "/energy"],
    "today.thefinancialexpress.com.bd": ["/first-page", "/trade-market", "/search?search=gas"],
    "samakal.com": ["/bangladesh", "/economics", "/search?search=gas"],
}

COMMON_SECTION_HINTS = [
    "/bangladesh",
    "/national",
    "/business",
    "/economy",
    "/energy",
    "/latest",
    "/last-page",
    "/online",
    "/online/national",
    "/online/business",
    "/search?search=gas",
    "/search?search=petrobangla",
]

BAD_SECTION_PATHS = {}

# Only page-level exclusions requested by user.
BLOCKED_SECTION_KEYWORDS = [
    "/international", "/world", "/sports", "/sport", "/culture", "/entertainment"
]

# --- PRE-COMPILED KEYWORD PATTERNS ---
PRIMARY_PATTERNS = []
for kw in ["gas", "lng", "petrobangla", "bapex", "bgfcl", "sgfl", "gtcl", "titas", "bakhrabad",
           "jalalabad", "pashchimanchal", "rpgcl", "bcmcl", "mgmcl",
           "maddhapara", "barapukuria", "coal", "rock", "mining", "extraction", "drilling", "energy", "brahmanbaria"]:
    PRIMARY_PATTERNS.append(re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE))

PRIORITY_PATTERNS = [re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE) 
                     for kw in ["explosion", "blast", "fire", "emergency", "sudden", "crisis", "cutoff", "shut down", "accident"]]
PRIORITY_BENGALI = ["বিস্ফোরণ", "আগুন", "জরুরি", "সংকট", "বন্ধ", "দুর্ঘটনা", "আগুনে", "হতাহত"]


PRIMARY_BENGALI = ["গ্যাস", "এলএনজি", "পেট্রোবাংলা", "কয়লা খনি", "পাথর খনি",
                    "তিতাস", "বাপেক্স", "মধ্যপাড়া", "বড়পুকুরিয়া", "জিটিসিএল",
                    "আরপিজিসিএল", "জালালাবাদ", "গ্যাসহীন", "গ্যাস সংকট", "কয়লা", "পাথর", "খনি", "উত্তোলন"]

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
                                  "turkmenistan", "kazakhstan", "uzbekistan", "azerbaijan",
                                  "brick kiln", "brickfield", "crop damage", "paddy field",
                                  "stone quarry", "sand lifting", "illegal sand"]]
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
                     "কোভিড", "মহামারি", "টিকা", "হু",
                     "ইটভাটা", "ইট ভাটা", "ধান", "ধানক্ষেত", "কৃষিজমি",
                     "পাথর কোয়ারি", "বালু", "অবৈধ বালু", "মাটি উত্তোলন"]

# Always exclude these topics even if they match core keywords.
HARD_EXCLUDE_PATTERNS = [
    re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
    for kw in [
        "stone quarry", "quarry", "rock quarry", "pathor koari", "pathor quarry",
        "nuclear power plant", "nuclear plant", "nuclear energy", "nuclear reactor",
        "rooppur nuclear", "rupur nuclear", "atomic energy"
    ]
]
HARD_EXCLUDE_BENGALI = [
    "পাথর কোয়ারি", "পাথরকোয়ারি", "পাথর খাদান", "কোয়ারি",
    "পারমাণবিক বিদ্যুৎ", "পারমাণবিক বিদ্যুৎকেন্দ্র", "পারমাণবিক কেন্দ্র",
    "পারমাণবিক শক্তি", "রূপপুর পারমাণবিক", "রূপপুর বিদ্যুৎকেন্দ্র", "আণবিক শক্তি কমিশন"
]

GENERIC_TITLE_PATTERNS = [
    re.compile(r'^\s*(news|sports|last page|first page|home|video|photos?)\s*$', re.IGNORECASE),
    re.compile(r'^\s*\d{5,}\s*$'),
]

GENERIC_TITLE_BENGALI = [
    "প্রথম পাতা", "শেষের পাতা", "শেষ পাতা", "খেলা", "বিনোদন", "দেশে দেশে", "জাতীয়"
]

TRANSPORT_PATTERNS = [
    re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
    for kw in [
        "launch fare", "bus fare", "transport fare", "metro fare", "rickshaw fare",
        "vehicle fare", "ticket fare", "kilometre fare", "per kilometre", "fare hike",
        "fare increased", "fare increase"
    ]
]
TRANSPORT_BENGALI = [
    "লঞ্চ ভাড়া", "বাস ভাড়া", "ভাড়া বৃদ্ধি", "ভাড়া বৃদ্ধি", "পরিবহন ভাড়া",
    "প্রতি কিলোমিটার", "কিলোমিটার প্রতি", "টিকিট ভাড়া", "নৌভাড়া"
]

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
    # Migration: Check old location if new one doesn't exist
    if not os.path.exists(STATS_FILE) and os.path.exists("source_stats.json"):
        try:
            with open("source_stats.json", "r", encoding="utf-8") as f:
                SOURCE_STATS = json.load(f)
            log("Migrated source_stats.json to docs/ folder")
        except Exception:
            SOURCE_STATS = {}
    elif os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                SOURCE_STATS = json.load(f)
        except Exception:
            SOURCE_STATS = {}

def save_stats():
    os.makedirs("docs", exist_ok=True)
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(SOURCE_STATS, f, ensure_ascii=False, indent=2)

def load_digest_state():
    if os.path.exists(DIGEST_STATE_FILE):
        try:
            with open(DIGEST_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_digest_state(state):
    with open(DIGEST_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_bad_sections():
    global BAD_SECTION_PATHS
    if os.path.exists(BAD_SECTION_FILE):
        try:
            with open(BAD_SECTION_FILE, "r", encoding="utf-8") as f:
                BAD_SECTION_PATHS = json.load(f)
        except Exception:
            BAD_SECTION_PATHS = {}
    else:
        BAD_SECTION_PATHS = {}


def save_bad_sections():
    with open(BAD_SECTION_FILE, "w", encoding="utf-8") as f:
        json.dump(BAD_SECTION_PATHS, f, ensure_ascii=False, indent=2)


def save_to_web(new_articles):
    """Saves the latest news to a JSON file for the web dashboard."""
    if not new_articles:
        return
    
    # Ensure docs directory exists
    os.makedirs("docs", exist_ok=True)
    
    existing_news = []
    if os.path.exists(WEB_DATA_FILE):
        try:
            with open(WEB_DATA_FILE, "r", encoding="utf-8") as f:
                existing_news = json.load(f)
        except Exception:
            existing_news = []
            
    # Use link as unique ID
    seen_links = {a['link'] for a in existing_news}
    
    # Add new articles that aren't already in the list
    added_count = 0
    bd_tz = datetime.timezone(datetime.timedelta(hours=6))
    now_bd = datetime.datetime.now(bd_tz)
    now_str = now_bd.strftime("%I:%M %p")
    for art in new_articles:
        if art['link'] not in seen_links:
            # Add timestamp if not present (default to scan time)
            if 'time' not in art:
                art['time'] = f"{now_str} (Scan)"
            else:
                # If we have a time but no label, it was likely from the source
                if "(" not in art['time']:
                    art['time'] = f"{art['time']} (Pub)"
            
            existing_news.insert(0, art)
            seen_links.add(art['link'])
            added_count += 1
            
    # Keep only latest 50
    existing_news = existing_news[:50]
    
    try:
        with open(WEB_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(existing_news, f, ensure_ascii=False, indent=2)
        log(f"Web Dashboard updated: {added_count} new articles added to {WEB_DATA_FILE}")
    except Exception as e:
        log(f"Error saving to web: {e}")


def _host_key(url):
    p = urllib.parse.urlparse(url)
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _path_query_key(url):
    p = urllib.parse.urlparse(url)
    key = p.path or "/"
    if p.query:
        key += "?" + p.query
    return key


def _is_common_hint_url(url):
    p = urllib.parse.urlparse(url)
    key = _path_query_key(url)
    return key in COMMON_SECTION_HINTS and p.path not in ("", "/")


def mark_bad_section_url(url):
    if not _is_common_hint_url(url):
        return
    host = _host_key(url)
    path_key = _path_query_key(url)
    if host not in BAD_SECTION_PATHS:
        BAD_SECTION_PATHS[host] = []
    if path_key not in BAD_SECTION_PATHS[host]:
        BAD_SECTION_PATHS[host].append(path_key)


def is_known_bad_section_url(url):
    host = _host_key(url)
    path_key = _path_query_key(url)
    return path_key in BAD_SECTION_PATHS.get(host, [])

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
        if stats["last_fail_streak"] == 3:
            send_telegram_retry(f"⚠️ Source Monitoring Alert: I haven't been able to reach '{name}' for the last 3 attempts. It may need a layout update.")
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
    if SELF_CHECK_MODE:
        log("[SELF_CHECK] Telegram send skipped")
        return True
    text = "".join(ch for ch in text if ch.isprintable() or ch in "\n\r\t")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": True}
    if parse_mode:
        data["parse_mode"] = parse_mode
    payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, payload, headers={'Content-Type': 'application/json'})
    secure_ctx = ssl.create_default_context()
    insecure_ctx = ssl._create_unverified_context()
    try:
        resp = urllib.request.urlopen(req, timeout=15, context=secure_ctx)
        result = json.loads(resp.read())
        if not result.get("ok"):
            log(f"Telegram error: {result.get('description', 'unknown')}")
        return result.get("ok", False)
    except ssl.SSLError as e:
        log(f"Telegram SSL error, retrying insecurely: {e}")
        try:
            resp = urllib.request.urlopen(req, timeout=15, context=insecure_ctx)
            result = json.loads(resp.read())
            if not result.get("ok"):
                log(f"Telegram error: {result.get('description', 'unknown')}")
            return result.get("ok", False)
        except Exception as inner:
            log(f"Telegram send failed after SSL fallback: {inner}")
            return False
    except urllib.error.URLError as e:
        msg = str(e)
        if "CERTIFICATE_VERIFY_FAILED" in msg or "self-signed certificate" in msg:
            log(f"Telegram cert verify failed, retrying insecurely: {e}")
            try:
                resp = urllib.request.urlopen(req, timeout=15, context=insecure_ctx)
                result = json.loads(resp.read())
                if not result.get("ok"):
                    log(f"Telegram error: {result.get('description', 'unknown')}")
                return result.get("ok", False)
            except Exception as inner:
                log(f"Telegram send failed after cert fallback: {inner}")
                return False
        log(f"Telegram send failed: {e}")
        return False
    except Exception as e:
        log(f"Telegram send failed: {e}")
        return False

def send_telegram_retry(text, retries=3):
    for i in range(retries):
        if send_telegram(text):
            return True
        time.sleep(2)
    return False

def chunk_telegram_message(text, max_len=3800):
    if len(text) <= max_len:
        return [text]
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, max_len)
        if split_at < 200:
            split_at = max_len
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    return chunks

def send_telegram_chunked(text, parse_mode="HTML", retries=3):
    chunks = chunk_telegram_message(text)
    for idx, chunk in enumerate(chunks, 1):
        ok = False
        for _ in range(retries):
            if send_telegram(chunk, parse_mode=parse_mode):
                ok = True
                break
            time.sleep(2)
        if not ok:
            log(f"Failed to send Telegram chunk {idx}/{len(chunks)}")
            return False
        if len(chunks) > 1:
            log(f"Telegram chunk {idx}/{len(chunks)} sent")
            time.sleep(0.4)
    return True

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
    # Add persistent human headers
    scraper.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Referer': 'https://www.google.com/',
        'Sec-Ch-Ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'cross-site',
        'Upgrade-Insecure-Requests': '1'
    })
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
                    log(f"HTTP {response.status_code} for {url} (cloudscraper)")
                    if response.status_code == 404:
                        mark_bad_section_url(url)

            # urllib fallback (runs when cloudscraper unavailable or non-200)
            headers = {
                "User-Agent": USER_AGENTS[i % len(USER_AGENTS)],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,bn;q=0.8",
                "Upgrade-Insecure-Requests": "1",
                "Referer": "https://www.google.com/",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache"
            }
            req = urllib.request.Request(encoded_url, headers=headers)
            secure_ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=15, context=secure_ctx) as response:
                return response.read()
        except ssl.SSLError as e:
            try:
                insecure_ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(req, timeout=15, context=insecure_ctx) as response:
                    log(f"SSL fallback used for {url}: {e}")
                    return response.read()
            except Exception as inner:
                if i == retries:
                    log(f"SSL fetch error for {url}: {inner}")
                else:
                    time.sleep(1)
        except Exception as e:
            if hasattr(e, 'code') and e.code == 403:
                if i == retries:
                    log(f"HTTP 403 for {url}")
                else:
                    time.sleep(1.2)
                continue
            if hasattr(e, 'code') and e.code == 404:
                mark_bad_section_url(url)
                if i == retries:
                    log(f"HTTP 404 for {url}")
                else:
                    time.sleep(0.6)
                continue
            if i == retries:
                log(f"Fetch error for {url}: {e}")
            else:
                time.sleep(1)
    return None

# --- KEYWORD MATCHING ---
def is_keyword_match(text):
    text_lower = text.lower()

    # Strict bypass for core gas/pipeline/Petrobangla terms.
    strict_terms = [
        "petrobangla", "pipeline gas", "gas pipeline", "gas transmission",
        "gas distribution", "lng", "well drilling", "gas well", "titas gas",
        "jalalabad gas", "bakhrabad gas", "gtcl", "bgfcl", "sgfl", "bapex",
        "পেট্রোবাংলা", "পাইপলাইন গ্যাস", "গ্যাস পাইপলাইন", "গ্যাস সঞ্চালন",
        "গ্যাস বিতরণ", "এলএনজি", "গ্যাস কূপ", "কূপ খনন", "তিতাস গ্যাস",
        "জালালাবাদ গ্যাস", "বাখরাবাদ গ্যাস", "বাপেক্স"
    ]
    if any(t in text_lower for t in strict_terms):
        return True

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

def is_priority_match(text):
    text_lower = text.lower()
    for pat in PRIORITY_PATTERNS:
        if pat.search(text_lower):
            return True
    for kw in PRIORITY_BENGALI:
        if kw in text_lower:
            return True
    return False


def is_core_target_match(text):
    text_lower = text.lower()
    core_terms = [
        "petrobangla", "pipeline gas", "gas pipeline", "gas transmission",
        "gas distribution", "lng", "well drilling", "gas well", "titas gas",
        "jalalabad gas", "bakhrabad gas", "gtcl", "bgfcl", "sgfl", "bapex",
        "piped gas", "distribution company", "mmcf", "gasfield", "gas field",
        "barapukuria", "maddhapara", "bcmcl", "mgmcl", "coal mine", "rock mine",
        "পেট্রোবাংলা", "পাইপলাইন গ্যাস", "গ্যাস পাইপলাইন", "গ্যাস সঞ্চালন",
        "গ্যাস বিতরণ", "এলএনজি", "গ্যাস কূপ", "কূপ খনন", "তিতাস গ্যাস",
        "জালালাবাদ গ্যাস", "বাখরাবাদ গ্যাস", "বাপেক্স", "গ্যাসক্ষেত্র", "গ্যাস ফিল্ড",
        "বড়পুকুরিয়া", "মধ্যপাড়া", "কয়লা খনি", "পাথর খনি"
    ]
    return any(term in text_lower for term in core_terms)


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


def should_exclude_text(text):
    """Exclude generic/global topics, but keep clearly core target news."""
    text_lower = text.lower()
    for pat in HARD_EXCLUDE_PATTERNS:
        if pat.search(text_lower):
            return True
    for kw in HARD_EXCLUDE_BENGALI:
        if kw in text_lower:
            return True

    # Exclude transport fare stories unless they contain strong core targets.
    is_transport_fare = any(p.search(text_lower) for p in TRANSPORT_PATTERNS) or any(k in text_lower for k in TRANSPORT_BENGALI)
    if is_transport_fare and not is_core_target_match(text):
        return True

    if is_core_target_match(text):
        return False
    return is_excluded(text)


def is_generic_title(text):
    t = (text or "").strip().lower()
    if not t:
        return True
    for p in GENERIC_TITLE_PATTERNS:
        if p.search(t):
            return True
    for kw in GENERIC_TITLE_BENGALI:
        if kw in t and len(t) <= 20:
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
            if not is_keyword_match(title) or should_exclude_text(title):
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
                art_obj = {"title": title.strip(), "link": link.strip(), "source": source_name}
                if date_node is not None and date_node.text:
                    try:
                        art_obj["time"] = pub_date_bd.strftime("%I:%M %p")
                    except Exception:
                        pass
                articles.append(art_obj)
    except Exception as e:
        log(f"RSS parse error ({source_name}): {e}")
    return articles

def parse_html(data, source_name, base_url):
    articles = []
    seen_links = set()
    try:
        if HAS_BS4:
            soup = BeautifulSoup(data, 'html.parser')

            # Source-specific extraction: Daily Sun uses overlay anchors with headline in sibling heading tags.
            if 'daily-sun.com' in base_url:
                for a in soup.find_all('a', href=True):
                    cls = ' '.join(a.get('class', []))
                    href = a.get('href', '').strip()
                    if 'linkOverlay' not in cls or not href:
                        continue
                    full_link = urllib.parse.urljoin(base_url, href) if not href.startswith('http') else href
                    if full_link in seen_links:
                        continue
                    box = a.find_parent('div', class_=re.compile(r'positionRelative|baseHover|desktopSectionLead', re.IGNORECASE)) or a.parent
                    title_node = box.find(['h1', 'h2', 'h3', 'h4', 'strong']) if box else None
                    title_text = title_node.get_text(separator=' ', strip=True) if title_node else ''
                    if len(title_text) < 15:
                        continue
                    if not is_keyword_match(title_text) or should_exclude_text(title_text):
                        continue
                    skip_url_zones = ['/tag/', '/category/', '/archive/', '/search/', '/author/',
                                      '/login', '/register', '/about', '/contact', '/privacy',
                                      '/terms', '/sitemap', '/feed', '/rss', '/atom',
                                      '/wp-admin', '/wp-content', '/wp-includes', '/cdn-cgi',
                                      'petrobangla.org', 'facebook.com', 'twitter.com', 'youtube.com',
                                      'instagram.com', 'wa.me', 't.me']
                    if any(z in full_link.lower() for z in skip_url_zones):
                        continue
                    
                    # Try to find time
                    found_time = None
                    if box:
                        time_node = box.find(['time', 'span'], class_=re.compile(r'time|date|published', re.IGNORECASE))
                        if time_node:
                            found_time = time_node.get_text(strip=True)
                    
                    art_obj = {"title": title_text, "link": full_link, "source": source_name}
                    if found_time:
                        art_obj["time"] = found_time
                    
                    seen_links.add(full_link)
                    articles.append(art_obj)

            for tag in soup.find_all('a', href=True):
                link = tag['href']
                if link in seen_links:
                    continue
                text = tag.get_text(strip=True)
                full_link = urllib.parse.urljoin(base_url, link) if not link.startswith('http') else link
                if is_blocked_section_url(full_link):
                    continue

                # Recovery path for date-based article URLs that may have short/generic anchor text.
                # This helps catch links like /news/2026/05/07/... or /print-edition/... that are often
                # rendered in compact blocks and can be skipped by strict text-length filters.
                date_url = re.search(r'/20\d{2}/\d{2}/\d{2}/', full_link)
                is_recovery_domain = (
                    ('bd-pratidin.com' in full_link.lower()) or
                    ('kalerkantho.com' in full_link.lower())
                )
                is_recovery_path = (
                    '/last-page/' in full_link.lower() or
                    '/print-edition/' in full_link.lower() or
                    '/news/' in full_link.lower()
                )
                if is_recovery_domain and (date_url or is_recovery_path):
                    skip_url_zones = ['/tag/', '/category/', '/archive/', '/search/', '/author/',
                                      '/login', '/register', '/about', '/contact', '/privacy',
                                      '/terms', '/sitemap', '/feed', '/rss', '/atom',
                                      '/wp-admin', '/wp-content', '/wp-includes', '/cdn-cgi',
                                      'facebook.com', 'twitter.com', 'youtube.com', 'instagram.com',
                                      'wa.me', 't.me']
                    if not any(z in full_link.lower() for z in skip_url_zones):
                        if is_blocked_section_url(full_link):
                            continue
                        fallback_title = text if text and len(text) >= 8 else full_link.rstrip('/').split('/')[-1].replace('-', ' ')
                        if is_generic_title(fallback_title):
                            continue
                        # Strict guard for recovery path: require core target signal in title/url context.
                        recovery_context = f"{fallback_title} {full_link.replace('-', ' ').replace('_', ' ')}"
                        if not is_core_target_match(recovery_context):
                            continue
                        seen_links.add(link)
                        
                        # Try to find nearby time
                        found_time = None
                        p = tag.parent
                        for _ in range(3): # Look up 3 levels
                            if not p: break
                            t_node = p.find(['time', 'span', 'small'], class_=re.compile(r'time|date|published|hour', re.IGNORECASE))
                            if t_node:
                                found_time = t_node.get_text(strip=True)
                                break
                            p = p.parent

                        art_obj = {"title": fallback_title, "link": full_link, "source": source_name}
                        if found_time:
                            art_obj["time"] = found_time
                        articles.append(art_obj)
                        continue

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
                full_text = text
                # SMART CHECK: If the link text is generic (like "Read more"), check the parent container's text
                if len(text) < 15 or any(word in text.lower() for word in ["read more", "full story", "click here", "বিস্তারিত"]):
                        heading_node = tag.parent.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b'])
                        if not heading_node and tag.parent.parent:
                            heading_node = tag.parent.parent.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b'])
                        if not heading_node and tag.parent.parent.parent:
                            heading_node = tag.parent.parent.parent.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b'])

                        heading = heading_node.get_text(strip=True) if heading_node else ""
                        if len(heading) > 15:
                            full_text = heading
                        elif is_keyword_match(link.replace('-', ' ').replace('_', ' ')):
                            full_text = link.replace('-', ' ').replace('_', ' ')
                        else:
                            continue
                
                if not is_keyword_match(full_text) or should_exclude_text(full_text):
                    continue
                    
                skip_url_zones = ['/tag/', '/category/', '/archive/', '/search/', '/author/',
                                  '/login', '/register', '/about', '/contact', '/privacy',
                                  '/terms', '/sitemap', '/feed', '/rss', '/atom',
                                  '/wp-admin', '/wp-content', '/wp-includes', '/cdn-cgi',
                                  'petrobangla.org', 'facebook.com', 'twitter.com', 'youtube.com',
                                  'instagram.com', 'wa.me', 't.me']
                if any(z in full_link.lower() for z in skip_url_zones):
                    continue
                if is_blocked_section_url(full_link):
                    continue
                seen_links.add(link)
                
                # Try to find nearby time
                found_time = None
                p = tag.parent
                for _ in range(3): # Look up 3 levels
                    if not p: break
                    t_node = p.find(['time', 'span'], class_=re.compile(r'time|date|published|hour', re.IGNORECASE))
                    if t_node:
                        found_time = t_node.get_text(strip=True)
                        break
                    p = p.parent

                art_obj = {"title": full_text, "link": full_link, "source": source_name}
                if found_time:
                    art_obj["time"] = found_time
                articles.append(art_obj)
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
                if not is_keyword_match(text) or should_exclude_text(text):
                    continue
                full_link = urllib.parse.urljoin(base_url, link) if not link.startswith('http') else link
                # Regex mode doesn't easily find nearby tags, so we use scan time here.
                articles.append({"title": text, "link": full_link, "source": source_name})
    except Exception as e:
        log(f"HTML parse error ({source_name}): {e}")
    return articles

def parse_sitemap(data, source_name):
    articles = []
    seen = set()
    try:
        root = ET.fromstring(data)
        for url_node in root.findall('.//{*}url'):
            loc = url_node.find('{*}loc')
            if loc is None or not loc.text:
                continue
            link = loc.text.strip()
            if not link or link in seen:
                continue
            seen.add(link)

            title_node = url_node.find('.//{*}title')
            keywords_node = url_node.find('.//{*}keywords')
            slug = link.rstrip('/').split('/')[-1]
            candidate_title = title_node.text.strip() if (title_node is not None and title_node.text) else slug.replace('-', ' ').replace('_', ' ')
            keyword_hint = keywords_node.text.strip() if (keywords_node is not None and keywords_node.text) else ""
            candidate_text = f"{candidate_title} {keyword_hint}".strip()

            if not is_keyword_match(candidate_text) or should_exclude_text(candidate_text):
                continue

            art_obj = {"title": candidate_title, "link": link, "source": source_name}
            lastmod_node = url_node.find('{*}lastmod')
            if lastmod_node is not None and lastmod_node.text:
                try:
                    # Sitemap dates are usually ISO format
                    dt = datetime.datetime.fromisoformat(lastmod_node.text.replace('Z', '+00:00'))
                    dt_bd = dt.astimezone(datetime.timezone(datetime.timedelta(hours=6)))
                    art_obj["time"] = dt_bd.strftime("%I:%M %p")
                except Exception:
                    pass
            articles.append(art_obj)
    except Exception as e:
        log(f"Sitemap parse error ({source_name}): {e}")
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

        if is_generic_title(article['title']):
            log(f"  ⏭ Generic title: {article['title'][:60]}...")
            return None

        if STRICT_CORE_ONLY and not is_core_target_match(full_text):
            log(f"  ⏭ Not core target: {article['title'][:60]}...")
            return None

        # Always check keyword relevance, even for short bodies.
        if not is_keyword_match(full_text):
            log(f"  ⏭ Irrelevant (no target keyword): {article['title'][:60]}...")
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
        # --- GEMINI AI SMART FILTER ---
        if HAS_GENAI and GEMINI_API_KEY and AI_FILTER_ENABLED:
            relevance = ai_verify_relevance(article['title'], body)
            if not relevance:
                log(f"  🤖 AI Filtered (Irrelevant): {article['title'][:60]}...")
                return None
            if AI_SUMMARIZE_ENABLED:
                summary = ai_summarize_article(article['title'], body)
                if summary:
                    article['summary'] = summary
        return article
    except Exception as e:
        log(f"  ⏭ Error verifying: {article['title'][:60]}... ({e})")
        return None

def scrape_source(source, start_time, end_time):
    name = source['name']
    urls_to_scan = get_urls_to_scan(source)
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
            elif source.get('type', 'html') == 'sitemap':
                articles = parse_sitemap(data, name)
                if articles:
                    verified = []
                    for art in articles:
                        result = verify_article(art, start_time, end_time)
                        if result is not None:
                            verified.append(result)
                        time.sleep(0.2)
                    articles = verified
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


def get_urls_to_scan(source):
    urls = list(source.get('urls', [source.get('url')] if source.get('url') else []))
    urls = [u for u in urls if u]
    if source.get('type', 'html') != 'html' or not urls:
        return urls

    # Use first URL as canonical base for hint expansion.
    base_url = urls[0]
    parsed = urllib.parse.urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        return urls

    host = parsed.netloc.lower()
    if host.startswith('www.'):
        host = host[4:]

    hints = []
    for domain, paths in DOMAIN_SECTION_HINTS.items():
        if host == domain or host.endswith('.' + domain):
            hints = paths
            break

    # Always include a conservative common set for all newspaper domains,
    # then merge any domain-specific hints.
    hints = list(dict.fromkeys(COMMON_SECTION_HINTS + hints))

    expanded = [u for u in urls if (not is_blocked_section_url(u) and not is_known_bad_section_url(u))]
    for path in hints:
        try:
            candidate = urllib.parse.urljoin(f"{parsed.scheme}://{parsed.netloc}/", path)
            if not is_blocked_section_url(candidate) and not is_known_bad_section_url(candidate):
                expanded.append(candidate)
        except Exception:
            continue

    # Keep order, drop duplicates
    seen = set()
    unique = []
    for u in expanded:
        if u in seen:
            continue
        seen.add(u)
        unique.append(u)
    return unique


def is_blocked_section_url(url):
    u = (url or "").lower()
    return any(k in u for k in BLOCKED_SECTION_KEYWORDS)

# --- MAIN SCRAPE ---
def scrape_all(ignore_sent_history=False):
    start_run_time = time.time()
    log("=" * 50)
    log("News Aggregator Started")
    log("=" * 50)
    load_stats()
    load_bad_sections()
    stats_before = {
        name: (s.get("success", 0), s.get("fail", 0))
        for name, s in SOURCE_STATS.items()
    }
    
    bd_tz = datetime.timezone(datetime.timedelta(hours=6))
    now_bd = datetime.datetime.now(bd_tz)
    digest_state = load_digest_state()
    today_bd = now_bd.strftime("%Y-%m-%d")
    last_digest_date = digest_state.get("last_digest_date")
    force_digest = os.environ.get("FORCE_DIGEST", "").strip().lower() in ("1", "true", "yes", "on")

    in_digest_window = (now_bd.hour == DIGEST_HOUR_BD)
    if DIGEST_CATCHUP_HOURS > 0 and now_bd.hour > DIGEST_HOUR_BD:
        in_digest_window = now_bd.hour <= (DIGEST_HOUR_BD + DIGEST_CATCHUP_HOURS)
    should_send_daily_digest = force_digest or (in_digest_window and last_digest_date != today_bd)
    
    search_query = os.environ.get("SEARCH_QUERY")
    if search_query:
        log(f"Running in SEARCH MODE for: {search_query}")
        start_time = now_bd - datetime.timedelta(days=7)
    elif SCAN_DAYS > 0:
        log(f"Running custom scan for last {SCAN_DAYS} days")
        start_time = now_bd - datetime.timedelta(days=SCAN_DAYS)
    else:
        # If we're in digest window, scan full 24 hours for digest.
        # Otherwise, we scan a shorter window (2.5 hours) to catch new articles for alerts.
        if should_send_daily_digest:
            start_time = now_bd - datetime.timedelta(hours=24)
        else:
            start_time = now_bd - datetime.timedelta(hours=2.5)
        
    sent_articles = set() if ignore_sent_history else load_sent_articles()
    all_new = []
    web_news = []
    priority_news = []
    run_seen_links = set()
    
    active_sources = SOURCES
    if SCAN_SOURCES:
        active_sources = [s for s in SOURCES if s['name'].lower() in SCAN_SOURCES]
        log(f"Filtering for {len(active_sources)} selected sources")

    log(f"Scanning {len(active_sources)} sources (parallel)...")
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(scrape_source, src, start_time, now_bd): src for src in active_sources}
        for future in as_completed(futures):
            source = futures[future]
            try:
                articles = future.result()
                for art in articles:
                    if art['link'] in run_seen_links:
                        continue
                    run_seen_links.add(art['link'])
                    
                    # Always include in web news
                    web_news.append(art)
                    
                    # Only include in Telegram if not already sent
                    if ignore_sent_history or art['link'] not in sent_articles:
                        if search_query:
                            if search_query.lower() in art['title'].lower():
                                all_new.append(art)
                        else:
                            all_new.append(art)
                            if is_priority_match(art['title']):
                                priority_news.append(art)
            except Exception as e:
                log(f"  Error processing {source['name']}: {e}")

    if EXTRA_ARTICLE_URLS:
        log(f"Checking {len(EXTRA_ARTICLE_URLS)} extra direct article URLs...")
        for extra_url in EXTRA_ARTICLE_URLS:
            extra_article = {"title": extra_url, "link": extra_url, "source": "Manual URL"}
            verified = verify_article(extra_article, start_time, now_bd)
            if verified is not None:
                if verified['link'] in run_seen_links:
                    continue
                run_seen_links.add(verified['link'])
                web_news.append(verified)
                
                if ignore_sent_history or verified['link'] not in sent_articles:
                    all_new.append(verified)
                    if is_priority_match(verified['title']):
                        priority_news.append(verified)

    save_stats()
    save_bad_sections()

    successful_sources = 0
    failed_sources = 0
    for name, stats in SOURCE_STATS.items():
        prev_success, prev_fail = stats_before.get(name, (0, 0))
        if stats.get("success", 0) > prev_success:
            successful_sources += 1
        if stats.get("fail", 0) > prev_fail:
            failed_sources += 1
    log(f"Health: {successful_sources} sources succeeded, {failed_sources} sources failed this run")

    if search_query:
        if all_new:
            msg = f"🔍 <b>Search Results: '{search_query}'</b>\n" + "-"*30 + "\n\n"
            for i, art in enumerate(all_new[:15], 1):
                msg += f"{i}. <a href='{html.escape(art['link'])}'>{html.escape(art['title'])}</a>\n\n"
            send_telegram_chunked(msg)
        else:
            send_telegram_retry(f"🔍 Search for '{search_query}' yielded no new results.")
        return

    # 1. Handle Breaking News Alerts (Instant)
    if priority_news:
        msg = "🚨 <b>BREAKING NEWS ALERT</b> 🚨\n" + "="*30 + "\n\n"
        for art in priority_news:
            msg += f"🔥 <b>{html.escape(art['title'])}</b>\n📌 {art['source']}\n🔗 <a href='{html.escape(art['link'])}'>Read Article</a>\n\n"
            sent_articles.add(art['link'])
        send_telegram_chunked(msg)
        save_sent_articles(sent_articles)

    # 2. Handle Daily Digest
    if should_send_daily_digest:
        if web_news:
            header = f"☀️ <b>Daily News Digest — {now_bd.strftime('%d %b %Y')}</b>\n"
            header += f"Found {len(web_news)} relevant articles.\n" + "="*30 + "\n\n"
            
            # Sort: Priority first
            web_news.sort(key=lambda x: is_priority_match(x['title']), reverse=True)
            
            body = ""
            for i, art in enumerate(web_news, 1):
                prefix = "🔴 " if is_priority_match(art['title']) else f"{i}. "
                summary_text = f"\n📝 <i>{html.escape(art.get('summary', ''))}</i>" if art.get('summary') else ""
                item = f"{prefix}<a href='{html.escape(art['link'])}'>{html.escape(art['title'])}</a>\n📌 {art['source']}{summary_text}\n\n"
                if len(header + body + item) > 3800:
                    send_telegram_chunked(header + body)
                    header = ""
                    body = ""
                body += item
                sent_articles.add(art['link'])
            
            sent_ok = send_telegram_chunked(header + body)
            if sent_ok:
                log(f"Digest sent to Telegram ({len(web_news)} articles)")
                save_sent_articles(sent_articles)
                digest_state["last_digest_date"] = today_bd
                digest_state["last_digest_sent_at"] = now_bd.strftime("%Y-%m-%d %H:%M:%S")
                save_digest_state(digest_state)
            else:
                log("Digest send failed; state not advanced so it can retry later")
        else:
            sent_ok = send_telegram_retry("☀️ Good Morning! No new energy news found in the last 24 hours.")
            if sent_ok:
                digest_state["last_digest_date"] = today_bd
                digest_state["last_digest_sent_at"] = now_bd.strftime("%Y-%m-%d %H:%M:%S")
                save_digest_state(digest_state)
            else:
                log("No-news digest send failed; state not advanced so it can retry later")
    
    if web_news:
        save_to_web(web_news)
    
    end_run_time = time.time()
    duration_sec = int(end_run_time - start_run_time)
    duration_str = f"{duration_sec // 60}m {duration_sec % 60}s"
    
    # Save global stats
    SOURCE_STATS["_meta"] = {
        "last_run_at": now_bd.strftime("%Y-%m-%d %H:%M:%S"),
        "duration": duration_str,
        "articles_found": len(all_new),
        "successful_sources": successful_sources,
        "failed_sources": failed_sources
    }
    save_stats()
    
    log(f"Scrape completed in {duration_str}. Found {len(all_new)} new articles.")


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
    elif cmd == "last24":
        os.environ["FORCE_DIGEST"] = "true"
        scrape_all(ignore_sent_history=True)
    else:
        send_telegram_retry("Unknown command. Use: /stats, /sources, /trigger, /last24")

# --- HELPERS ---
def get_target_timeframe():
    bd_tz = datetime.timezone(datetime.timedelta(hours=6))
    now_bd = datetime.datetime.now(bd_tz)
    start_time = now_bd - datetime.timedelta(hours=24)
    return start_time, now_bd

# --- AI LOGIC ---
def ai_verify_relevance(title, body):
    """Use Gemini to verify if the article is actually about BD energy sector."""
    if not HAS_GENAI or not gemini_model:
        return True
    
    prompt = f"""
    You are a professional energy sector analyst for Bangladesh. 
    Analyze the following article (Title and Snippet) and determine if it is directly relevant to:
    1. Bangladesh's Natural Gas, LNG, or Coal mining sector.
    2. Petrobangla or its subsidiaries (Titas, Bapex, GTCL, etc.).
    3. Major energy infrastructure (pipelines, drilling, extraction) in Bangladesh.
    
    Exclude: LPG cylinders, international oil prices (unless affecting BD power/gas), generic global climate news, or routine transport fare news.
    
    Title: {title}
    Snippet: {body[:1500]}
    
    Answer ONLY 'YES' if it is highly relevant, or 'NO' if it is not.
    """
    try:
        response = gemini_model.generate_content(prompt)
        answer = response.text.strip().upper()
        return "YES" in answer
    except Exception as e:
        log(f"  🤖 AI Error (Filter): {e}")
        return True # Fallback to true so we don't miss news on error

def ai_summarize_article(title, body):
    """Generate a 2-sentence summary for the article."""
    if not HAS_GENAI or not gemini_model or not body:
        return None
    
    prompt = f"""
    Summarize this news article in 2 concise sentences for a professional energy industry update.
    Focus on the core impact (e.g. gas production increase, pipeline leak, new drilling contract).
    Language: If the title is in Bengali, provide the summary in Bengali. If English, use English.
    
    Title: {title}
    Text: {body[:2000]}
    
    Summary:
    """
    try:
        response = gemini_model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        log(f"  🤖 AI Error (Summary): {e}")
        return None

# --- ENTRY ---
if __name__ == "__main__":
    args = sys.argv[1:]
    if args:
        cmd = args[0].lstrip("-/").lower()
        handle_command(cmd)
    else:
        scrape_all()
