import sys
import os
sys.path.append(os.getcwd())
from news_aggregator import fetch_url

urls = [
    "https://www.kalerkantho.com/rss.xml",
    "https://samakal.com/feed",
    "https://www.deshrupantor.com/sitemap.xml",
    "https://www.dhakatribune.com/news-sitemap.xml",
    "https://www.banglatribune.com/news-sitemap.xml",
    "https://www.ittefaq.com.bd/news-sitemap.xml",
    "https://www.observerbd.com/sitemap.php"
]

for url in urls:
    print(f"Testing {url}...")
    data = fetch_url(url)
    if data:
        print(f"  SUCCESS! Size: {len(data)} bytes")
    else:
        print(f"  FAILED!")
