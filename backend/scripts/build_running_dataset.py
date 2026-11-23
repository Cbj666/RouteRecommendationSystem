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
    s_air       annual NO2 from the CHAP 1 km grid (regional correction only)

Weights live in W below and are deliberately explicit: this is a
multi-criteria score, not a measurement. They sum to 1.00 (v2 口径, 2026-11),
so `score` is a weighted mean and 100 is reachable in principle.

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
# 六维，权重合计 1.00（v2 口径，2026-11 定版）。旧 v1 口径合计 0.95、满分只有 95，
# 分数尺度不好解释；改成 1.00 后 score 就是六维加权平均，满分 100。
# 调整依据（逐版权重见 data/output/running/v1/weights/iterations.csv）：
#   safety 0.25→0.36、cross 0.10→0.15：这两维 std 最大（26.7 / 39.9），逐段区分度靠它们；
#   slope  0.15→0.06：武汉坡度中位 88 分，几乎不区分，只用来压极端陡坡；
#   air    0.15→0.11：CHAP 1 km 只做区域校正，同圈层内道路差异仅 0.2–1.8 µg/m³；
#   fac    0.05→0.06：到最近设施点的距离，城内/城外差异大，但沿途密度不可知。
# 效果：全网 std 9.9→12.4（+25%），与 v1 秩相关 0.98、前 10% 路段重合 0.87。
W = {
    "safety": 0.36, "green": 0.26, "slope": 0.06,
    "cross": 0.15, "fac": 0.06, "air": 0.11,
}

# 分档线（右闭区间，边界值归下档）。旧线 40/55/70/85 下"很好"恒为 0，
# 因为全网最高分只有 ~85；改成 35/50/65/80 后五档都有人。
GRADE_BINS = [0, 35, 50, 65, 80, 100]
GRADE_LABELS = ["差", "一般", "较好", "好", "很好"]

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

