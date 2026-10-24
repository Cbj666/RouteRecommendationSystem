# -*- coding: utf-8 -*-
"""Build the running/cycling suitability dataset (v0).

One row per OSM road segment with a 0–100 suitability score and the
sub-scores behind it, so the front end can explain *why* a segment scores low.

Indicators (all computable from data already in the repo)
    s_safety    road class: footway/cycleway good, trunk/primary bad
    s_green     distance to the nearest green polygon and to water
    s_slope     DEM slope (build_slope.py) — flat is better for running
    s_cross     intersection density within 200 m (more crossings = more stops)
    s_fac       sports facilities / toilets / convenience stores within 300 m

Weights live in WEIGHTS below and are deliberately explicit: this is a
multi-criteria score, not a measurement.

Output
    data/processed/running/v1/segments.gpkg      (layer segments)
    data/processed/running/v1/score_summary.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/ for `app`
RAW = ROOT / "data" / "raw"
V1 = ROOT / "data" / "processed" / "v1"
OUT = ROOT / "data" / "processed" / "running" / "v1"
GPKG = RAW / "hubei" / "hubei-261013-free-OpenMap" / "hubei.gpkg"
CRS = 32650

# --- scoring design -------------------------------------------------------
W = {"safety": 0.30, "green": 0.25, "slope": 0.20, "cross": 0.10, "fac": 0.10}

ROAD_SAFETY = {
    "footway": 95, "path": 90, "pedestrian": 95, "steps": 70, "cycleway": 92,
    "living_street": 80, "residential": 70, "service": 62, "unclassified": 56,
    "tertiary": 46, "tertiary_link": 44, "secondary": 32, "secondary_link": 30,
    "primary": 18, "primary_link": 16, "trunk": 10, "trunk_link": 8,
    "track": 74, "track_grade1": 72, "track_grade2": 66, "track_grade3": 58,
    "track_grade4": 50, "track_grade5": 44, "bridleway": 60, "road": 50,
}
GREEN_FCLASS = {"park", "forest", "grass", "meadow", "scrub", "recreation_ground"}
FAC_FCLASS = {
    "pitch", "track", "sports_centre", "sports_hall", "stadium", "playground",
    "park", "toilet", "shelter", "bench", "drinking_water",
    "supermarket", "convenience", "bicycle_parking", "bicycle_rental",
}
MAX_GREEN_M = 1500.0
MAX_WATER_M = 1500.0
SLOPE_ZERO = 10.0     # %: at or above this, running suitability is 0


def nearest_distance_upto(tree, target_geoms, pts, max_dist: float) -> np.ndarray:
    """Exact distance from each point to the nearest target geometry, capped."""
    out = np.full(len(pts), np.inf)
    if tree is None:
        return out
    pairs = tree.query(pts, predicate="dwithin", distance=max_dist)
    if pairs.size == 0:
        return out
    a, b = pairs[0], pairs[1]
    # shapely returns (tree_idx, input_idx); guard against the opposite order
    if a.max() >= len(target_geoms):
        a, b = b, a
    if a.max() >= len(target_geoms) or b.max() >= len(pts):
        print(f"    ! unexpected index ranges a<{a.max()}/{len(target_geoms)} "
              f"b<{b.max()}/{len(pts)}", flush=True)
        keep = (a < len(target_geoms)) & (b < len(pts))
        a, b = a[keep], b[keep]
    cand = target_geoms[a]
    d = shapely.distance(cand, pts[b])
    np.minimum.at(out, b, d)
    return out


def main() -> int:
    print("[run] reading segments ...")
    seg = pyogrio.read_dataframe(V1 / "osm_walk_roads.gpkg", layer="walk_roads")
    seg = seg.to_crs(CRS).reset_index(drop=True)
    mid = seg.geometry.interpolate(0.5, normalized=True)
    mx = mid.x.to_numpy()
    my = mid.y.to_numpy()
    mid_xy = np.column_stack([mx, my])
    bbox = tuple(float(v) for v in seg.to_crs(4326).total_bounds)  # layers are WGS84

    print("[run] loading DEM slope ...")
    slope_csv = OUT / "segment_slope.csv"
    if not slope_csv.exists():
        print("missing segment_slope.csv — run build_slope.py first", file=sys.stderr)
        return 1
    slope = pd.read_csv(slope_csv)[["osm_id", "slope_mean_pct", "elev_gain_m"]]
    seg["osm_id"] = pd.to_numeric(seg["osm_id"], errors="coerce").astype("int64")
    seg = seg.merge(slope, on="osm_id", how="left")
    seg["slope_mean_pct"] = seg["slope_mean_pct"].fillna(0.0)

    print("[run] reading green / water / facilities ...")
    land = pyogrio.read_dataframe(GPKG, layer="gis_osm_landuse_a_free", bbox=bbox)
    green = land[land["fclass"].isin(GREEN_FCLASS)].to_crs(CRS)
    green_tree = (
        shapely.STRtree(green.geometry.to_numpy()) if len(green) else None
    )

    water = pyogrio.read_dataframe(GPKG, layer="gis_osm_water_a_free", bbox=bbox)
    water = water.to_crs(CRS)
    water_tree = shapely.STRtree(water.geometry.to_numpy()) if len(water) else None

    poi = gpd.read_file(V1 / "poi.gpkg", layer="poi_points")
    poi = poi[poi["fclass"].isin(FAC_FCLASS)].to_crs(CRS)
    poi_tree = cKDTree(np.column_stack([poi.geometry.x, poi.geometry.y])) if len(poi) else None

    main_roads = seg[seg["fclass"].isin(
        ["primary", "primary_link", "secondary", "secondary_link", "trunk", "motorway"]
    )]
    main_tree = shapely.STRtree(main_roads.geometry.to_numpy()) if len(main_roads) else None

    print("[run] intersections from the multimodal graph ...")
    from app.graph import load_or_build

    g = load_or_build(cache=True, verbose=False)
    deg = np.diff(g.csr.indptr)[: g.n_walk]
    inter = np.column_stack([g.x[: g.n_walk][deg >= 3], g.y[: g.n_walk][deg >= 3]])
    inter_tree = cKDTree(inter)

    # --- distance-based terms -------------------------------------------
    print("[run] distances ...")
    mid_geom = mid.to_numpy()
    d_green = nearest_distance_upto(green_tree, green.geometry.to_numpy(), mid_geom, MAX_GREEN_M)
    print("  green done")
    d_water = nearest_distance_upto(water_tree, water.geometry.to_numpy(), mid_geom, MAX_WATER_M)
    print("  water done")
    d_main = nearest_distance_upto(main_tree, main_roads.geometry.to_numpy(), mid_geom, 500.0)
    print("  main roads done")

    print("[run] counts ...")
    cross_counts = np.array([len(x) for x in inter_tree.query_ball_point(mid_xy, r=200.0)])
    fac_counts = (
        np.array([len(x) for x in poi_tree.query_ball_point(mid_xy, r=500.0)])
        if poi_tree is not None else np.zeros(len(seg))
    )

    # --- sub-scores ------------------------------------------------------
    seg["d_green_m"] = np.round(d_green, 1)
    seg["d_water_m"] = np.round(d_water, 1)
    seg["d_main_m"] = np.round(d_main, 1)
    seg["cross_200m"] = cross_counts
    seg["fac_500m"] = fac_counts

    s_safety = seg["fclass"].map(ROAD_SAFETY).fillna(50.0).to_numpy(dtype=float)
    # close to a major road is worse even on a minor street
    s_safety = np.clip(s_safety - np.where(d_main < 50, 15, 0) - np.where(d_main < 20, 10, 0), 0, 100)

    s_green = np.clip(100 * (1 - d_green / MAX_GREEN_M), 0, 100)
    s_water = np.clip(100 * (1 - d_water / MAX_WATER_M), 0, 100)
    s_green = 0.7 * s_green + 0.3 * s_water

    s_slope = np.clip(100 * (1 - seg["slope_mean_pct"].to_numpy() / SLOPE_ZERO), 0, 100)
    s_cross = np.clip(100 - 7 * cross_counts, 0, 100)
    s_fac = np.clip(15 * fac_counts, 0, 100)

    seg["s_safety"] = np.round(s_safety, 1)
    seg["s_green"] = np.round(s_green, 1)
    seg["s_slope"] = np.round(s_slope, 1)
    seg["s_cross"] = np.round(s_cross, 1)
    seg["s_fac"] = np.round(s_fac, 1)

    seg["score"] = np.round(
        W["safety"] * s_safety + W["green"] * s_green + W["slope"] * s_slope
        + W["cross"] * s_cross + W["fac"] * s_fac,
        1,
    )
    seg["grade"] = pd.cut(
        seg["score"], bins=[0, 40, 55, 70, 85, 100],
        labels=["差", "一般", "较好", "好", "很好"], include_lowest=True,
    ).astype(str)

    keep = [
        "osm_id", "fclass", "name", "length_m", "walk_group", "in_boundary",
        "slope_mean_pct", "elev_gain_m", "d_green_m", "d_water_m", "d_main_m",
        "cross_200m", "fac_500m", "s_safety", "s_green", "s_slope",
        "s_cross", "s_fac", "score", "grade", "geometry",
    ]
    out = seg[[c for c in keep if c in seg.columns]].to_crs(4326)
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "segments.gpkg"
    if target.exists():
        target.unlink()
    out.to_file(target, layer="segments", driver="GPKG")
    print(f"[run] {len(out):,} segments -> {target.relative_to(ROOT)}")

    dstats = out["score"].describe(percentiles=[0.1, 0.5, 0.9]).round(1)
    summary = {
        "segments": int(len(out)),
        "length_km": round(float(out["length_m"].sum() / 1000), 1),
        "weights": W,
        "score": {k: float(v) for k, v in dstats.items()},
        "grade_counts": {k: int(v) for k, v in out["grade"].value_counts().items()},
        "median_subscores": {
            k: round(float(out[k].median()), 1)
            for k in ["s_safety", "s_green", "s_slope", "s_cross", "s_fac"]
        },
        "notes": [
            "坡度来自 SRTM 1\"，150 m 高斯平滑后求梯度；城区精度约 ±1 个百分点",
            "绿化用 landuse 多边形距离代理，不是实测绿视率",
            "机动车暴露用道路等级 + 距主干道距离代理，无路段流量数据",
            "POI 来自 OSM，覆盖弱于商业地图，设施计数偏低",
        ],
    }
    (OUT / "score_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
