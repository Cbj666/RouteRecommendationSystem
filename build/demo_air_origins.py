"""跨区域暴露对比 + NO2 与道路等级的实测关系（演示用）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "build"))

from app import running  # noqa: E402
import demo_routes as D  # noqa: E402

PROC = ROOT / "data" / "processed" / "running" / "v1"
OUT = ROOT / "data" / "output" / "running" / "v1" / "demo"
OUT.mkdir(parents=True, exist_ok=True)
CACHE = PROC / "edge_air_cache.npz"

ORIGINS = [
    ("东湖绿道（湖心岛）", 114.3900, 30.5500),
    ("武汉大学（珞珈山）", 114.3547, 30.5342),
    ("汉口江滩", 114.2950, 30.5850),
    ("青山江滩", 114.4200, 30.6100),
    ("沌口新区", 114.2000, 30.4900),
]


def get_edge_air(g):
    if CACHE.exists():
        z = np.load(CACHE)
        print(f"  命中缓存 {CACHE.name}")
        return {"pm25": z["pm25"], "no2": z["no2"]}
    air = D.air_on_edges(g)
    np.savez_compressed(CACHE, pm25=air["pm25"].astype(np.float32), no2=air["no2"].astype(np.float32))
    print(f"  写入缓存 {CACHE.name}")
    return air


if __name__ == "__main__":
    g = running.load_or_build()
    air = get_edge_air(g)
    prefs = {"green": 1.0, "safe": 1.0, "flat": 0.6}
    pref = running._pref_score(g, prefs)
    cost = running._cost_matrix(g, pref)

    rows = []
    keep = {}
    for name, lng, lat in ORIGINS:
        lp = D.loops_with_air(g, air, lng, lat, 5000, prefs, max_candidates=8)
        if not lp:
            print(f"  {name}: 无候选")
            continue
        r = lp[0]
        keep[name] = lp[0]["nodes"]
        rows.append({"origin": name, "lng": lng, "lat": lat,
                     **{k: r[k] for k in ("length_m", "minutes", "score", "pm25", "no2",
                                          "tree_share", "slope_mean_pct", "facility_m")}})
        print(f"  {name}: {r['length_m']:.0f} m 分 {r['score']:.1f}  "
              f"PM2.5 {r['pm25']:.1f}  NO2 {r['no2']:.1f}  树 {r['tree_share']:.2f}")

    df = pd.DataFrame(rows).sort_values("no2")
    df.to_csv(OUT / "origins_air.csv", index=False, encoding="utf-8-sig")
    print(df[["origin", "no2", "pm25", "score"]].to_string(index=False))
    print(f"  NO2 极差 {df['no2'].max() / df['no2'].min():.2f}×   "
          f"PM2.5 极差 {df['pm25'].max() / df['pm25'].min():.2f}×")
    np.savez_compressed(OUT / "_origin_nodes.npz",
                        **{k.replace("/", "_"): np.array(v, dtype=np.int64) for k, v in keep.items()})

    # ---- NO2 / PM2.5 与道路等级
    seg = gpd.read_file(PROC / "segments.gpkg", layer="segments",
                        columns=["osm_id", "fclass", "length_m"])
    a = pd.read_csv(PROC / "segment_air.csv", encoding="utf-8-sig").drop(columns=["length_m"])
    m = seg.merge(a, on="osm_id", how="left")
    m = m[(m["length_m"] >= 20) & m["no2_ugm3"].notna()]
    group = {
        "trunk": "快速路/高架", "primary": "主干道", "secondary": "次干道",
        "tertiary": "支路", "residential": "居住区道路", "service": "服务性道路",
        "unclassified": "未分类", "footway": "人行道", "path": "小径",
        "cycleway": "自行车道", "pedestrian": "步行街", "track": "田间/土路",
    }
    m["grp"] = m["fclass"].map(group).fillna(m["fclass"])
    stat = (m.groupby("grp")
              .agg(n=("no2_ugm3", "size"), km=("length_m", lambda s: s.sum() / 1000),
                   no2=("no2_ugm3", "median"), no2_q1=("no2_ugm3", lambda s: s.quantile(0.25)),
                   no2_q3=("no2_ugm3", lambda s: s.quantile(0.75)),
                   pm25=("pm25_ugm3", "median"))
              .sort_values("no2", ascending=False))
    stat.to_csv(OUT / "no2_by_class.csv", encoding="utf-8-sig")
    print("\n[NO2 按道路等级]")
    print(stat.round(2).to_string())
    json.dump({"origins": rows, "by_class": stat.round(3).reset_index().to_dict("records")},
              open(OUT / "air_summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)

