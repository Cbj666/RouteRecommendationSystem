"""剔除落在水体（长江/湖泊）里的起点，重算排名并重出热点图。"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))

import demo_hotspots as demo  # noqa: E402

OUT = ROOT / "data" / "output" / "running" / "v1" / "demo"
HUBEI = ROOT / "data" / "raw" / "hubei" / "hubei-261013-free-OpenMap" / "hubei.gpkg"
BBOX = (114.17, 30.45, 114.48, 30.65)


def water_mask():
    poly = gpd.read_file(HUBEI, layer="gis_osm_water_a_free", bbox=BBOX).to_crs(32650)
    line = gpd.read_file(HUBEI, layer="gis_osm_waterways_free", bbox=BBOX).to_crs(32650)
    parts = list(poly.geometry) + [g.buffer(35.0) for g in line.geometry]
    return unary_union(parts)


def main() -> None:
    df = pd.read_csv(OUT / "hotspots.csv", encoding="utf-8-sig")
    mask = water_mask().buffer(-120.0)   # 向内收 120 m：只剔除真正在水中央的点，保留岸边/堤上的点

    pts = gpd.GeoDataFrame(df, geometry=[Point(xy) for xy in zip(df["lng"], df["lat"])],
                           crs=4326).to_crs(32650)
    inside = pts.geometry.within(mask)

    dropped = df[inside].copy()
    kept = df[~inside].copy().reset_index(drop=True)
    print(f"起点 {len(df)} → 保留 {len(kept)}，剔除 {len(dropped)} 个落在水里的：")
    for _, r in dropped.iterrows():
        print(f"  {r['lng']:.4f}, {r['lat']:.4f}  top3={r['top3']:.1f}")

    kept.to_csv(OUT / "hotspots_kept.csv", index=False, encoding="utf-8-sig")
    demo.plot(kept, title=False)

    # 复制到 presentation，供 PPT 直接取用
    import shutil
    dst = ROOT / "presentation" / "热点图.png"
    shutil.copyfile(OUT / "fig_hotspots.png", dst)
    print("副本 →", dst)


if __name__ == "__main__":
    main()
