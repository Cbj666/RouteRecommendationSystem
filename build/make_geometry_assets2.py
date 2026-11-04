"""追加素材：行政区（逐区 + 合并）、水系（面/线）、六边形热力斑块。

输出仍到 presentation/素材/，D/E/F 三套，透明底 PNG。
运行：
    .\\.venv\\Scripts\\python.exe build\\make_geometry_assets2.py
"""

from __future__ import annotations

import math
import pathlib

import geopandas as gpd
import shapely.affinity
import matplotlib
import numpy as np
import pandas as pd
from shapely.geometry import Point, Polygon, box

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "presentation" / "素材"
OUT.mkdir(parents=True, exist_ok=True)

PRIMARY = "#15503C"
ROCK = "#7FA894"
PALE = "#D9E8DF"
BLUE = "#2F6E8F"
BLUE_PALE = "#CFE0E8"

CANVAS_W = 1800
DPI = CANVAS_W / 9.0
SRC = ROOT / "data" / "raw" / "hubei" / "hubei-261013-free-OpenMap" / "hubei.gpkg"
BBOX = (113.6, 29.9, 115.2, 31.45)


def make_canvas(ext):
    x0, x1, y0, y1 = ext
    aspect = (y1 - y0) / (x1 - x0)
    fig = plt.figure(figsize=(9.0, 9.0 * aspect))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_axis_off()
    return fig, ax


def save(fig, name, transparent=True):
    fig.savefig(OUT / name, dpi=DPI, transparent=transparent,
                facecolor="none" if transparent else "white", pad_inches=0)
    plt.close(fig)
    print(f"  {name}")


def km(gdf):
    return gdf.set_geometry(gdf.geometry.scale(0.001, 0.001, origin=(0, 0)))


