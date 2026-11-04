"""导「前端可直接用」的 GeoJSON，并评估入库体积。

python build/export_web_assets.py                  # 只导水绿底图（小，建议入库）
python build/export_web_assets.py --with-segments   # 连整市评分路网一起导（大，约 35 MB）

输出在 data/output/running/v1/web/，不会自动入库。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SEG_GPKG = ROOT / "data" / "processed" / "running" / "v1" / "segments.gpkg"
HUBEI = ROOT / "data" / "raw" / "hubei" / "hubei-261013-free-OpenMap" / "hubei.gpkg"
OUT = ROOT / "data" / "output" / "running" / "v1" / "web"
BBOX = (113.70, 30.00, 115.10, 31.40)

GREEN = {
    "forest", "scrub", "park", "grass", "meadow", "recreation_ground",
    "orchard", "vineyard", "village_green", "heath",
}


def dump(gdf: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(gdf.to_json(drop_id=True, ensure_ascii=False))
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"  {path.name:24s} {path.stat().st_size / 1024 / 1024:6.2f} MB  {len(gdf):,} 个要素")


def round_geom(gdf: gpd.GeoDataFrame, ndigits: int = 5) -> gpd.GeoDataFrame:
    from shapely import set_precision

    out = gdf.copy()
    out["geometry"] = [set_precision(g, 10 ** (-ndigits)) for g in out.geometry]
    return out


def export_water_green() -> None:
    water = gpd.read_file(HUBEI, layer="gis_osm_water_a_free", bbox=BBOX).to_crs(4326)
    water = water[["fclass", "geometry"]].rename(columns={"fclass": "kind"})
    water["kind"] = "water"

    land = gpd.read_file(HUBEI, layer="gis_osm_landuse_a_free", bbox=BBOX).to_crs(4326)
    land = land[land["fclass"].isin(GREEN)]
    land = land[["fclass", "geometry"]].rename(columns={"fclass": "kind"})
    land["kind"] = "green"

    both = gpd.GeoDataFrame(pd.concat([water, land], ignore_index=True), crs=4326)
    area_km2 = both.to_crs(32650).geometry.area / 1e6
    keep = ((both["kind"] == "water") & (area_km2 >= 0.03)) | (
        (both["kind"] == "green") & (area_km2 >= 0.02)
    )
    both = both[keep].copy()
    both["geometry"] = both.geometry.simplify(0.0002, preserve_topology=True)
    both = both[~both.geometry.is_empty]
    print(
        f"水绿底图：水体 {int((both['kind'] == 'water').sum()):,} / "
        f"绿地 {int((both['kind'] == 'green').sum()):,}"
        f"（原始 {len(water):,} / {len(land):,}，已按面积过滤 + 简化）"
    )
    dump(round_geom(both), OUT / "water_green.geojson")


def export_segments() -> None:
    seg = gpd.read_file(SEG_GPKG, layer="segments").to_crs(4326)
    seg = seg[["osm_id", "score", "grade", "length_m", "geometry"]].copy()
    seg["score"] = seg["score"].round(1)
    seg["length_m"] = seg["length_m"].round(0).astype(int)
    print(f"评分路网：{len(seg):,} 段")
    dump(round_geom(seg), OUT / "segments.geojson")


def main() -> None:
    export_water_green()
    if "--with-segments" in sys.argv:
        export_segments()
    print("输出目录：", OUT)


if __name__ == "__main__":
    main()
