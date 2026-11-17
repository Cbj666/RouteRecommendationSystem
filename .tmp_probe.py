# -*- coding: utf-8 -*-
import gzip
import json
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd

RUN = Path("data/processed/running/v1")
WEB = Path("data/output/running/v1/web")

t0 = time.perf_counter()
gdf = gpd.read_file(RUN / "segments.gpkg", layer="segments")
print(f"segments read: {time.perf_counter() - t0:.2f}s rows={len(gdf)} crs={gdf.crs}")
print("columns:", list(gdf.columns))
print(gdf.dtypes.to_string())
print("bounds:", [round(x, 6) for x in gdf.total_bounds])
print("null counts:", gdf.isna().sum().to_dict())
print("sample:", gdf.iloc[0].drop("geometry").to_dict())
print("geom types:", gdf.geom_type.value_counts().to_dict())
print("valid:", bool(gdf.geometry.is_valid.all()))

t0 = time.perf_counter()
sub = gdf.cx[114.30:114.42, 30.50:30.58]
print(f"cx city bbox: {time.perf_counter() - t0:.3f}s rows={len(sub)}")

t0 = time.perf_counter()
js = sub.to_json(drop_id=True)
print(f"to_json {len(sub)}: {time.perf_counter() - t0:.3f}s chars={len(js):,} gzip={len(gzip.compress(js.encode())):,}")

t0 = time.perf_counter()
obj = json.loads(js)
print(f"json.loads: {time.perf_counter() - t0:.3f}s")
print("first props:", obj["features"][0]["properties"])

for tol in (0.0001, 0.0002):
    t0 = time.perf_counter()
    simp = sub.copy()
    simp["geometry"] = simp.geometry.simplify(tol, preserve_topology=True)
    js2 = simp.to_json(drop_id=True)
    print(f"simplify {tol}: {time.perf_counter() - t0:.3f}s chars={len(js2):,} gzip={len(gzip.compress(js2.encode())):,}")

t0 = time.perf_counter()
wg = gpd.read_file(WEB / "water_green.geojson")
print(f"water read: {time.perf_counter() - t0:.2f}s rows={len(wg)} crs={wg.crs}")
print("wg columns:", list(wg.columns), wg["kind"].value_counts().to_dict())
print("wg bounds:", [round(x, 6) for x in wg.total_bounds])
print("wg geom types:", wg.geom_type.value_counts().to_dict())
t0 = time.perf_counter()
wjs = wg.to_json(drop_id=True)
print(f"wg to_json: {time.perf_counter() - t0:.3f}s chars={len(wjs):,} gzip={len(gzip.compress(wjs.encode())):,}")

t0 = time.perf_counter()
poi = pd.read_csv(RUN / "amap_sport_poi.csv", encoding="utf-8-sig")
print(f"poi read: {time.perf_counter() - t0:.3f}s rows={len(poi)}")
print("poi columns:", list(poi.columns))
print("poi null:", poi.isna().sum().to_dict())
print("in_boundary:", poi["in_boundary"].value_counts().to_dict())
print("adname:", poi["adname"].value_counts().head(8).to_dict())
pat = "台球|棋牌|游戏|歌舞|夜总会|网吧|KTV"
drop = poi["type"].fillna("").str.contains(pat, regex=True)
print("excluded:", int(drop.sum()), "kept:", int((~drop).sum()))
print("poi bounds:", [round(poi.lng.min(), 6), round(poi.lat.min(), 6), round(poi.lng.max(), 6), round(poi.lat.max(), 6)])
print("types head:", poi["type"].value_counts().head(10).to_dict())