def main():
    boundary = gpd.read_file(ROOT / "data" / "processed" / "v1" / "wuhan_boundary.geojson").to_crs(32650)
    city = boundary.union_all()
    bx0, by0, bx1, by1 = boundary.total_bounds
    pad = 1500.0
    ext_a = ((bx0 - pad) / 1000, (bx1 + pad) / 1000, (by0 - pad) / 1000, (by1 + pad) / 1000)

    # ---------------------------------------------------------------- D 行政区
    print("[素材] 行政区")
    adm = gpd.read_file(SRC, layer="gis_osm_adminareas_a_free", bbox=BBOX).to_crs(32650)
    adm = adm[adm["fclass"] == "admin_level6"].copy()
    adm = adm[adm.geometry.centroid.within(city)]
    districts = gpd.GeoDataFrame(adm[["name"]].copy(), geometry=adm.geometry, crs=32650)
    districts = districts[~districts.geometry.is_empty].sort_values("name").reset_index(drop=True)
    districts["area_km2"] = (districts.geometry.area / 1e6).round(0)
    print("       ", len(districts), "个区", [n for n in districts["name"].head(4)])

    dkm = km(districts)
    fig, ax = make_canvas(ext_a)
    dkm.plot(ax=ax, facecolor=PRIMARY, edgecolor="white", linewidth=1.8, alpha=0.35)
    city_km = gpd.GeoDataFrame(geometry=[shapely.affinity.scale(city, xfact=0.001, yfact=0.001, origin=(0, 0))], crs=32650)
    city_km.boundary.plot(ax=ax, color=PRIMARY, linewidth=2.2)
    save(fig, "D1_分区_合并.png")

    for _, row in districts.iterrows():
        safe = str(row["name"]).replace("（", "_").replace("）", "").replace("(", "_").replace(")", "")
        dx0, dy0, dx1, dy1 = row.geometry.bounds
        ex = ((dx0 - 1500) / 1000, (dx1 + 1500) / 1000, (dy0 - 1500) / 1000, (dy1 + 1500) / 1000)
        fig, ax = make_canvas(ex)
        one = gpd.GeoDataFrame([row], geometry="geometry", crs=32650)
        one_km = one.set_geometry(one.geometry.scale(0.001, 0.001, origin=(0, 0)))
        one_km.plot(ax=ax, facecolor=PRIMARY, edgecolor=PRIMARY, linewidth=2.0, alpha=0.20)
        save(fig, f"D2_分区_{safe}.png")

    # ---------------------------------------------------------------- E 水系
    print("[素材] 水系")
    water = gpd.read_file(SRC, layer="gis_osm_water_a_free", bbox=BBOX).to_crs(32650)
    water = water[water.geometry.intersects(city)]
    water = water.copy()
    water["geometry"] = water.geometry.intersection(city)
    water = water[~water.geometry.is_empty]
    ways = gpd.read_file(SRC, layer="gis_osm_waterways_free", bbox=BBOX).to_crs(32650)
    ways = ways[ways.geometry.intersects(city)]
    ways = ways.copy()
    ways["geometry"] = ways.geometry.intersection(city)
    ways = ways[~ways.geometry.is_empty]
    print(f"        面 {len(water)} 个 / 线 {len(ways)} 条")

    wkm, ways_km = km(water), km(ways)

    fig, ax = make_canvas(ext_a)
    wkm.plot(ax=ax, color=BLUE_PALE, edgecolor="none")
    ways_km.plot(ax=ax, color=BLUE, linewidth=0.5, alpha=0.9)
    save(fig, "E1_水系_面与线.png")

    fig, ax = make_canvas(ext_a)
    wkm.plot(ax=ax, facecolor="none", edgecolor=BLUE, linewidth=0.7)
    ways_km.plot(ax=ax, color=BLUE, linewidth=0.45, alpha=0.85)
    save(fig, "E2_水系_仅轮廓.png")

    seg = gpd.read_file(ROOT / "data" / "processed" / "running" / "v1" / "segments.gpkg",
                        layer="segments").to_crs(32650)
    seg = seg[seg.intersects(box(*ext_a_utm(ext_a)))]
    seg_km = km(seg)
    fig, ax = make_canvas(ext_a)
    wkm.plot(ax=ax, color=BLUE_PALE, edgecolor="none", zorder=1)
    seg_km.plot(ax=ax, color=ROCK, linewidth=0.24, alpha=0.8, zorder=2)
    ways_km.plot(ax=ax, color=BLUE, linewidth=0.5, alpha=0.9, zorder=3)
    save(fig, "E3_水系加路网.png")

    # ---------------------------------------------------------------- F 六边形热力
    print("[素材] 六边形热力")
    hot = pd.read_csv(ROOT / "data" / "output" / "running" / "v1" / "demo" / "hotspots.csv",
                      encoding="utf-8-sig")
    pts = gpd.GeoDataFrame(
        hot, geometry=[Point(x, y) for x, y in zip(hot["lng"], hot["lat"])], crs=4326
    ).to_crs(32650)
    px, py, pv = pts.geometry.x.to_numpy(), pts.geometry.y.to_numpy(), pts["top3"].to_numpy()

    r = 1400.0         # 六边形外接圆半径（米）
    dx, dy = 1.5 * r, math.sqrt(3) * r
    x0h, y0h = px.min() - 6000, py.min() - 6000
    x1h, y1h = px.max() + 6000, py.max() + 6000
    rows, cols = int((y1h - y0h) / dy) + 2, int((x1h - x0h) / dx) + 2
    cells = []
    for j in range(rows):
        for i in range(cols):
            cx = x0h + i * dx + (dx / 2 if j % 2 else 0)
            cy = y0h + j * dy
            if not city.contains(Point(cx, cy)):
                continue
            d2 = (px - cx) ** 2 + (py - cy) ** 2
            near = d2 <= (9000.0 ** 2)
            if not near.any():
                continue
            w = 1.0 / np.power(np.sqrt(d2[near]), 2.0)
            val = float(np.sum(w * pv[near]) / np.sum(w))
            cells.append((cx, cy, val, math.sqrt(d2.min())))
    print(f"        {len(cells)} 个六边形格（半径 1400 m）")

    cells_gdf = gpd.GeoDataFrame(
        {"v": [c[2] for c in cells]},
        geometry=[
            Polygon([(cx + r * math.cos(math.pi / 3 * k), cy + r * math.sin(math.pi / 3 * k))
                     for k in range(6)])
            for cx, cy, _, _ in cells
        ],
        crs=32650,
    )
    ckm = km(cells_gdf)
    v = cells_gdf["v"].to_numpy()
    lo, hi = np.percentile(v, 3), np.percentile(v, 97)
    cmap = LinearSegmentedColormap.from_list("hh", ["#E7F1EA", "#B7DAC6", "#63AE8A", "#2E7A5D", "#154C3B"])

    fig, ax = make_canvas(ext_a)
    ckm.plot(ax=ax, color=[cmap(np.clip((t - lo) / (hi - lo), 0, 1)) for t in v],
             edgecolor="white", linewidth=0.25)
    save(fig, "F1_热力六边形_全市.png")

    fig, ax = make_canvas(ext_a)
    ckm.plot(ax=ax, color=[cmap(np.clip((t - lo) / (hi - lo), 0, 1)) for t in v],
             edgecolor="none")
    city_kmf = gpd.GeoDataFrame(geometry=[shapely.affinity.scale(city, xfact=0.001, yfact=0.001, origin=(0, 0))], crs=32650)
    city_kmf.boundary.plot(ax=ax, color="#0E3A2C", linewidth=1.1, alpha=0.7)
    save(fig, "F2_热力六边形_带边界.png")

    fig, ax = make_canvas(ext_a)
    seg_km.plot(ax=ax, color="#8FA9A0", linewidth=0.22, alpha=0.45)
    ckm.plot(ax=ax, color=[cmap(np.clip((t - lo) / (hi - lo), 0, 1)) for t in v],
             edgecolor="none", alpha=0.86)
    city_kmg = gpd.GeoDataFrame(geometry=[shapely.affinity.scale(city, xfact=0.001, yfact=0.001, origin=(0, 0))], crs=32650)
    city_kmg.boundary.plot(ax=ax, color="#0E3A2C", linewidth=1.0, alpha=0.65)
    save(fig, "F3_热力六边形_带路网.png")

    print(f"[素材] 完成 → {OUT}")


def ext_a_utm(ext_km):
    return (ext_km[0] * 1000, ext_km[2] * 1000, ext_km[1] * 1000, ext_km[3] * 1000)


if __name__ == "__main__":
    main()
