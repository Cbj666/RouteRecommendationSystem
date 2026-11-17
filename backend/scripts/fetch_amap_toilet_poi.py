# -*- coding: utf-8 -*-
"""Crawl Amap public toilets (公共厕所) across Wuhan with keyword search.

Why: the facility dimension (s_fac, weight 0.05) currently only knows sports
venues plus a thin OSM support-POI set, so it is ~constant citywide.  Public
toilets are the canonical "running support" facility — every 500 m of a good
riverside route has one — and Amap's category 200300 is dense and city-managed.

Method
    * keyword search (`place/around` + ``keywords``) instead of a bare typecode:
      the keyword also catches toilets whose POI *type* is not 200300 but whose
      name says 公厕/卫生间 (park, mall, metro-station toilets).
    * 0.06 deg grid (~6.2 km cells) over the Wuhan boundary, radius 4500 m so
      neighbouring cells overlap and every point is covered (diagonal/2 ≈ 4.4 km).
    * 25 results per page, paginate until a short page.
    * every raw response is cached under data/cache/amap_toilet/, so reruns and
      a resumed crawl cost no quota.

Quota
    `place/*` allows 5,000 calls/day at <=3 QPS.  One page = 25 POIs, so the
    daily budget is ~125k POIs, not 5k.  ``--max-calls`` (default 4600) is a
    safety stop; it also stops cleanly on DAILY_QUERY_OVER_LIMIT.

Output
    data/processed/running/v1/amap_toilet_poi.csv   (WGS84 + GCJ-02)
    data/cache/amap_toilet/<lon>_<lat>_p<page>.json (raw responses)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo_utils import gcj02_to_wgs84  # noqa: E402

BOUNDARY = ROOT / "data" / "raw" / "boundary" / "武汉市_市.geojson"
CACHE = ROOT / "data" / "cache" / "amap_toilet"
OUT = ROOT / "data" / "processed" / "running" / "v1"
CELL_DEG = 0.06
RADIUS_M = 4500
KEYWORDS = "公共厕所|公厕|厕所|卫生间|洗手间"
MAX_PAGE = 40
SLEEP_S = 0.42          # >= 1/3 s, Amap allows 3 QPS
DAILY_MARKERS = ("DAILY_QUERY_OVER_LIMIT", "INSUFFICIENT_PRIVILEGES", "USER_DAILY_QUERY_OVER_LIMIT")


def load_key() -> str:
    for name in (".env", ".env.txt"):
        p = ROOT / name
        if not p.exists():
            continue
        m = re.search(r"GAODE_KEY\s*=\s*(\S+)", p.read_text(encoding="utf-8", errors="ignore"))
        if m:
            return m.group(1).strip()
    raise RuntimeError("GAODE_KEY not found in .env")


def query(key: str, lon: float, lat: float, page: int) -> dict:
    params = {
        "key": key,
        "keywords": KEYWORDS,
        "location": f"{lon:.6f},{lat:.6f}",
        "radius": str(RADIUS_M),
        "offset": "25",
        "page": str(page),
        "extensions": "base",
    }
    url = "https://restapi.amap.com/v3/place/around?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)


def build_cells(geom, bounds) -> list[tuple[float, float]]:
    minx, miny, maxx, maxy = bounds
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
    return cells


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-calls", type=int, default=4600, help="hard cap on live API calls")
    ap.add_argument("--max-cells", type=int, default=0, help="pilot: only the first N cells")
    args = ap.parse_args()

    key = load_key()
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    boundary = gpd.read_file(BOUNDARY).to_crs(4326)
    geom = boundary.geometry.union_all()
    cells = build_cells(geom, boundary.total_bounds)
    if args.max_cells:
        cells = cells[: args.max_cells]
    print(f"[toilet] {len(cells)} cells inside Wuhan boundary", flush=True)

    pois: dict[str, dict] = {}
    calls = cached = 0
    t0 = time.time()
    exhausted = False
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
            if data is None:
                for attempt in range(5):
                    if calls >= args.max_calls:
                        exhausted = True
                        break
                    try:
                        data = query(key, lon, lat, page)
                    except Exception as exc:  # noqa: BLE001
                        print(f"[toilet] cell {lon},{lat} p{page} failed: {exc}", flush=True)
                        time.sleep(2.0 * (attempt + 1))
                        continue
                    calls += 1
                    time.sleep(SLEEP_S)
                    if str(data.get("status")) == "1":
                        break
                    info = str(data.get("info")).upper()
                    if "CUQPS" in info:          # rate limit: back off and retry
                        time.sleep(1.5 * (attempt + 1))
                        data = None
                        continue
                    if any(m in info for m in DAILY_MARKERS):
                        exhausted = True
                    break
                if data is None:
                    break
                cf.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            if exhausted and data is None:
                break

            status = str(data.get("status"))
            if status != "1":
                info = str(data.get("info"))
                print(f"[toilet] status={status} info={info} at cell {lon},{lat} p{page}", flush=True)
                if any(m in info.upper() for m in DAILY_MARKERS):
                    print("[toilet] daily quota exhausted, stopping", flush=True)
                    exhausted = True
                break
            rows = data.get("pois") or []
            for r in rows:
                pid = r.get("id")
                if pid and pid not in pois:
                    pois[pid] = r
            if len(rows) < 25:
                break
        if exhausted:
            print(f"[toilet] stopping after {i}/{len(cells)} cells (quota/call cap)", flush=True)
            break
        if i % 20 == 0:
            print(f"[toilet] {i}/{len(cells)} cells, {len(pois):,} pois, "
                  f"calls={calls} cached={cached}, {time.time() - t0:.0f}s", flush=True)

    print(f"[toilet] done: {len(pois):,} unique POIs, {calls} live calls, {cached} cached", flush=True)
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
    df = pd.DataFrame(recs).drop_duplicates("poi_id")
    df["in_boundary"] = gpd.GeoSeries(shapely.points(df["lng"], df["lat"]), crs=4326).within(geom)
    df = df.sort_values(["adname", "name"]).reset_index(drop=True)
    target = OUT / "amap_toilet_poi.csv"
    df.to_csv(target, index=False, encoding="utf-8-sig")
    inside = df[df["in_boundary"]]
    print(f"[toilet] {len(df):,} POIs ({len(inside):,} in boundary) -> {target}")
    print("[toilet] by district:\n" + inside["adname"].value_counts().head(15).to_string())
    print("[toilet] by typecode:\n" + inside["typecode"].value_counts().head(10).to_string())
    print("[toilet] by main type:\n" +
          inside["type"].fillna("").str.split(";").str[1].value_counts().head(10).to_string())
    print("[toilet] name ends with:", Counter(
        ("公共厕所" if "公共厕所" in n else "公厕" if "公厕" in n else
         "卫生间" if "卫生间" in n else "洗手间" if "洗手间" in n else "其他")
        for n in inside["name"].fillna("")
    ).most_common())
    return 0


if __name__ == "__main__":
    sys.exit(main())
