# -*- coding: utf-8 -*-
"""Generate running loops for a few Wuhan origins and map them.

Output
    data/output/running/v1/loops.geojson
    data/output/running/v1/loops.png
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import running  # noqa: E402

OUT = ROOT / "data" / "output" / "running" / "v1"

ORIGINS = [
    ("wuda", "武汉大学（八一路珞珈山）", 114.3547, 30.5342),
    ("donghu", "东湖绿道（湖心岛）", 114.4100, 30.5480),
    ("jiangtan", "汉口江滩", 114.2960, 30.5980),
]
TARGET_M = 5000

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def main() -> int:
    t0 = time.time()
    print("[loops] loading run graph ...")
    g = running.load_or_build()
    print(f"[loops] {g.n:,} nodes, {g.csr_len.nnz:,} edges, {time.time() - t0:.1f}s")

    OUT.mkdir(parents=True, exist_ok=True)
    all_feats = []
    fig, axes = plt.subplots(1, 3, figsize=(19, 6.6), constrained_layout=True)

    for ax, (slug, label, lng, lat) in zip(axes, ORIGINS):
        t1 = time.time()
        loops = running.generate_loops(g, lng, lat, TARGET_M)
        print(f"\n=== {label} · 目标 {TARGET_M / 1000:.0f} km ===")
        print(f"    {len(loops)} loops in {time.time() - t1:.1f}s")
        for i, lp in enumerate(loops[:3], 1):
            print(
                f"  #{i} {lp['length_m'] / 1000:.2f} km  {lp['minutes']:.0f} min  "
                f"score {lp['score']:.1f}  tree {lp['tree_share'] * 100:.0f}%  "
                f"slope {lp['slope_mean_pct']:.1f}%  fac {lp['facility_m']:.0f} m"
            )
        if loops:
            fc = running.to_geojson(g, loops, slug)
            for f in fc["features"]:
                f["properties"]["origin"] = slug
                f["properties"]["label"] = label
            all_feats += fc["features"]

        # plot: fast LineCollection of edges inside the view
        import shapely
        from matplotlib.collections import LineCollection

        cx, cy = running._utm(lng, lat)
        rows, cols = g.csr_len.nonzero()
        xs, ys = g.x, g.y
        inside = (
            (np.minimum(xs[rows], xs[cols]) < cx + 4500)
            & (np.maximum(xs[rows], xs[cols]) > cx - 4500)
            & (np.minimum(ys[rows], ys[cols]) < cy + 4500)
            & (np.maximum(ys[rows], ys[cols]) > cy - 4500)
            & (rows < cols)
        )
        r, c = rows[inside], cols[inside]
        segs = np.stack(
            [np.column_stack([xs[r], ys[r]]), np.column_stack([xs[c], ys[c]])], axis=1
        )
        lc = LineCollection(segs, cmap="RdYlGn", linewidths=0.6, alpha=0.55, zorder=1)
        lc.set_array(g.edge_attr["score"][inside])
        lc.set_clim(25, 70)
        ax.add_collection(lc)
        colours = ["#111111", "#2f7d5d", "#8c6d1f"]
        for i, lp in enumerate(loops[:3]):
            xy = np.array([[g.x[n], g.y[n]] for n in lp["nodes"]])
            ax.plot(xy[:, 0], xy[:, 1], color=colours[i % 3],
                    linewidth=2.6 - i * 0.6, solid_capstyle="round", zorder=5,
                    label=f"#{i + 1} {lp['length_m'] / 1000:.1f} km / {lp['score']:.0f}分")
        ax.scatter([cx], [cy], s=90, c="#ffffff", edgecolor="#000000", zorder=6)
        ax.set_xlim(cx - 4200, cx + 4200)
        ax.set_ylim(cy - 4200, cy + 4200)
        ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f"{label} · 目标 {TARGET_M / 1000:.0f} km", fontsize=11)
        if loops:
            ax.legend(loc="lower left", fontsize=8, framealpha=0.9)

    fc = {"type": "FeatureCollection", "features": all_feats}
    target = OUT / "loops.geojson"
    target.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    print(f"\n[loops] {len(all_feats)} loops -> {target.relative_to(ROOT)}")

    png = OUT / "loops.png"
    fig.savefig(png, dpi=150)
    print(f"[loops] map -> {png.relative_to(ROOT)}")
    print(f"[loops] total {time.time() - t0:.1f}s")
    return 0


def _edge_geoms(g: running.RunGraph):
    import shapely

    rows, cols = g.csr_len.nonzero()
    keep = rows < cols          # one geometry per undirected edge
    coords = np.stack([g.x, g.y], axis=1)
    for a, b in zip(rows[keep], cols[keep]):
        yield shapely.LineString([coords[a], coords[b]])


if __name__ == "__main__":
    sys.exit(main())
