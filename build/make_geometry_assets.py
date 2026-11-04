"""生成 PPT 视觉素材：把地图解构成可以单独叠放的几何层。

输出 presentation/素材/，全部**透明背景 PNG**，分两套配准范围：

    全市套（约 136 × 157 km）  A 开头，含行政区、路网
    中心城套（约 46 × 40 km）  B 开头，含路网、三种路线、热点点阵

同一套内部的图片尺寸与地理范围完全一致，在 PPT 里按相同大小叠放即可对齐。

运行：
    .\\.venv\\Scripts\\python.exe build\\make_geometry_assets.py
"""

from __future__ import annotations

import pathlib
import sys

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
from scipy.sparse.csgraph import dijkstra
from shapely.geometry import Point, box

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import running  # noqa: E402

OUT = ROOT / "presentation" / "素材"
OUT.mkdir(parents=True, exist_ok=True)

PRIMARY = "#15503C"
ROCK = "#7FA894"
PALE = "#D9E8DF"

CANVAS_W = 1800
DPI = CANVAS_W / 9.0

ORIGIN = (114.3547, 30.5342)  # 武汉大学 · 八一路珞珈山
PREFS = {"green": 1.0, "safe": 1.0, "flat": 0.6}


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


def edge_len(g, a, b):
    lo, hi = int(g.csr_len.indptr[a]), int(g.csr_len.indptr[a + 1])
    if lo == hi:
        return 0.0
    i = int(np.searchsorted(g.csr_len.indices[lo:hi], b)) + lo
    if i >= hi or g.csr_len.indices[i] != b:
        return 0.0
    return float(g.csr_len.data[i])


def route_length(g, nodes):
    return sum(edge_len(g, a, b) for a, b in zip(nodes[:-1], nodes[1:]))


def path_nodes(g, pred, start, end):
    out, cur = [], int(end)
    while cur != -9999 and cur != start:
        out.append(cur)
        cur = int(pred[cur])
    out.append(int(start))
    return out[::-1]


def one_way_nodes(g, cost, lng, lat, target_m, n_dir=8):
    origin, _ = g.nearest(lng, lat)
    dist_len = dijkstra(g.csr_len, directed=True, indices=origin)
    band = np.flatnonzero(np.isfinite(dist_len) & (np.abs(dist_len - target_m) <= 0.12 * target_m))
    if band.size < 2:
        return []
    ang = np.arctan2(g.y[band] - g.y[origin], g.x[band] - g.x[origin])
    order = np.argsort(ang)
    picked = [band[order[int(i * (len(order) - 1) / (n_dir - 1))]] for i in range(n_dir)]
    picked = list(dict.fromkeys(int(v) for v in picked))
    _, pred = dijkstra(cost, directed=True, indices=origin, return_predecessors=True)
    best, best_gap = [], float("inf")
    for dest in picked:
        nodes = path_nodes(g, pred, origin, dest)
        if len(nodes) < 2:
            continue
        length = route_length(g, nodes)
        if not (0.85 * target_m <= length <= 1.15 * target_m):
            continue
        gap = abs(length - target_m)
        if gap < best_gap:
            best, best_gap = nodes, gap
    return best


