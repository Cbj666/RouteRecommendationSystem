import geopandas as gpd, pandas as pd, numpy as np
from shapely.geometry import Point

st = pd.read_csv(r"data/processed/running/v1/air_quality_stations.csv", encoding="utf-8-sig")
wuhan = st[st["in_boundary"]]
pts = gpd.GeoDataFrame(wuhan, geometry=[Point(xy) for xy in zip(wuhan["lon"], wuhan["lat"])], crs=4326).to_crs(32650)
print("武汉站数:", len(pts), "| AQI:", pts["aqi"].min(), "~", pts["aqi"].max(), "中位", pts["aqi"].median())

seg = gpd.read_file(r"data/processed/running/v1/segments.gpkg", layer="segments")[["length_m", "score", "geometry"]].to_crs(32650)
print("路段:", len(seg), "总长 km:", round(seg["length_m"].sum() / 1000, 1))
mid = seg.geometry.interpolate(0.5, normalized=True)

for r in (1000, 2000, 3000, 5000):
    d = mid.apply(lambda g: pts.distance(g).min())
    inside = d <= r
    print(f"  中点距最近站 <= {r/1000:.0f} km: {inside.mean()*100:5.1f}% 路段 / {seg.loc[inside, 'length_m'].sum()/seg['length_m'].sum()*100:5.1f}% 路长")

d = mid.apply(lambda g: pts.distance(g).min())
print("  距离 p50/p90/p99 (km): %.2f / %.2f / %.2f" % (d.quantile(.5)/1000, d.quantile(.9)/1000, d.quantile(.99)/1000))
