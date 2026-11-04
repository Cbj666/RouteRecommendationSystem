import json, urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8123"
MOCKS = Path("frontend/app/src/mocks")
MOCKS.mkdir(parents=True, exist_ok=True)

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))

def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))

def dump(name, obj):
    p = MOCKS / name
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{name:26s} {p.stat().st_size/1024:7.1f} KB")

dump("health.json", get("/health"))
dump("meta.json", get("/api/meta"))
dump("segments.json", get("/api/segments?min_lng=114.352&min_lat=30.530&max_lng=114.366&max_lat=30.540&limit=1200"))
dump("facilities.json", get("/api/facilities?min_lng=114.330&min_lat=30.515&max_lng=114.400&max_lat=30.570&kinds=all"))
dump("loops.json", post("/api/loops", {"lng": 114.3547, "lat": 30.5342, "target_m": 5000,
                                      "prefs": {"green": 1.0, "safe": 1.0, "flat": 0.6}}))