# --- air quality ----------------------------------------------------------
# 逐年 NO2（CHAP 1 km 网格，build_air_quality_chap.py 产出）。
# 只做「区域校正」：同一圈层内道路等级之间的差异仅 0.2–1.8 µg/m³，
# 而城区与外围差 9.9 µg/m³（见 data/output/running/v1/demo/README.md）。
AIR_CSV = OUT / "segment_air.csv"
NO2_FULL = 10.0       # WHO 2021 年均指导值 → 100 分
NO2_ZERO = 40.0       # GB 3095—2012 二级年均限值 → 0 分


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

    canopy_csv = OUT / "segment_canopy.csv"
    if canopy_csv.exists():
        can = pd.read_csv(canopy_csv)[["osm_id", "tree_share", "green_share", "tree_share_max"]]
        seg = seg.merge(can, on="osm_id", how="left")
        print(f"[run] canopy merged: tree mean {seg['tree_share'].mean():.3f}")
    else:
        print("[run] WARNING: segment_canopy.csv missing, run build_canopy.py", file=sys.stderr)
        seg["tree_share"] = np.nan
        seg["green_share"] = np.nan
        seg["tree_share_max"] = np.nan
    seg["tree_share"] = seg["tree_share"].fillna(0.0)
    seg["green_share"] = seg["green_share"].fillna(0.0)

    print("[run] reading green / water / facilities ...")
    land = pyogrio.read_dataframe(GPKG, layer="gis_osm_landuse_a_free", bbox=bbox)
    green = land[land["fclass"].isin(GREEN_FCLASS)].to_crs(CRS)
    green_tree = (
        shapely.STRtree(green.geometry.to_numpy()) if len(green) else None
    )

    water = pyogrio.read_dataframe(GPKG, layer="gis_osm_water_a_free", bbox=bbox)
    water = water.to_crs(CRS)
    water_tree = shapely.STRtree(water.geometry.to_numpy()) if len(water) else None

    # facilities = Amap sports POIs (dense, commercial source) + OSM support POIs
    parts = []
    amap_csv = OUT / "amap_sport_poi.csv"
    if amap_csv.exists():
        am = pd.read_csv(amap_csv)
        am = am[am["in_boundary"].astype(bool)].dropna(subset=["lng", "lat"])
        # billiards / card rooms / arcades are indoor entertainment, not running support
        drop = am["type"].fillna("").str.contains("台球|棋牌|游戏|歌舞|夜总会|网吧|KTV", regex=True)
        print(f"[run] amap sports POIs: {len(am):,} -> {int((~drop).sum()):,} after dropping indoor entertainment")
        am = am[~drop].reset_index(drop=True)
        parts.append(gpd.GeoDataFrame(
            am[["poi_id", "name"]].copy(),
            # np.asarray keeps the geometry aligned with am's RangeIndex
            geometry=gpd.GeoSeries(np.asarray(shapely.points(am["lng"], am["lat"])), crs=4326),
            crs=4326,
        ).to_crs(CRS))
        print(f"[run] amap sports POIs: {len(am):,}")
    else:
        print("[run] WARNING: amap_sport_poi.csv missing, facilities from OSM only", file=sys.stderr)

    poi = gpd.read_file(V1 / "poi.gpkg", layer="poi_points")
    poi = poi[poi["fclass"].isin(FAC_FCLASS)].to_crs(CRS)
    parts.append(poi[["poi_id", "name", "geometry"]].assign(name=poi["name"].fillna("")))

    fac = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=CRS)
    fac = fac[fac.geometry.notna() & ~fac.geometry.is_empty].copy()
    fac = fac[np.isfinite(fac.geometry.x) & np.isfinite(fac.geometry.y)]
    poi = fac
    poi_tree = cKDTree(np.column_stack([poi.geometry.x, poi.geometry.y])) if len(poi) else None
    print(f"[run] facility points: {len(poi):,}")

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
    if poi_tree is not None:
        d_fac, _ = poi_tree.query(mid_xy, k=1)
        d_fac = np.asarray(d_fac, dtype=float)
        fac_counts = np.array([len(x) for x in poi_tree.query_ball_point(mid_xy, r=500.0)])
    else:
        d_fac = np.full(len(seg), np.inf)
        fac_counts = np.zeros(len(seg))

    # --- sub-scores ------------------------------------------------------
    seg["d_green_m"] = np.round(d_green, 1)
    seg["d_water_m"] = np.round(d_water, 1)
    seg["d_main_m"] = np.round(d_main, 1)
    seg["cross_200m"] = cross_counts
    seg["d_fac_m"] = np.round(d_fac, 0)
    seg["fac_500m"] = fac_counts

    s_safety = seg["fclass"].map(ROAD_SAFETY).fillna(50.0).to_numpy(dtype=float)
    # close to a major road is worse even on a minor street
    s_safety = np.clip(s_safety - np.where(d_main < 50, 15, 0) - np.where(d_main < 20, 10, 0), 0, 100)

    # green = measured canopy (70%) + proximity to a green area (30%).
    # WorldCover resolution misses single street trees, so the distance term
    # keeps "next to a park but under no canopy" from scoring zero.
    shade = 0.8 * seg["tree_share"].to_numpy() + 0.2 * seg["green_share"].to_numpy()
    canopy_score = 100 * (1 - np.exp(-2.5 * shade))
    near_score = np.clip(100 * (1 - d_green / MAX_GREEN_M), 0, 100)
    s_green = 0.7 * canopy_score + 0.3 * near_score

    s_slope = np.clip(100 * (1 - seg["slope_mean_pct"].to_numpy() / SLOPE_ZERO), 0, 100)
    s_cross = np.clip(100 - 7 * cross_counts, 0, 100)
    # decay with walking distance: 0 m -> 100, 500 m -> 37, 1 km -> 14
    s_fac = 100 * np.exp(-d_fac / 500.0)

    seg["s_safety"] = np.round(s_safety, 1)
    seg["s_green"] = np.round(s_green, 1)
    seg["s_slope"] = np.round(s_slope, 1)
    seg["s_cross"] = np.round(s_cross, 1)
    seg["s_fac"] = np.round(s_fac, 1)

    # --- air: annual NO2 from the CHAP 1 km grid --------------------------
    if not AIR_CSV.exists():
        raise SystemExit(
            f"缺少 {AIR_CSV.relative_to(ROOT)}\n"
            "先跑：.\\\\.venv\\\\Scripts\\\\python.exe backend\\\\scripts\\\\build_air_quality_chap.py --year 2024"
        )
    air = pd.read_csv(
        AIR_CSV, encoding="utf-8-sig", usecols=["osm_id", "pm25_ugm3", "no2_ugm3"]
    ).set_index("osm_id")
    no2 = seg["osm_id"].map(air["no2_ugm3"]).to_numpy(dtype=float)
    pm25 = seg["osm_id"].map(air["pm25_ugm3"]).to_numpy(dtype=float)
    n_nan = int(np.isnan(no2).sum())
    no2 = np.where(np.isnan(no2), float(np.nanmedian(no2)), no2)
    pm25 = np.where(np.isnan(pm25), float(np.nanmedian(pm25)), pm25)
    # 100 分 = WHO 指导值，0 分 = 国标二级；线性插值，超出即截断
    s_air = np.clip(100 * (NO2_ZERO - no2) / (NO2_ZERO - NO2_FULL), 0, 100)

    seg["no2_ugm3"] = np.round(no2, 2)
    seg["pm25_ugm3"] = np.round(pm25, 2)
    seg["s_air"] = np.round(s_air, 1)
    print(f"[run] air: NO2 中位 {np.median(no2):.1f}，缺值补城市中位 {n_nan} 段")

    seg["score"] = np.round(
        W["safety"] * s_safety + W["green"] * s_green + W["slope"] * s_slope
        + W["cross"] * s_cross + W["fac"] * s_fac + W["air"] * s_air,
        1,
    )
    seg["grade"] = pd.cut(
        seg["score"], bins=GRADE_BINS, labels=GRADE_LABELS, include_lowest=True,
    ).astype(str)

    keep = [
        "osm_id", "fclass", "name", "length_m", "walk_group", "in_boundary",
        "slope_mean_pct", "elev_gain_m", "tree_share", "green_share",
        "d_green_m", "d_water_m", "d_main_m", "d_fac_m",
        "cross_200m", "fac_500m", "no2_ugm3", "pm25_ugm3",
        "s_safety", "s_green", "s_slope",
        "s_cross", "s_fac", "s_air", "score", "grade", "geometry",
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
        "grade_bins": GRADE_BINS[1:-1],
        "grade_labels": GRADE_LABELS,
        "score": {k: float(v) for k, v in dstats.items()},
        "grade_counts": {k: int(v) for k, v in out["grade"].value_counts().items()},
        "median_subscores": {
            k: round(float(out[k].median()), 1)
            for k in ["s_safety", "s_green", "s_slope", "s_cross", "s_fac", "s_air"]
        },
        "air": {
            "source": "CHAP ChinaHighPM2.5 V4 / ChinaHighNO2 (1 km, Zenodo)",
            "no2_median": round(float(out["no2_ugm3"].median()), 2),
            "pm25_median": round(float(out["pm25_ugm3"].median()), 2),
            "formula": f"s_air = clip(100*(NO2 {NO2_ZERO:.0f} -> 0, {NO2_FULL:.0f} -> 100), 0, 100)",
            "note": "只做区域校正；同圈层内道路等级差异仅 0.2–1.8 µg/m³，不用于逐段区分",
        },
        "notes": [
            "坡度来自 SRTM 1\"，150 m 高斯平滑后求梯度；城区精度约 ±1 个百分点",
            "绿化用 ESA WorldCover 10 m 树冠覆盖率（120 m 窗口），比街景绿视率更不受拍摄点影响",
            "机动车暴露用道路等级 + 距主干道距离代理，无路段流量数据",
            "空气用 CHAP 1 km 年均 NO2：满分=WHO 2021 指导值 10，零分=国标二级 40",
            "设施 = 高德运动场馆 4,081 + OSM 公园/厕所/便利店 5,344 + 高德公厕 5,117，共 14,542 个点，按到最近点的步行距离衰减",
        ],
    }
    (OUT / "score_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
