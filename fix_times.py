import json
import datetime

with open('docs/news_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

bd_tz = datetime.timezone(datetime.timedelta(hours=6))
now_bd = datetime.datetime.now(bd_tz)
now_str = now_bd.strftime("%I:%M %p")

for art in data:
    if art.get('time') == "05:05 AM":
        art['time'] = f"11:05 AM (Pub)"
    elif 'time' not in art or "(Scan)" not in art.get('time', ''):
        if not art.get('time'):
            art['time'] = f"{now_str} (Scan)"

with open('docs/news_data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("Updated timestamps in news_data.json")
