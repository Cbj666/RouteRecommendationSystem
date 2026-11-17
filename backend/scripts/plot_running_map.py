# -*- coding: utf-8 -*-
"""Render the running-suitability map for a showcase area (prototype figure).

Shows the scored segments over parks/water/sports facilities — this is the
"map layer" the front-end prototype stands on.

Output: data/output/running/v1/map_donghu.png
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyogrio

matplotlib.use("Agg")
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
RUN = ROOT / "data" / "processed" / "running" / "v1"
V1 = ROOT / "data" / "processed" / "v1"
OUT = ROOT / "data" / "output" / "running" / "v1"
GPKG = RAW / "hubei" / "hubei-261013-free-OpenMap" / "hubei.gpkg"

SHOWCASE = (114.285, 30.495, 114.455, 30.585)   # 东湖 / 珞珈山 / 水果湖
GREEN = {"park", "forest", "grass", "meadow", "scrub", "recreation_ground"}

# 权重与分档线从 score_summary.json 读，页脚不写死，避免和评分口径脱节
_W_FALLBACK = {"safety": 0.36, "green": 0.26, "slope": 0.06,
               "cross": 0.15, "fac": 0.06, "air": 0.11}
_DIM_LABEL = {"safety": "安全", "green": "绿化", "slope": "坡度",
              "cross": "过街", "fac": "设施", "air": "空气"}


def weights_text() -> str:
    """把六维权重排成一行中文，例如「安全 0.36 + 绿化 0.26 + …（合计 1.00）」。"""
    import json
    w = _W_FALLBACK
    try:
        w = json.loads((RUN / "score_summary.json").read_text(encoding="utf-8"))["weights"]
    except Exception:  # noqa: BLE001 - 页脚文本不该因为缺文件而失败
        pass
    parts = [f"{_DIM_LABEL[k]} {float(w[k]):.2f}" for k in
             ("safety", "green", "slope", "cross", "fac", "air")]
    return " + ".join(parts) + f"（合计 {sum(float(v) for v in w.values()):.2f}）"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    import shapely
    # SHOWCASE is lon/lat; the plot is in metres (EPSG:32650)
    west, south, east, north = (
        gpd.GeoSeries([shapely.box(*SHOWCASE)], crs=4326).to_crs(32650).total_bounds
    )

    seg_all = gpd.read_file(RUN / "segments.gpkg", layer="segments").to_crs(32650)
    view = gpd.GeoSeries([shapely.box(*SHOWCASE)], crs=4326).to_crs(32650).iloc[0]
    seg = seg_all[seg_all.intersects(view)].copy()
    land = pyogrio.read_dataframe(GPKG, layer="gis_osm_landuse_a_free", bbox=SHOWCASE).to_crs(32650)
    green = land[land["fclass"].isin(GREEN)]
    water = pyogrio.read_dataframe(GPKG, layer="gis_osm_water_a_free", bbox=SHOWCASE).to_crs(32650)

    amap = pd.read_csv(ROOT / "data" / "processed" / "running" / "v1" / "amap_sport_poi.csv")
    amap = amap[~amap["type"].fillna("").str.contains("台球|棋牌|游戏|歌舞|夜总会|网吧|KTV", regex=True)]
    sport = gpd.GeoDataFrame(
        amap[["name"]].copy(),
        geometry=gpd.GeoSeries(shapely.points(amap["lng"], amap["lat"]), crs=4326),
        crs=4326,
    ).to_crs(32650)
    sport = sport.cx[west:east, south:north]

    # overlay the generated loop for the campus origin (real route, not a mock)
    loop_path = OUT.parent / "v1" / "loops.geojson"
    loops = None
    if loop_path.exists():
        lj = gpd.read_file(loop_path)
        loops = lj[(lj["origin"] == "wuda") & (lj["rank"] == 1)].to_crs(32650)
        print(f"[map] loop overlay: {len(loops)} line(s), {loops['length_m'].iloc[0] if len(loops) else 0:.1f} m")

    fig, ax = plt.subplots(figsize=(13, 10), dpi=170)
    water.plot(ax=ax, color="#cfe3f3", edgecolor="#a9c8e0", linewidth=0.4, zorder=1)
    green.plot(ax=ax, color="#dcecd6", edgecolor="#b7d4ad", linewidth=0.3, zorder=1)

    # colour segments by score; thin lines for minor ways
    order = seg["score"].sort_values().index
    s = seg.loc[order]
    lw = s["fclass"].map(
        {"primary": 2.2, "secondary": 1.9, "tertiary": 1.6, "trunk": 2.4,
         "residential": 1.2, "unclassified": 1.0, "service": 0.9,
         "footway": 1.1, "path": 1.0, "cycleway": 1.4, "pedestrian": 1.2}
    ).fillna(0.9)
    s.plot(
        ax=ax, column="score", cmap="RdYlGn", vmin=25, vmax=70,
        linewidth=lw, zorder=3, legend=False,
    )

    sport.geometry.centroid.plot(ax=ax, markersize=9, color="#7b3294",
                                 alpha=0.65, zorder=4)
    if loops is not None and len(loops):
        loops.plot(ax=ax, color="#111111", linewidth=2.4, zorder=6)

    sm = plt.cm.ScalarMappable(cmap="RdYlGn", norm=plt.Normalize(vmin=25, vmax=70))
    cb = fig.colorbar(sm, ax=ax, fraction=0.028, pad=0.02)
    cb.set_label("慢跑适宜性评分（0–100）", fontsize=11)

    from matplotlib.lines import Line2D

    handles = [
        Line2D([0], [0], color="#7b3294", marker="o", linestyle="none",
               markersize=7, label="运动场馆（高德）"),
        plt.Rectangle((0, 0), 1, 1, color="#dcecd6", label="绿地"),
        plt.Rectangle((0, 0), 1, 1, color="#cfe3f3", label="水体"),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=9, framealpha=0.9)

    ax.set_xlim(west, east)
    ax.set_ylim(south, north)
    ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title("武汉东湖片区：慢跑环境适宜性评价（原型 v0）", fontsize=15, pad=12)
    fig.text(
        0.02, 0.015,
        f"评分 = {weights_text()}   |   "
        "数据：OSM 路网 / SRTM 30 m 坡度 / ESA WorldCover 10 m 树冠 / 高德运动场馆 POI",
        fontsize=8.5, color="#555555",
    )
    target = OUT / "map_donghu.png"
    fig.savefig(target, bbox_inches="tight")
    print("wrote", target.relative_to(ROOT))

    # --- clean map layer for the UI prototype: no title / axes / colorbar ---
    ax.set_title(""); ax.set_xlabel(""); ax.set_ylabel("")
    ax.set_axis_off()
    cb.remove()
    ax.get_legend().remove()
    for txt in list(fig.texts):
        txt.remove()
    fig.set_size_inches(12, 9)
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    layer = OUT / "map_layer.png"
    fig.savefig(layer, bbox_inches="tight", pad_inches=0, facecolor="#f4f7f6")
    print("wrote", layer.relative_to(ROOT))
    print(f"segments in view: {len(seg)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
