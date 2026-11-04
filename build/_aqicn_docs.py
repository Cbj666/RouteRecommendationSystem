import re, urllib.request

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    for enc in ("utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")

for url in ["https://aqicn.org/json-api/doc/", "https://aqicn.org/api/"]:
    print("=" * 70)
    print(url)
    try:
        html = fetch(url)
    except Exception as e:
        print("  ERR", type(e).__name__, e)
        continue
    txt = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    txt = re.sub(r"(?s)<[^>]+>", "\n", txt)
    txt = re.sub(r"&nbsp;?", " ", txt)
    txt = re.sub(r"&amp;", "&", txt)
    txt = re.sub(r"\n\s*\n+", "\n", txt)
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    print("  lines:", len(lines))
    # 打印含关键词的行
    kw = ("feed", "token", "rate", "limit", "hour", "free", "commercial", "geo:", "search", "map/bounds", "aqi", "iaqi", "forecast", "error")
    hits = [l for l in lines if any(k in l.lower() for k in kw)]
    for l in hits[:90]:
        print("   ", l[:200])
