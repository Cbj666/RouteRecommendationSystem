# -*- coding: utf-8 -*-
"""Merge the Amap public-toilet crawl into ``poi.gpkg`` (layer ``poi_points``).

Amap granularity: ``200300`` is a city public toilet, while ``200301/2/3`` are
the male / female / accessible rooms *inside* a venue (a mall can contribute
half a dozen points at one address).  The first is what "沿途公厕" means for a
runner, so:

    fclass = "toilet"          for 200300        -> picked up by FAC_FCLASS
    fclass = "toilet_indoor"   for 200301/2/3    -> stored, not scored

Compound typecodes such as ``060400|200300`` (a supermarket that also carries a
toilet tag) describe the venue, not a toilet, so they are dropped.  A generic
``200000`` 公共设施 point *named* 公共厕所 is kept: the name is the evidence, the
type is just coarse.  Locksmiths / waterproofing shops that the fuzzy keyword
search also returned are rejected by name.

Idempotent: rows with ``source_layer == "amap_toilet"`` are dropped and rebuilt,
so rerunning after a bigger crawl just replaces the Amap subset.  ``src_id``
keeps Amap's POI id for later re-fetches / dedupe.

Output
    data/processed/v1/poi.gpkg            (poi_points appended, poi_areas kept)
    data/output/running/v1/amap_toilet_merge_summary.json
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
V1 = ROOT / "data" / "processed" / "v1"
RUN = ROOT / "data" / "processed" / "running" / "v1"
OUT = ROOT / "data" / "output" / "running" / "v1"
CSV = RUN / "amap_toilet_poi.csv"
GPKG = V1 / "poi.gpkg"
CRS = 32650
SOURCE = "amap_toilet"
PUBLIC_CODES = {"200300"}
INDOOR_CODES = {"200301", "200302", "200303"}
# Amap sometimes files a real public toilet under a generic typecode (200000
# 公共设施, 150908 停车场 at a metro station, 070000 生活服务 ...).  The keyword
# search also drags in locksmiths / waterproofing shops, so the fallback needs
# both a positive name pattern and a vendor/office blacklist.
TOILET_WORDS = ("公共厕所", "城市公厕", "公厕", "旅游厕所", "公共卫生间",
                "卫生间", "洗手间", "第三卫生间", "厕所")
NOT_A_TOILET = ("隔断", "开锁", "维修", "防水", "修缮", "广告", "图文",
                "管理站", "管理中心", "服务部", "锁业", "锁城", "大王",
                "暂停营业", "已关闭", "拆除")


def classify(name: str, typecode: str) -> str | None:
    """Return ``toilet`` / ``toilet_indoor`` / ``None`` (not a toilet POI)."""
    text = str(name or "")
    if any(w in text for w in NOT_A_TOILET):
        return None                      # closed toilet / vendor / management office
    parts = [p for p in str(typecode or "").split("|") if p]
    if parts and parts[0] in PUBLIC_CODES:
        return "toilet"
    if parts and parts[0] in INDOOR_CODES:
        return "toilet_indoor"
    if any(w in text for w in TOILET_WORDS):
        return "toilet"                  # real toilet under a generic typecode
    return None


def next_ids(existing: pd.Series, n: int) -> list[str]:
    nums = existing.str.slice(2).astype(int)
    start = int(nums.max()) + 1
    return [f"P-{i:06d}" for i in range(start, start + n)]


def main() -> int:
    if not CSV.exists():
        raise SystemExit(f"缺少 {CSV.relative_to(ROOT)}，先跑 backend/scripts/fetch_amap_toilet_poi.py")
    df = pd.read_csv(CSV, encoding="utf-8-sig")
    total_crawled = len(df)
    in_boundary_n = int(df["in_boundary"].sum())
    print(f"[merge] crawled {total_crawled:,} POIs ({in_boundary_n:,} in boundary)")
    df = df[df["in_boundary"].astype(bool)].dropna(subset=["lng", "lat"]).copy()
    df["fclass_new"] = [classify(n, t) for n, t in zip(df["name"], df["typecode"])]
    dropped = df[df["fclass_new"].isna()]
    if len(dropped):
        print(f"[merge] dropped {len(dropped):,} compound/venue POIs (e.g. "
              f"{dropped['name'].head(3).tolist()})")
    df = df[df["fclass_new"].notna()].copy()
    print(f"[merge] toilet subset {len(df):,}: "
          f"public {int((df['fclass_new'] == 'toilet').sum()):,}, "
          f"indoor {int((df['fclass_new'] == 'toilet_indoor').sum()):,}")

    pts = gpd.read_file(GPKG, layer="poi_points")
    print(f"[merge] poi_points before: {len(pts):,} ({pts.crs})")
    if "src_id" not in pts.columns:
        pts["src_id"] = pd.NA
    old_amap = pts["source_layer"] == SOURCE
    print(f"[merge] replacing {int(old_amap.sum()):,} previous {SOURCE} rows")
    pts = pts[~old_amap].copy()

    df = df.sort_values(["adname", "name", "poi_id"]).reset_index(drop=True)
    new = gpd.GeoDataFrame(
        {
            "poi_id": next_ids(pts["poi_id"], len(df)),
            "source_layer": SOURCE,
            "source_group": "amenities",
            "geom_kind": "point",
            "osm_id": pd.NA,
            "fclass": df["fclass_new"].to_numpy(),
            "category": "政府公共",
            "name": df["name"].fillna("").to_numpy(),
            "area_m2": np.nan,
            "in_boundary": True,
            "src_id": df["poi_id"].to_numpy(),
        },
        geometry=gpd.GeoSeries(shapely.points(df["lng"], df["lat"]), crs=4326),
        crs=4326,
    )
    # column order must match the existing layer
    cols = [c for c in pts.columns if c != "geometry"]
    new = new[cols + ["geometry"]]

    # QA: how many Amap toilets sit on top of a toilet already in poi.gpkg?
    old_toilets = pts[pts["fclass"] == "toilet"].to_crs(CRS)
    new_m = new.to_crs(CRS)
    dups = 0
    if len(old_toilets):
        tree = cKDTree(np.column_stack([old_toilets.geometry.x, old_toilets.geometry.y]))
        dist, _ = tree.query(np.column_stack([new_m.geometry.x, new_m.geometry.y]), k=1)
        dups = int((dist < 20).sum())
        print(f"[merge] {dups:,} Amap toilets within 20 m of an existing toilet POI")

    merged = gpd.GeoDataFrame(
        pd.concat([pts, new], ignore_index=True), geometry="geometry", crs=pts.crs
    )
    pyogrio.write_dataframe(merged, GPKG, layer="poi_points", driver="GPKG")
    print(f"[merge] poi_points after: {len(merged):,} -> {GPKG}")
    print("[merge] layers:", [x[0] for x in pyogrio.list_layers(GPKG)])

    summary = {
        "crawled": int(total_crawled),
        "in_boundary": in_boundary_n,
        "merged": int(len(new)),
        "public_toilet": int((new["fclass"] == "toilet").sum()),
        "indoor_toilet": int((new["fclass"] == "toilet_indoor").sum()),
        "dropped_venue_pois": int(len(dropped)),
        "near_existing_toilet_20m": dups,
        "poi_points_total": int(len(merged)),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "amap_toilet_merge_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
