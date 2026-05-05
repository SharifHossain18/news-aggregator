import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import datetime
import ssl
import re
import html
import sys
import os
import io
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SOURCES = [
    {"name": "Prothom Alo", "url": "https://www.prothomalo.com/", "type": "html"},
    {"name": "Daily Star", "url": "https://www.thedailystar.net/", "type": "html"},
    {"name": "Dhaka Tribune", "url": "https://www.dhakatribune.com/", "type": "html"},
    {"name": "TBS News", "url": "https://tbsnews.net/", "type": "html"},
    {"name": "Kaler Kantho", "url": "https://www.kalerkantho.com/", "type": "html"},
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
    {"name": "Financial Express", "url": "https://thefinancialexpress.com.bd/", "type": "html"},
]

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
                                  "international", "thermal power plant", "power plant",
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

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

def fetch_url(url, retries=3):
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENTS[i % len(USER_AGENTS)]})
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
                return response.read()
        except Exception:
            import time
            if i < retries:
                time.sleep(1)
    return None

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
    if has_foreign and re.search(r'\b(with us|with bangladesh)\b', text_lower):
        return True
    return False

def parse_html(data, source_name, base_url):
    articles = []
    seen_links = set()
    try:
        html_str = data.decode('utf-8', errors='ignore')
        soup = BeautifulSoup(html_str, 'html.parser')
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
    except Exception as e:
        print(f"  HTML parse error ({source_name}): {e}")
    return articles

bd_tz = datetime.timezone(datetime.timedelta(hours=6))
now_bd = datetime.datetime.now(bd_tz)
cutoff = now_bd - datetime.timedelta(hours=24)

print(f"\n{'='*60}")
print(f"  Bangladesh Energy/Mining News — Last 24 Hours")
print(f"  Scanned at: {now_bd.strftime('%Y-%m-%d %H:%M:%S')} BD time")
print(f"  Cutoff: {cutoff.strftime('%Y-%m-%d %H:%M:%S')} BD time")
print(f"{'='*60}\n")

all_articles = []

for source in SOURCES:
    name = source['name']
    print(f"  Scanning {name}...")
    try:
        data = fetch_url(source['url'])
        if data is None:
            continue
        if source['type'] == 'html':
            articles = parse_html(data, name, source['url'])
            for art in articles:
                all_articles.append(art)
    except Exception as e:
        print(f"  Error ({name}): {e}")

if not all_articles:
    print("\nNo articles found in the last 24 hours.")
else:
    print(f"\n{'='*60}")
    print(f"  Found {len(all_articles)} articles:")
    print(f"{'='*60}\n")

    for i, art in enumerate(all_articles, 1):
        print(f"  {i}. {art['title']}")
        print(f"     📌 {art['source']}")
        print(f"     🔗 {art['link']}")
        print(f"     ⏰ Posted: within last 24 hours (exact time not available from HTML source)")
        print()
