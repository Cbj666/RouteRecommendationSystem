"""生成前端原型用的地图底图（1600×1000，白绿配色）。

图层：浅底 → 绿地（OSM 面，不透明） → 水体（OSM 面/线，不透明）
      → 评分路网 → 环线。

绿地全部用多边形，不用栅格，边缘才是清楚的。
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import running  # noqa: E402

OUT = ROOT / "build" / "proto"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]

LNG0, LAT0, LNG1, LAT1 = 114.305, 30.508, 114.405, 30.562
SRC = ROOT / "data" / "raw" / "hubei" / "hubei-261013-free-OpenMap" / "hubei.gpkg"

BG = "#F5F8F2"
WATER = "#B3D4E6"
GREEN_DARK = "#9FC49B"   # 林地
GREEN_LIGHT = "#CFE3BE"  # 草地 / 公园

GREEN_DARK_CLASSES = {"forest", "scrub"}
GREEN_LIGHT_CLASSES = {"park", "grass", "meadow", "recreation_ground"}


def _layer(name: str, clip_m: gpd.GeoDataFrame) -> gpd.GeoDataFrame | None:
    try:
        g = gpd.read_file(SRC, layer=name, bbox=(LNG0, LAT0, LNG1, LAT1)).to_crs(32650)
    except Exception as exc:  # noqa: BLE001
        print("skip", name, exc)
        return None
    if g.empty:
        return None
    return gpd.clip(g, clip_m)


def draw_green(ax, clip_m: gpd.GeoDataFrame) -> None:
    land = _layer("gis_osm_landuse_a_free", clip_m)
    if land is None:
        return
    light = land[land["fclass"].isin(GREEN_LIGHT_CLASSES)]
    dark = land[land["fclass"].isin(GREEN_DARK_CLASSES)]
    if not light.empty:
        light.plot(ax=ax, color=GREEN_LIGHT, edgecolor="none", zorder=2)
    if not dark.empty:
        dark.plot(ax=ax, color=GREEN_DARK, edgecolor="none", zorder=3)


def draw_water(ax, clip_m: gpd.GeoDataFrame) -> None:
    for name, lw in (("gis_osm_water_a_free", None), ("gis_osm_waterways_free", 6.0)):
        g = _layer(name, clip_m)
        if g is None:
            continue
        if lw is None:
            g.plot(ax=ax, color=WATER, edgecolor="none", zorder=4)
        else:
            g.plot(ax=ax, color=WATER, linewidth=lw, zorder=4)


def main() -> None:
    seg = gpd.read_file(ROOT / "data" / "processed" / "running" / "v1" / "segments.gpkg",
                        layer="segments").to_crs(32650)
    clip = gpd.GeoDataFrame(geometry=[box(LNG0, LAT0, LNG1, LAT1)], crs=4326)
    clip_m = clip.to_crs(32650)
    seg = gpd.clip(seg, clip_m)

    fig = plt.figure(figsize=(16, 10), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG)

    x0, y0, x1, y1 = clip_m.total_bounds
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")

    plain = "--plain" in sys.argv
    if not plain:
        draw_green(ax, clip_m)
        draw_water(ax, clip_m)

    sc = seg["score"].to_numpy()
    cmap = LinearSegmentedColormap.from_list(
        "s", ["#D94F4F", "#E8A33D", "#8FBF6A", "#2E7A5D", "#15503C"]
    )
    colors = cmap(np.clip((sc - 30) / 42, 0, 1))
    segs = [np.asarray(g.coords) for g in seg.geometry if g.geom_type == "LineString"]
    ax.add_collection(LineCollection(segs, colors=colors, linewidths=0.9, alpha=0.95, zorder=5))

    g = running.load_or_build()
    loops = running.generate_loops(g, 114.3547, 30.5342, 5000,
                                   prefs={"green": 1.0, "safe": 1.0, "flat": 0.6},
                                   max_candidates=8)
    best = loops[0]
    nodes = best["nodes"]
    pts = [np.column_stack([g.x[nodes], g.y[nodes]])]
    ax.add_collection(LineCollection(pts, colors="#FFFFFF", linewidth=6.6, alpha=0.95, zorder=6))
    ax.add_collection(LineCollection(pts, colors="#141414", linewidth=3.8, zorder=7))

    ax.set_axis_off()
    fig.savefig(OUT / "map_base.png", dpi=100, facecolor=BG)
    print("map", OUT / "map_base.png", best["length_m"], round(best["score"], 1))


if __name__ == "__main__":
    main()
