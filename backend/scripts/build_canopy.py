# -*- coding: utf-8 -*-
"""Tree-cover / green-cover share per walk segment, from ESA WorldCover 10 m.

Why this instead of street-view greenness
    Street-level imagery is not available for China without enterprise
    credentials (Tencent requires enterprise certification; Baidu/Gaode do not
    offer it; Mapillary coverage in Wuhan is sparse and roughly a decade old).
    WorldCover 2021 is free, global, 10 m, and gives a measured *tree cover*
    class — a defensible canopy proxy that is not biased by camera placement.

Method
    1. mosaic the 10 m class raster over the walk-network bbox,
    2. downsample x2 (20 m) to keep memory sane,
    3. box-filter the "tree" and "green" masks over ~120 m,
    4. sample the resulting share surface at every segment vertex and average
       length-weighted.

Output
    data/processed/running/v1/segment_canopy.csv
        osm_id, tree_share, green_share, tree_share_max

Classes (WorldCover v200): 10 tree, 20 shrub, 30 grass, 40 crop, 50 built,
60 bare, 70 snow, 80 water, 90 wetland, 95 mangrove, 100 moss.
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import rasterio
import shapely
from rasterio.windows import from_bounds
from scipy.ndimage import uniform_filter

ROOT = Path(__file__).resolve().parents[2]
WC = ROOT / "data" / "raw" / "worldcover"
V1 = ROOT / "data" / "processed" / "v1"
OUT = ROOT / "data" / "processed" / "running" / "v1"
TILES = ["N27E111", "N27E114", "N30E111", "N30E114"]
DOWNSAMPLE = 2          # 10 m -> 20 m
SMOOTH_PX = 6           # 6 * 20 m = 120 m box
TREE, GREEN = 10, {10, 20, 30, 40}


def build_mosaic(bbox) -> tuple[np.ndarray, dict]:
    """Mosaic the 10 m class raster for bbox; returns (array, geotransform)."""
    src0 = rasterio.open(WC / f"ESA_WorldCover_10m_2021_v200_{TILES[-1]}_Map.tif")
    res = src0.res[0]
    src0.close()

    lon0, lat0, lon1, lat1 = bbox
    width = int(round((lon1 - lon0) / res))
    height = int(round((lat1 - lat0) / res))
    arr = np.zeros((height, width), dtype=np.uint8)
    filled = np.zeros((height, width), dtype=bool)

    for t in TILES:
        p = WC / f"ESA_WorldCover_10m_2021_v200_{t}_Map.tif"
        if not p.exists():
            print(f"  missing tile {t}, skipped")
            continue
        with rasterio.open(p) as src:
            b = src.bounds
            if b.right <= lon0 or b.left >= lon1 or b.top <= lat0 or b.bottom >= lat1:
                continue
            win = from_bounds(lon0, lat0, lon1, lat1, src.transform)
            data = src.read(1, window=win, boundless=True, fill_value=0)
            c0 = int(round((max(b.left, lon0) - lon0) / res))
            r0 = int(round((lat1 - min(b.top, lat1)) / res))
            h, w = data.shape
            arr[r0:r0 + h, c0:c0 + w] = data[: height - r0, : width - c0]
            filled[r0:r0 + h, c0:c0 + w] = True
            print(f"  {t}: {h}x{w} px pasted")

    if (~filled).any():
        print(f"  uncovered pixels: {(~filled).sum():,} (filled with 0)")
    return arr, {"lon0": lon0, "lat1": lat1, "res": res}


def main() -> int:
    print("[canopy] reading walk network ...")
    gdf = pyogrio.read_dataframe(V1 / "osm_walk_roads.gpkg", layer="walk_roads")
    wgs = gdf.to_crs(4326)
    b = wgs.total_bounds
    bbox = (float(b[0]) - 0.01, float(b[1]) - 0.01, float(b[2]) + 0.01, float(b[3]) + 0.01)
    print(f"[canopy] bbox {tuple(round(v, 3) for v in bbox)}")

    print("[canopy] mosaicking WorldCover ...")
    arr, geo = build_mosaic(bbox)

    if DOWNSAMPLE > 1:
        arr = arr[::DOWNSAMPLE, ::DOWNSAMPLE]
        geo = {**geo, "res": geo["res"] * DOWNSAMPLE}

    def share_surface(mask: np.ndarray) -> np.ndarray:
        f = mask.astype(np.float32)
        uniform_filter(f, size=SMOOTH_PX, output=f, mode="nearest")
        return f

    print("[canopy] smoothing tree mask ...")
    tree = share_surface(arr == TREE)
    print("[canopy] smoothing green mask ...")
    green_m = np.isin(arr, list(GREEN)).astype(np.float32)
    uniform_filter(green_m, size=SMOOTH_PX, output=green_m, mode="nearest")

    res = geo["res"]
    lon0, lat1 = geo["lon0"], geo["lat1"]
    rows, cols = tree.shape

    def index(lon, lat):
        c = np.rint((lon - lon0) / res).astype(np.int64)
        r = np.rint((lat1 - lat) / res).astype(np.int64)
        np.clip(c, 0, cols - 1, out=c)
        np.clip(r, 0, rows - 1, out=r)
        return r, c

    print(f"[canopy] sampling {len(gdf):,} segments ...")
    metric = gdf.to_crs(32650)
    out_rows = []
    for osm_id, geom, geom_m in zip(gdf["osm_id"], wgs.geometry, metric.geometry):
        ll = np.asarray(shapely.get_coordinates(geom), dtype=np.float64)
        xy = np.asarray(shapely.get_coordinates(geom_m), dtype=np.float64)
        if len(ll) < 2:
            continue
        seg = np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1]))
        if seg.sum() <= 0:
            continue
        r, c = index(ll[:, 0], ll[:, 1])
        t = tree[r, c]
        g = green_m[r, c]
        vw = np.empty(len(t))
        vw[0] = seg[0] / 2
        vw[-1] = seg[-1] / 2
        if len(t) > 2:
            vw[1:-1] = (seg[:-1] + seg[1:]) / 2
        vw = np.clip(vw, 1e-3, None)
        out_rows.append(
            (
                int(osm_id),
                round(float(np.average(t, weights=vw)), 3),
                round(float(np.average(g, weights=vw)), 3),
                round(float(t.max()), 3),
            )
        )

    out = pd.DataFrame(
        out_rows, columns=["osm_id", "tree_share", "green_share", "tree_share_max"]
    )
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "segment_canopy.csv"
    out.to_csv(target, index=False)
    print(f"[canopy] {len(out):,} segments -> {target.relative_to(ROOT)}")
    q = out[["tree_share", "green_share"]].describe(percentiles=[0.5, 0.9]).round(3)
    print(q.to_string())
    print(f"[canopy] segments with tree share > 30%: {(out['tree_share'] > 0.3).sum():,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
