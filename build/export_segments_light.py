"""给前端导出「能自己画路网」的路网 GeoJSON，并对比几种压缩策略的体积。

python build/export_segments_light.py

产物都写到 data/output/running/v1/web/，不会自动入库。
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
SEG = ROOT / "data" / "processed" / "running" / "v1" / "segments.gpkg"
OUT = ROOT / "data" / "output" / "running" / "v1" / "web"

BANDS = [("差", 1), ("一般", 2), ("较好", 3), ("好", 4), ("很好", 5)]


def dump(obj: dict, name: str) -> None:
    p = OUT / name
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  {name:28s} {p.stat().st_size / 1024 / 1024:6.2f} MB  {len(obj['features']):>7,} 个要素")


def round_coords(geom, nd: int = 4):
    from shapely import set_precision

    return set_precision(geom, 10 ** (-nd))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    seg = gpd.read_file(SEG, layer="segments").to_crs(4326)
    print(f"原始 {len(seg):,} 段")

    # A：每段一个 feature，只留 grade + 分数整数，坐标 4 位小数
    a = seg[["grade", "score", "geometry"]].copy()
    a["score"] = a["score"].round(0).astype(int)
    a["geometry"] = [round_coords(g, 4) for g in a.geometry]
    dump(json.loads(a.to_json(drop_id=True, ensure_ascii=False)), "segments_by_feature.geojson")

    # B：按五档合并成 5 个 MultiLineString，只留档位
    b = seg[["grade", "geometry"]].copy()
    b["geometry"] = [round_coords(g, 4) for g in b.geometry]
    feats = []
    for label, idx in BANDS:
        part = b[b["grade"] == label]
        if part.empty:
            continue
        merged = part.geometry.union_all()
        feats.append(
            {
                "type": "Feature",
                "properties": {"grade": label, "band": idx},
                "geometry": merged.__geo_interface__,
            }
        )
        print(f"    {label}: {len(part):,} 段 → {merged.geom_type}")
    dump({"type": "FeatureCollection", "features": feats}, "segments_by_band.geojson")


if __name__ == "__main__":
    main()
