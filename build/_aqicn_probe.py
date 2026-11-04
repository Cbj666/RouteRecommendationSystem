import json, os, sys, urllib.parse, urllib.request
from pathlib import Path

root = Path(r"E:\MyProject\等时圈交通可达性分析系统")
env = {}
for line in (root / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    env[k.strip()] = v.strip().strip('"').strip("'")
tok = env.get("AQICN_TOKEN")
print("token loaded:", bool(tok), "len", len(tok or ""))

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

calls = {
    "city/wuhan": f"https://api.waqi.info/feed/wuhan/?token={tok}",
    "geo/wuhan-center": f"https://api.waqi.info/feed/geo:30.5928;114.3055/?token={tok}",
    "search/wuhan": f"https://api.waqi.info/search/?token={tok}&keyword=wuhan",
}
for name, url in calls.items():
    print("\n=====", name)
    try:
        d = get(url)
    except Exception as e:
        print("  ERROR", type(e).__name__, e)
        continue
    print("  status:", d.get("status"))
    data = d.get("data")
    if isinstance(data, list):
        print("  count:", len(data))
        for it in data[:8]:
            st = it.get("station", {})
            print("   -", it.get("aqi"), "|", st.get("name"), "|", st.get("geo"), "| time", it.get("time", {}).get("stime"))
    elif isinstance(data, dict):
        for k in ("aqi", "idx"):
            print(f"  {k}:", data.get(k))
        print("  city:", data.get("city"))
        print("  time:", data.get("time"))
        iaqi = data.get("iaqi", {})
        print("  iaqi keys:", list(iaqi))
        print("  iaqi:", {k: v.get("v") for k, v in iaqi.items()})
        print("  forecast keys:", list(data.get("forecast", {})))
        print("  attributions:", data.get("attributions"))
    else:
        print("  data:", str(data)[:300])
