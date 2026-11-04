"""按到城市中心的距离分圈，统计 NO2（整体 + 分道路等级），供出图使用。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed" / "running" / "v1"
OUT = ROOT / "data" / "output" / "running" / "v1" / "demo"
OUT.mkdir(parents=True, exist_ok=True)

CENTER = (114.2833, 30.5833)   # 江汉路
BINS = [(0, 2), (2, 4), (4, 6), (6, 8), (8, 12), (12, 20), (20, 40), (40, 1e9)]
LABELS = ["<2", "2–4", "4–6", "6–8", "8–12", "12–20", "20–40", ">40"]
GRP = {"trunk": "trunk", "primary": "primary", "secondary": "secondary",
       "tertiary": "tertiary", "residential": "residential", "service": "service",
       "unclassified": "unclassified", "footway": "footway", "path": "path",
       "cycleway": "cycleway", "pedestrian": "pedestrian"}


def main():
    seg = gpd.read_file(PROC / "segments.gpkg", layer="segments",
                        columns=["osm_id", "fclass", "length_m"])
    air = pd.read_csv(PROC / "segment_air.csv", encoding="utf-8-sig").drop(columns=["length_m"])
    m = seg.merge(air, on="osm_id", how="left").to_crs(32650)
    c = gpd.GeoSeries([Point(*CENTER)], crs=4326).to_crs(32650).iloc[0]
    m["d_km"] = m.geometry.centroid.distance(c) / 1000.0
    m = m[(m["length_m"] >= 20) & m["no2_ugm3"].notna()].copy()
    m["g"] = m["fclass"].map(GRP).fillna("other")

    edges = [0] + [hi for _, hi in BINS]
    m["ring"] = pd.cut(m["d_km"], bins=[-np.inf] + [hi for _, hi in BINS], labels=LABELS)

    allr = (m.groupby("ring", observed=True)
              .agg(n=("no2_ugm3", "size"),
                   km=("length_m", lambda s: s.sum() / 1000),
                   no2=("no2_ugm3", "median"),
                   pm25=("pm25_ugm3", "median"))
              .reset_index())
    allr.to_csv(OUT / "_ring_all.csv", index=False, encoding="utf-8-sig")

    byc = (m.groupby(["ring", "g"], observed=True)
             .agg(n=("no2_ugm3", "size"), no2=("no2_ugm3", "median"),
                  km=("length_m", lambda s: s.sum() / 1000))
             .reset_index())
    byc.to_csv(OUT / "_ring_class.csv", index=False, encoding="utf-8-sig")

    print(allr.round(2).to_string(index=False))
    print("\n区内极差（主干道 vs 人行道）:")
    for r in LABELS:
        s = byc[(byc["ring"] == r) & byc["g"].isin(["trunk", "primary", "residential", "footway"])]
        s = s[s["n"] >= 200]
        if len(s) >= 2:
            print(f"  {r:>6}: {s['no2'].min():.2f} – {s['no2'].max():.2f}  "
                  f"（{s['g'].tolist()}）")
    rho = m[["d_km", "no2_ugm3"]].corr(method="spearman").iloc[0, 1]
    print(f"\nSpearman(到中心距离, NO2) = {rho:.3f}")


if __name__ == "__main__":
    main()
