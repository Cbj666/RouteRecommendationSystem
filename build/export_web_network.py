"""给前端准备两样东西：

1) 能自己画的路网 GeoJSON（两个尺度）
   - segments_city.geojson      中心城 9.6×6.0 km，全量 8,425 段（约 1.6 MB）
   - segments_arterial.geojson  全市主干（trunk/primary/secondary/tertiary/motorway，约 6 MB）
2) 几份「假装是后端返回」的环线响应，直接放进前端 mocks/

python build/export_web_network.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
from shapely import set_precision

ROOT = Path(__file__).resolve().parents[1]
SEG = ROOT / "data" / "processed" / "running" / "v1" / "segments.gpkg"
OUT = ROOT / "data" / "output" / "running" / "v1" / "web"
MOCKS = ROOT / "frontend" / "app" / "src" / "mocks"

CITY_BBOX = (114.305, 30.508, 114.405, 30.562)
ARTERIAL = ["motorway", "trunk", "primary", "secondary", "tertiary"]

ORIGINS = [
    ("loops_5km_wuda", 114.3547, 30.5342, 5000),
    ("loops_3km_wuda", 114.3547, 30.5342, 3000),
    ("loops_10km_wuda", 114.3547, 30.5342, 10000),
    ("loops_5km_donghu", 114.4120, 30.5560, 5000),
]


def dump_geojson(gdf: gpd.GeoDataFrame, path: Path, nd: int = 4) -> None:
    # 源表里有空几何（退化路段），且 set_precision 遇到退化线段也会吐 None。
    # 不剔掉的话 GeoJSON 会出现 "geometry": null，浏览器端一读就崩。
    g = gdf.copy()
    g["geometry"] = [set_precision(x, 10 ** (-nd)) for x in g.geometry]
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    payload = json.loads(g.to_json(drop_id=True, ensure_ascii=False))
    # 兜底：to_json 仍可能把退化几何写成 null，浏览器端会直接崩，这里再过一遍。
    feats = [f for f in payload["features"] if f.get("geometry")]
    payload["features"] = feats
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"  {path.name:26s} {path.stat().st_size / 1024 / 1024:5.2f} MB  {len(feats):>6,} 段")


def export_network(seg: gpd.GeoDataFrame) -> None:
    keep = ["score", "grade", "fclass", "geometry"]

    city = seg.cx[CITY_BBOX[0]:CITY_BBOX[2], CITY_BBOX[1]:CITY_BBOX[3]][keep].copy()
    city["score"] = city["score"].round(0).astype(int)
    print(f"中心城 {len(city):,} 段")
    dump_geojson(city, OUT / "segments_city.geojson")

    art = seg[seg["fclass"].isin(ARTERIAL)][keep].copy()
    art["score"] = art["score"].round(0).astype(int)
    print(f"全市主干 {len(art):,} 段")
    dump_geojson(art, OUT / "segments_arterial.geojson")


def export_routes() -> None:
    sys.path.insert(0, str(ROOT / "backend"))
    from app import running

    g = running.load_or_build()
    MOCKS.mkdir(parents=True, exist_ok=True)
    for name, lng, lat, target in ORIGINS:
        loops = running.generate_loops(
            g, lng, lat, target_m=target,
            prefs={"green": 1.0, "safe": 1.0, "flat": 0.6},
            max_candidates=8,
        )
        fc = running.to_geojson(g, loops[:3], name=name)
        p = MOCKS / f"{name}.json"
        p.write_text(
            json.dumps(json.loads(json.dumps(fc, default=float)), ensure_ascii=False),
            encoding="utf-8",
        )
        best = loops[0]
        print(
            f"  {p.name:24s} {p.stat().st_size / 1024:6.1f} KB  "
            f"{len(loops[:3])} 条  首条 {best['length_m']:.0f} m / {best['score']:.1f} 分"
        )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    seg = gpd.read_file(SEG, layer="segments").to_crs(4326)
    export_network(seg)

    # 整市全量：给「不想依赖后端又要看全城」的场合预备，约 30 MB，默认也导出。
    if "--no-all" not in sys.argv:
        keep = ["score", "grade", "fclass", "geometry"]
        allseg = seg[keep].copy()
        allseg["score"] = allseg["score"].round(0).astype(int)
        print("全市全量")
        dump_geojson(allseg, OUT / "segments_all.geojson")

    print("路线 mock：")
    export_routes()


if __name__ == "__main__":
    main()
