import pandas as pd, geopandas as gpd, numpy as np
from shapely.geometry import Point
P = r"data/processed/running/v1"
seg = gpd.read_file(P + "/segments.gpkg", layer="segments", columns=["osm_id","fclass","length_m"])
a = pd.read_csv(P + "/segment_air.csv", encoding="utf-8-sig").drop(columns=["length_m"])
m = seg.merge(a, on="osm_id", how="left").to_crs(32650)
c = gpd.GeoSeries([Point(114.2833, 30.5833)], crs=4326).to_crs(32650).iloc[0]  # 江汉路
m["d_center_km"] = m.geometry.centroid.distance(c) / 1000
m = m[(m["length_m"] >= 20) & m["no2_ugm3"].notna()]

grp = {"trunk":"快速路/高架","primary":"主干道","secondary":"次干道","tertiary":"支路",
       "residential":"居住区道路","service":"服务性道路","unclassified":"未分类",
       "footway":"人行道","path":"小径","cycleway":"自行车道","pedestrian":"步行街"}
for lo, hi, tag in [(0,4,"核心区 <4km"), (4,8,"中心区 4-8km"), (8,20,"近郊 8-20km"), (20,999,"远郊 >20km")]:
    s = m[(m.d_center_km>=lo)&(m.d_center_km<hi)].copy()
    s["g"] = s["fclass"].map(grp)
    t = (s.groupby("g").agg(n=("no2_ugm3","size"), no2=("no2_ugm3","median"), km=("length_m", lambda x: x.sum()/1000))
           .query("n >= 200").sort_values("no2", ascending=False))
    print(f"\n== {tag}  (路段 {len(s)}, 中位 NO2 {s['no2_ugm3'].median():.1f})")
    print(t.round(2).to_string())
print("\n全区 NO2 vs 到中心距离 的 Spearman:",
      round(m[["d_center_km","no2_ugm3"]].corr(method="spearman").iloc[0,1], 3))
