import json, urllib.request
from pathlib import Path

root = Path(r"E:\MyProject\等时圈交通可达性分析系统")
env = dict(l.strip().split("=", 1) for l in (root / ".env").read_text(encoding="utf-8").splitlines()
           if l.strip() and not l.startswith("#") and "=" in l)
tok = env["AQICN_TOKEN"].strip()

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

tests = {
  "feed/@station 1529": f"https://api.waqi.info/feed/@1529/?token={tok}",
  "map/bounds 武汉": f"https://api.waqi.info/map/bounds/?token={tok}&latlng=30.35,114.05,30.85,114.65",
  "bad token": "https://api.waqi.info/feed/wuhan/?token=deadbeef",
}
for name, url in tests.items():
    print("=" * 60); print(name)
    try:
        d = get(url)
    except Exception as e:
        print("  ERR", type(e).__name__, e); continue
    print("  status:", d.get("status"))
    data = d.get("data")
    if isinstance(data, list):
        print("  n:", len(data))
        for it in data[:6]:
            print("   ", {k: it.get(k) for k in ("aqi", "lat", "lon", "station", "uid") if k in it})
    elif isinstance(data, dict):
        print("  aqi", data.get("aqi"), "| idx", data.get("idx"), "|", data.get("city", {}).get("name"))
        fc = data.get("forecast", {}).get("daily", {})
        for k, v in fc.items():
            print("   forecast", k, len(v), v[0] if v else None)