def main():
    print("[素材] 读数据")
    boundary = gpd.read_file(ROOT / "data" / "processed" / "v1" / "wuhan_boundary.geojson").to_crs(32650)
    seg = gpd.read_file(ROOT / "data" / "processed" / "running" / "v1" / "segments.gpkg",
                        layer="segments").to_crs(32650)
    hot = pd.read_csv(ROOT / "data" / "output" / "running" / "v1" / "demo" / "hotspots.csv",
                      encoding="utf-8-sig")
    pts = gpd.GeoDataFrame(
        hot, geometry=[Point(x, y) for x, y in zip(hot["lng"], hot["lat"])], crs=4326
    ).to_crs(32650)

    print("[素材] 算路线")
    g = running.load_or_build()
    cost = running._cost_matrix(g, running._pref_score(g, PREFS))
    rings = running.generate_loops(g, ORIGIN[0], ORIGIN[1], target_m=5000, prefs=PREFS, max_candidates=8)
    rings.sort(key=lambda r: -r["score"])
    ring = rings[0]["nodes"]
    mars = running.generate_loops(g, ORIGIN[0], ORIGIN[1], target_m=42195, prefs=PREFS, max_candidates=8)
    mars.sort(key=lambda r: -r["score"])
    mar = mars[0]["nodes"]
    one = one_way_nodes(g, cost, ORIGIN[0], ORIGIN[1], target_m=10000)
    print(f"       环线 {route_length(g, ring)/1000:.2f} km / 单行线 {route_length(g, one)/1000:.2f} km"
          f" / 马拉松 {route_length(g, mar)/1000:.2f} km")

    def xy(nodes):
        idx = np.array(nodes, dtype=int)
        return g.x[idx] / 1000.0, g.y[idx] / 1000.0

    # 全市套 ------------------------------------------------------------------
    bx0, by0, bx1, by1 = boundary.total_bounds
    pad = 1500.0
    ext_a = ((bx0 - pad) / 1000, (bx1 + pad) / 1000, (by0 - pad) / 1000, (by1 + pad) / 1000)
    bkm = boundary.set_geometry(boundary.geometry.scale(0.001, 0.001, origin=(0, 0)))
    inside = seg[seg.intersects(boundary.union_all())]
    inside_km = inside.set_geometry(inside.geometry.scale(0.001, 0.001, origin=(0, 0)))
    seg_km = seg.set_geometry(seg.geometry.scale(0.001, 0.001, origin=(0, 0)))

    print("[素材] 全市套")
    fig, ax = make_canvas(ext_a)
    bkm.plot(ax=ax, facecolor=PRIMARY, edgecolor="none", alpha=0.06)
    bkm.boundary.plot(ax=ax, color=PRIMARY, linewidth=5.0, joinstyle="round")
    save(fig, "A1_行政区_全市.png")

    fig, ax = make_canvas(ext_a)
    inside_km.plot(ax=ax, color=PRIMARY, linewidth=0.3, alpha=0.55)
    save(fig, "A2_路网_全市.png")

    fig, ax = make_canvas(ext_a)
    bkm.plot(ax=ax, facecolor="none", edgecolor=PRIMARY, linewidth=2.0, alpha=0.55)
    seg_km.plot(ax=ax, color=PRIMARY, linewidth=0.22, alpha=0.28)
    save(fig, "A3_路网含域外_全市.png")

    # 中心城套 ----------------------------------------------------------------
    hx0, hy0, hx1, hy1 = pts.total_bounds
    cpad = 4000.0
    mar_idx = np.array(mar, dtype=int)
    cx0 = min(hx0, g.x[mar_idx].min()) - cpad
    cy0 = min(hy0, g.y[mar_idx].min()) - cpad
    cx1 = max(hx1, g.x[mar_idx].max()) + cpad
    cy1 = max(hy1, g.y[mar_idx].max()) + cpad
    ext_b = (cx0 / 1000, cx1 / 1000, cy0 / 1000, cy1 / 1000)
    near = seg[seg.intersects(box(cx0, cy0, cx1, cy1))]
    near_km = near.set_geometry(near.geometry.scale(0.001, 0.001, origin=(0, 0)))
    print(f"       中心城范围 {int(cx1-cx0)/1000:.1f} × {int(cy1-cy0)/1000:.1f} km")

    print("[素材] 中心城套")
    fig, ax = make_canvas(ext_b)
    near_km.plot(ax=ax, color=PRIMARY, linewidth=0.42, alpha=0.55)
    save(fig, "B1_路网_中心城.png")

    for name, nodes, lw in [
        ("B2_路线_环线5km.png", ring, 3.4),
        ("B3_路线_单行线10km.png", one, 3.4),
        ("B4_路线_马拉松42km.png", mar, 3.0),
    ]:
        fig, ax = make_canvas(ext_b)
        xs, ys = xy(nodes)
        ax.plot(xs, ys, color=PRIMARY, linewidth=lw,
                solid_capstyle="round", solid_joinstyle="round")
        ax.plot(xs[0], ys[0], "o", ms=10, mfc="white", mec=PRIMARY, mew=2.4, zorder=5)
        save(fig, name)

    fig, ax = make_canvas(ext_b)
    for nodes, lw, alpha in [(mar, 2.4, 0.45), (one, 3.0, 0.75), (ring, 4.2, 1.0)]:
        xs, ys = xy(nodes)
        ax.plot(xs, ys, color=PRIMARY, linewidth=lw, alpha=alpha,
                solid_capstyle="round", solid_joinstyle="round")
    save(fig, "B5_路线_三条合并.png")

    v = pts["top3"].to_numpy()
    rank = v.argsort().argsort()
    norm = rank / max(len(v) - 1, 1)
    cmap = LinearSegmentedColormap.from_list("h", ["#B7DAC6", "#63AE8A", "#2E7A5D", "#154C3B"])
    sizes = 60 + 760 * norm ** 1.45

    fig, ax = make_canvas(ext_b)
    ax.scatter(pts.geometry.x / 1000.0, pts.geometry.y / 1000.0, s=sizes,
               c=[cmap(t) for t in norm], edgecolor="white", linewidth=0.6, zorder=3)
    save(fig, "B6_热点点阵.png")

    fig, ax = make_canvas(ext_b)
    ax.scatter(pts.geometry.x / 1000.0, pts.geometry.y / 1000.0, s=sizes,
               c=[cmap(t) for t in norm], edgecolor="white", linewidth=0.6, zorder=3)
    xs, ys = xy(ring)
    ax.plot(xs, ys, color="#B8402F", linewidth=3.6,
            solid_capstyle="round", solid_joinstyle="round", zorder=4)
    save(fig, "B7_热点加环线.png")

    # C 套：单条路线的紧裁幅面（不含路网，适合做大图）
    print("[素材] 路线紧裁套")
    for name, nodes, lw, padm in [
        ("C1_路线_环线5km_紧裁.png", ring, 4.6, 1200.0),
        ("C2_路线_单行线10km_紧裁.png", one, 4.6, 1200.0),
        ("C3_路线_马拉松42km_紧裁.png", mar, 3.4, 1500.0),
    ]:
        idx = np.array(nodes, dtype=int)
        ex = (g.x[idx].min() - padm) / 1000, (g.x[idx].max() + padm) / 1000, \
             (g.y[idx].min() - padm) / 1000, (g.y[idx].max() + padm) / 1000
        fig, ax = make_canvas(ex)
        xs, ys = xy(nodes)
        ax.plot(xs, ys, color=PRIMARY, linewidth=lw,
                solid_capstyle="round", solid_joinstyle="round")
        ax.plot(xs[0], ys[0], "o", ms=9, mfc="white", mec=PRIMARY, mew=2.2, zorder=5)
        save(fig, name)

    # 预览 --------------------------------------------------------------------
    print("[素材] 预览合成")
    fig, ax = make_canvas(ext_a)
    bkm.plot(ax=ax, facecolor=PALE, edgecolor=PRIMARY, linewidth=2.4)
    inside_km.plot(ax=ax, color=ROCK, linewidth=0.28, alpha=0.7)
    save(fig, "Z1_预览_全市.png", transparent=False)

    fig, ax = make_canvas(ext_b)
    near_km.plot(ax=ax, color=ROCK, linewidth=0.4, alpha=0.75)
    ax.scatter(pts.geometry.x / 1000.0, pts.geometry.y / 1000.0, s=sizes * 0.75,
               c=[cmap(t) for t in norm], edgecolor="white", linewidth=0.5, zorder=3, alpha=0.95)
    xs, ys = xy(ring)
    ax.plot(xs, ys, color=PRIMARY, linewidth=4.6,
            solid_capstyle="round", solid_joinstyle="round", zorder=4)
    save(fig, "Z2_预览_中心城.png", transparent=False)

    print(f"[素材] 完成 → {OUT}")


if __name__ == "__main__":
    main()
