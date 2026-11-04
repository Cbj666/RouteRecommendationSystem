import geopandas as gpd, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.cm import ScalarMappable
from shapely.geometry import Point, box

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

st = pd.read_csv(r"data/processed/running/v1/air_quality_stations.csv", encoding="utf-8-sig")
w = st[st["in_boundary"]].reset_index(drop=True)
seg = gpd.read_file(r"data/processed/running/v1/segments.gpkg", layer="segments").to_crs(32650)
clip = gpd.GeoDataFrame(geometry=[box(w["lon"].min()-0.055, w["lat"].min()-0.035,
                                      w["lon"].max()+0.055, w["lat"].max()+0.035)], crs=4326).to_crs(32650).geometry.iloc[0]
seg = seg[seg.intersects(clip)]

fig, ax = plt.subplots(figsize=(9.2, 9.2), dpi=200)
seg.plot(ax=ax, color="#e2e2e2", linewidth=0.25, zorder=1)
seg[seg["score"] >= 55].plot(ax=ax, color="#8ec9a6", linewidth=0.35, zorder=2)
cmap = LinearSegmentedColormap.from_list("aqi", ["#1a9850", "#fee08b", "#fc8d59", "#d73027"])
norm = Normalize(vmin=60, vmax=120)
pts = gpd.GeoDataFrame(w, geometry=[Point(xy) for xy in zip(w["lon"], w["lat"])], crs=4326).to_crs(32650)
pts.buffer(3000).boundary.plot(ax=ax, color="#c8c8c8", linewidth=0.6, linestyle=(0, (3, 3)), zorder=3)
pts.plot(ax=ax, color=[cmap(norm(v)) for v in pts["aqi"]], markersize=120,
         edgecolor="#444", linewidth=0.8, zorder=5)

OFF = {906: (-12, 16), 1529: (16, -2), 910: (16, 14), 907: (-12, -14), 905: (-12, 10),
       10442: (14, -12), 904: (14, -6), 908: (14, 10), 909: (14, -8), 912: (-14, 8)}
ALIGN = {906: "right", 907: "right", 905: "right", 912: "right"}
for _, r in pts.iterrows():
    uid = int(r["uid"])
    nm = r["name"].split("(")[-1].rstrip(")") if "(" in r["name"] else r["name"]
    if uid == 1529:
        nm = "武汉（城市站）"
    dx, dy = OFF.get(uid, (12, 10))
    ax.annotate(f"{nm} · {int(r['aqi'])}", (r.geometry.x, r.geometry.y), xytext=(dx, dy),
                textcoords="offset points", fontsize=8, color="#222",
                ha="right" if ALIGN.get(uid) == "right" else "left", va="center", zorder=6,
                bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="#dddddd", lw=0.5, alpha=0.92))

cb = fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=ax, shrink=0.45, pad=0.01)
cb.set_label("AQI（AQICN，US EPA 口径）", fontsize=8.5)
cb.ax.tick_params(labelsize=7.5)
ax.set_title("武汉 10 个空气质量监测点（AQICN，2026-10-29 19:00）\n底图：慢跑适宜性路网；绿＝≥55 分路段；虚线＝站点 3 km 缓冲", fontsize=11)
ax.set_axis_off()
fig.tight_layout()
fig.savefig(r"data/output/running/v1/air_quality_stations.png", bbox_inches="tight", facecolor="white")
print("saved")
