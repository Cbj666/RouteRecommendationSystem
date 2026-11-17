# -*- coding: utf-8 -*-
"""One-off: how much the Amap toilet subset moves the s_fac dimension.

Compares three facility sets at the midpoints of all 91k walk segments:

    as_built   what segments.gpkg actually used before 2026-11-17
               (sports POIs index-misaligned -> 828/4,081 lost; OSM POIs lost
               because their geometry column was not carried through concat)
    old_fixed  geometry bugs fixed, Amap toilets NOT yet added
    new        geometry bugs fixed + the 5,117 Amap public toilets

Read-only; writes data/output/running/v1/toilet_facility_impact.json.
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

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "data" / "processed" / "v1"
OUT = ROOT / "data" / "processed" / "running" / "v1"
CRS = 32650
FAC_FCLASS = {
    "pitch", "track", "sports_centre", "sports_hall", "stadium", "playground",
    "park", "toilet", "shelter", "bench", "drinking_water",
    "supermarket", "convenience", "bicycle_parking", "bicycle_rental",
}


def sports() -> pd.DataFrame:
    am = pd.read_csv(OUT / "amap_sport_poi.csv")
    am = am[am["in_boundary"].astype(bool)].dropna(subset=["lng", "lat"])
    drop = am["type"].fillna("").str.contains("台球|棋牌|游戏|歌舞|夜总会|网吧|KTV", regex=True)
    return am[~drop]


def facility_points(fix_bugs: bool, include_amap_toilet: bool) -> gpd.GeoDataFrame:
    am = sports()
    if fix_bugs:
        am = am.reset_index(drop=True)
        geom = gpd.GeoSeries(np.asarray(shapely.points(am["lng"], am["lat"])), crs=4326)
        p1 = gpd.GeoDataFrame(am[["poi_id", "name"]].copy(), geometry=geom, crs=4326)
    else:                      # the pre-fix construction: range index vs filtered index
        p1 = gpd.GeoDataFrame(
            am[["poi_id", "name"]].copy(),
            geometry=gpd.GeoSeries(shapely.points(am["lng"], am["lat"]), crs=4326),
            crs=4326,
        )
    p1 = p1.to_crs(CRS)

    poi = gpd.read_file(V1 / "poi.gpkg", layer="poi_points")
    if not include_amap_toilet:
        poi = poi[poi["source_layer"] != "amap_toilet"]
    poi = poi[poi["fclass"].isin(FAC_FCLASS)].to_crs(CRS)
    if fix_bugs:
        p2 = poi[["poi_id", "name", "geometry"]].assign(name=poi["name"].fillna(""))
    else:                      # the pre-fix construction: geometry column dropped
        p2 = poi[["poi_id", "name"]].assign(name=poi["name"].fillna(""))

    fac = gpd.GeoDataFrame(pd.concat([p1, p2], ignore_index=True), geometry="geometry", crs=CRS)
    fac = fac[fac.geometry.notna() & ~fac.geometry.is_empty]
    return fac[np.isfinite(fac.geometry.x) & np.isfinite(fac.geometry.y)]


def distances(mid_xy: np.ndarray, fac: gpd.GeoDataFrame) -> np.ndarray:
    tree = cKDTree(np.column_stack([fac.geometry.x, fac.geometry.y]))
    d, _ = tree.query(mid_xy, k=1)
    return np.asarray(d, dtype=float)


def stats(name: str, d: np.ndarray, s_fac: np.ndarray, n_fac: int) -> dict:
    return {
        "set": name,
        "facilities": n_fac,
        "median_d_fac_m": round(float(np.median(d)), 1),
        "pct_within_300m": round(float((d <= 300).mean() * 100), 1),
        "pct_within_500m": round(float((d <= 500).mean() * 100), 1),
        "pct_within_1000m": round(float((d <= 1000).mean() * 100), 1),
        "mean_s_fac": round(float(s_fac.mean()), 2),
        "median_s_fac": round(float(np.median(s_fac)), 2),
        "pct_s_fac_lt_20": round(float((s_fac < 20).mean() * 100), 1),
    }


def main() -> int:
    seg = pyogrio.read_dataframe(V1 / "osm_walk_roads.gpkg", layer="walk_roads")
    seg = seg.to_crs(CRS).reset_index(drop=True)
    mid = seg.geometry.interpolate(0.5, normalized=True)
    mid_xy = np.column_stack([mid.x.to_numpy(), mid.y.to_numpy()])
    print(f"[impact] {len(seg):,} segments")

    sets = {
        "as_built": facility_points(False, False),
        "old_fixed": facility_points(True, False),
        "new": facility_points(True, True),
    }
    results, d = {}, {}
    for name, fac in sets.items():
        print(f"[impact] {name}: {len(fac):,} facilities")
        d[name] = distances(mid_xy, fac)
        results[name] = stats(name, d[name], 100 * np.exp(-d[name] / 500.0), len(fac))

    def compare(a: str, b: str) -> dict:
        sa, sb = 100 * np.exp(-d[a] / 500.0), 100 * np.exp(-d[b] / 500.0)
        delta = sb - sa
        changed = delta > 0.05
        return {
            "from": a, "to": b,
            "changed_segments": int(changed.sum()),
            "changed_pct": round(float(changed.mean() * 100), 1),
            "mean_delta_s_fac": round(float(delta.mean()), 2),
            "median_delta_s_fac_when_changed": (
                round(float(np.median(delta[changed])), 1) if changed.any() else None
            ),
            "mean_delta_total_score": round(float(0.05 * delta.mean()), 2),
            "max_delta_total_score": round(float(0.05 * delta.max()), 2),
            "share_reaching_s_fac_50": {
                a: round(float((sa >= 50).mean() * 100), 1),
                b: round(float((sb >= 50).mean() * 100), 1),
            },
        }

    summary = {
        "segments": len(seg),
        "sets": results,
        "as_built_to_new": compare("as_built", "new"),
        "old_fixed_to_new": compare("old_fixed", "new"),
        "note": "total score delta = 0.05 * delta s_fac at current weight; "
                "s_fac = 100*exp(-d_fac/500)",
    }
    dst = OUT / "toilet_facility_impact.json"
    dst.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[impact] -> {dst.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
