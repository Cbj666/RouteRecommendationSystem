# -*- coding: utf-8 -*-
"""Crawl Amap POIs for sports facilities across Wuhan (grid + pagination).

Why: official citywide fitness-facility data is not downloadable (the only
open registry, Jiang'an district, requires a registered high-security system).
OSM covers 2,608 pitches citywide and is thin in the suburbs; Amap's
"体育休闲服务;运动场馆" (typecode 080100) is far denser.

Method
    * 0.06 deg grid (~6.2 km cells) over the Wuhan boundary,
    * place/around with radius 4500 m so neighbouring cells overlap,
    * 25 results per page, paginate until a short page,
    * every raw response is cached, so a rerun costs no quota.

Quota: a few hundred to ~1,500 calls; `place/*` allows 5,000/day.

Output
    data/processed/running/v1/amap_sport_poi.csv   (WGS84 + GCJ-02)
    data/cache/amap_sport/<cell>_<page>.json       (raw responses)
"""
from __future__ import annotations

import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/ for `app`
from app.secrets import require as require_secret  # noqa: E402
from geo_utils import gcj02_to_wgs84  # noqa: E402

BOUNDARY = ROOT / "data" / "raw" / "boundary" / "武汉市_市.geojson"
CACHE = ROOT / "data" / "cache" / "amap_sport"
OUT = ROOT / "data" / "processed" / "running" / "v1"
CELL_DEG = 0.06
RADIUS_M = 4500
TYPES = "080100"          # 体育休闲服务 > 运动场馆
MAX_PAGE = 40
SLEEP_S = 0.45


def load_key() -> str:
    """高德 Web 服务 Key：环境变量优先，其次项目根 .env（见 app/secrets.py）。"""
    return require_secret(
        "AMAP_WEB_KEY",
        "GAODE_KEY",
        "AMAP_KEY",
        hint="https://lbs.amap.com/ 控制台 → 应用管理 → Web 服务 Key",
    )


def query(key: str, lon: float, lat: float, page: int) -> dict:
    params = {
        "key": key,
        "types": TYPES,
        "location": f"{lon:.6f},{lat:.6f}",
        "radius": str(RADIUS_M),
        "offset": "25",
        "page": str(page),
        "extensions": "base",
    }
    url = "https://restapi.amap.com/v3/place/around?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)


def main() -> int:
    key = load_key()
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    boundary = gpd.read_file(BOUNDARY).to_crs(4326)
    geom = boundary.geometry.union_all()
    minx, miny, maxx, maxy = boundary.total_bounds

    cells = []
    lat = miny
    while lat < maxy:
        lon = minx
        while lon < maxx:
            box = shapely.box(lon, lat, min(lon + CELL_DEG, maxx), min(lat + CELL_DEG, maxy))
            if box.intersects(geom):
                cells.append((round(lon + CELL_DEG / 2, 5), round(lat + CELL_DEG / 2, 5)))
            lon += CELL_DEG
        lat += CELL_DEG
    print(f"[amap] {len(cells)} cells inside Wuhan boundary", flush=True)

    pois: dict[str, dict] = {}
    calls = 0
    cached = 0
    t0 = time.time()
    for i, (lon, lat) in enumerate(cells, 1):
        for page in range(1, MAX_PAGE + 1):
            cf = CACHE / f"{lon:.5f}_{lat:.5f}_p{page}.json"
            data = None
            if cf.exists():
                cached_data = json.loads(cf.read_text(encoding="utf-8"))
                if str(cached_data.get("status")) == "1":
                    data = cached_data
                    cached += 1
                else:
                    cf.unlink()          # failed response: drop and retry
            else:
                data = None
                for attempt in range(5):
                    try:
                        data = query(key, lon, lat, page)
                    except Exception as exc:  # noqa: BLE001
                        print(f"[amap] cell {lon},{lat} p{page} failed: {exc}", flush=True)
                        time.sleep(2.0 * (attempt + 1))
                        continue
                    calls += 1
                    time.sleep(SLEEP_S)
                    if str(data.get("status")) == "1":
                        break
                    info = str(data.get("info"))
                    if "CUQPS" in info:          # rate limit: back off and retry
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    break
                if data is None:
                    break
                cf.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            status = str(data.get("status"))
            if status != "1":
                info = data.get("info")
                print(f"[amap] status={status} info={info} at cell {lon},{lat} p{page}", flush=True)
                if "INSUFFICIENT_PRIVILEGES" in str(info).upper() or "DAILY" in str(info).upper():
                    print("[amap] daily quota exhausted, stopping", flush=True)
                    page = MAX_PAGE
                break
            rows = data.get("pois") or []
            for r in rows:
                pid = r.get("id")
                if pid and pid not in pois:
                    pois[pid] = r
            if len(rows) < 25:
                break
        if i % 50 == 0:
            print(f"[amap] {i}/{len(cells)} cells, {len(pois):,} pois, "
                  f"calls={calls} cached={cached}, {time.time() - t0:.0f}s", flush=True)

    print(f"[amap] done: {len(pois):,} unique POIs, {calls} live calls, {cached} cached", flush=True)
    if not pois:
        return 1

    recs = []
    for r in pois.values():
        loc = r.get("location") or ","
        try:
            glon, glat = (float(v) for v in loc.split(","))
        except ValueError:
            continue
        wlon, wlat = gcj02_to_wgs84(glon, glat)
        recs.append(
            {
                "poi_id": r.get("id"),
                "name": r.get("name"),
                "type": r.get("type"),
                "typecode": r.get("typecode"),
                "lng_gcj02": glon,
                "lat_gcj02": glat,
                "lng": wlon,
                "lat": wlat,
                "address": r.get("address"),
                "adname": r.get("adname"),
                "adcode": r.get("adcode"),
                "tel": r.get("tel"),
            }
        )
    df = pd.DataFrame(recs)
    df["in_boundary"] = gpd.GeoSeries(
        shapely.points(df["lng"], df["lat"]), crs=4326
    ).within(geom)
    df = df.sort_values(["adname", "name"]).reset_index(drop=True)
    target = OUT / "amap_sport_poi.csv"
    df.to_csv(target, index=False, encoding="utf-8-sig")
    print(f"[amap] {len(df):,} POIs ({int(df['in_boundary'].sum()):,} in boundary) -> {target}")
    print("[amap] top types:")
    print(df["type"].value_counts().head(10).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
