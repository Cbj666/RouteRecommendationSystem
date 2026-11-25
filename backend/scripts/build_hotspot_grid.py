# -*- coding: utf-8 -*-
"""把全城评分路段聚合为等距热点网格（静态分析产物）。

所属模块：离线数据构建层。

作用：读取 ``segments.gpkg`` 的六维评分，按默认 2 km（经度 0.0208°、纬度 0.018°）
网格做**按路段长度加权**的聚合，输出前端热点页直接渲染的 JSON 与供 GIS
核对用的 GeoJSON。产物写入 ``data/output/running/v1/hotspot/``，由
``backend/app/api.py`` 的 ``GET /api/hotspot`` 读取并提供给前端，前端不直接
访问 ``data/`` 目录。

网格边长可用 ``--cell-lng/--cell-lat`` 调整（1 km 更细、3 km 更粗），
默认 2 km：全市域约 1,800 格，城市级视野下色块不碎、每格样本也够。

口径：
- 综合分 = 汇总路段 ``score × length_m`` / 汇总长度，与矢量评分口径一致；
- 分档沿用 v2 的 35/50/65/80；
- 热点格 = 综合分 ≥ 65（「好」及以上）且样本长度 ≥ 1000 m，避免单段路撑起一格；
- 格子名称取最近的休闲旅游/交通设施/运动场馆地标，超过 1.2 km 补方位词，
  仅用于展示，不参与评分。

用法：
    python backend/scripts/build_hotspot_grid.py                      # 默认 2 km
    python backend/scripts/build_hotspot_grid.py --cell-lng 0.0104 --cell-lat 0.009   # 1 km
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyogrio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import paths  # noqa: E402

RUN = paths.DATA / "processed" / "running" / "v1"
SEGMENTS = RUN / "segments.gpkg"
POI_GPKG = paths.V1 / "poi.gpkg"
FACILITY_CSV = RUN / "amap_sport_poi.csv"
OUT_DIR = paths.OUTPUT / "running" / "v1" / "hotspot"

# 默认 2 km 网格（经度 0.0208° ≈ 2.0 km，纬度 0.018° ≈ 2.0 km）；
# 城市级视野下 1 km 太碎，2 km 的色块更连贯，每格样本也更足
CELL_LNG = 0.0208
CELL_LAT = 0.018
OUT_JSON_NAME = "grid.json"
OUT_GEO_NAME = "grid.geojson"

GRADE_BINS = [35, 50, 65, 80]
GRADE_LABELS = ["差", "一般", "较好", "好", "很好"]

# 命名用锚点：地标名称里混有大量连锁店/银行，先过滤再取最近点
ANCHOR_BLOCKLIST = re.compile(
    r"银行|超市|便利店|公厕|厕所|停车场|加油站|药店|诊所|医院|酒店|宾馆|"
    r"餐厅|饭店|咖啡|奶茶|快递|菜市场|幼儿园|小学|中学|大学|学院|公司|"
    r"营业厅|网点|支行|ATM"
)
# 公园/水域名称优先作为地标：比商业场馆稳定，也更符合跑步语义
PARK_PATTERN = re.compile(r"公园|广场|湖|湿地|绿道|景区|山|江滩|沙滩|植物园|动物园|体育中心|体育公园")
# 场馆类备选地标；台球/棋牌/游戏等与跑步无关的室内娱乐先排除
VENUE_PATTERN = re.compile(r"运动|健身|游泳|瑜伽|体育馆|体育中心|球场|攀岩|跑步|骑行")
VENUE_BLOCKLIST = re.compile(r"台球|棋牌|游戏|网吧|KTV|夜总会|电玩|密室|剧本|足浴|按摩|会所|棋牌室")

# 命名锚点优先级惩罚（km）：公园 0、交通设施 0.3、休闲点 0.6、场馆 1.5
ANCHOR_PENALTY = np.array([0.0, 0.3, 0.6, 1.5])

# 八个方位，用于给远离锚点的格子补方位词
DIRECTIONS = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]


def grade_of(score: float) -> str:
    """按 v2 分档线返回等级。"""
    for boundary, label in zip(GRADE_BINS, GRADE_LABELS):
        if score < boundary:
            return label
    return GRADE_LABELS[-1]


def load_segments() -> pd.DataFrame:
    """读取评分路段，只保留市界内记录并补上中点经纬度。"""
    gdf = pyogrio.read_dataframe(SEGMENTS, layer="segments")
    if "in_boundary" in gdf.columns:
        gdf = gdf[gdf["in_boundary"].astype(str).str.lower().isin(["true", "1"])]
    if gdf.empty:
        raise SystemExit("segments.gpkg 里没有市界内的评分路段")

    bounds = gdf.bounds
    df = pd.DataFrame(
        {
            "lng": (bounds["minx"] + bounds["maxx"]) / 2.0,
            "lat": (bounds["miny"] + bounds["maxy"]) / 2.0,
            "length_m": gdf["length_m"].astype(float).to_numpy(),
            "score": gdf["score"].astype(float).to_numpy(),
        }
    )
    for dim in ("s_safety", "s_green", "s_slope", "s_cross", "s_fac", "s_air"):
        df[dim] = gdf[dim].astype(float).to_numpy()
    return df


def load_anchors() -> pd.DataFrame:
    """收集命名锚点：公园/景区面、交通设施点、休闲点、运动场馆（带优先级）。"""
    frames: list[pd.DataFrame] = []

    def add(name: pd.Series, lng, lat, kind: int) -> None:
        frames.append(
            pd.DataFrame({"name": name.astype(str), "lng": lng, "lat": lat, "kind": kind})
        )

    areas = pyogrio.read_dataframe(POI_GPKG, layer="poi_areas", columns=["name", "category"])
    areas = areas[(areas["category"] == "休闲旅游") & areas["name"].notna()]
    areas = areas[areas["name"].astype(str).str.contains(PARK_PATTERN, na=False)]
    if len(areas):
        # 地理坐标系下 centroid 会给出警告且不准，先投到 EPSG:32650 再回算
        c = areas.geometry.to_crs(32650).centroid.to_crs(4326)
        add(areas["name"], c.x, c.y, 0)

    points = pyogrio.read_dataframe(
        POI_GPKG, layer="poi_points",
        columns=["name", "category", "source_layer", "geometry"],
    )
    usable = points[
        points["name"].notna() & points["name"].astype(str).str.len().between(2, 20)
    ]
    transit = usable[usable["category"] == "交通设施"]
    if len(transit):
        add(transit["name"], transit.geometry.x, transit.geometry.y, 1)
    leisure = usable[usable["category"] == "休闲旅游"]
    if len(leisure):
        add(leisure["name"], leisure.geometry.x, leisure.geometry.y, 2)

    if FACILITY_CSV.exists():
        venues = pd.read_csv(FACILITY_CSV, encoding="utf-8-sig")
        names = venues["name"].astype(str)
        venues = venues[
            names.str.contains(VENUE_PATTERN, na=False)
            & ~names.str.contains(VENUE_BLOCKLIST, na=False)
            & names.str.len().between(2, 20)
        ]
        add(venues["name"], venues["lng"], venues["lat"], 3)

    anchors = pd.concat(frames, ignore_index=True).dropna()
    anchors["name"] = anchors["name"].str.strip()
    anchors = anchors[~anchors["name"].str.contains(ANCHOR_BLOCKLIST, na=False)]
    anchors = anchors[anchors["name"].str.len() >= 2]
    # 同名锚点可能来自多个来源；同一名称保留优先级最高的一条，避免重复
    anchors = anchors.sort_values("kind", kind="stable").drop_duplicates("name", keep="first")
    return anchors.reset_index(drop=True)


def direction_of(dx: float, dy: float) -> str:
    """把东/北方向位移换算成八方位中文词。"""
    angle = math.degrees(math.atan2(dx, dy)) % 360.0
    return DIRECTIONS[int((angle + 22.5) // 45) % 8]


DIRECTION_SUFFIXES = tuple(sorted(DIRECTIONS, key=len, reverse=True))


def label_cells(cells: pd.DataFrame, anchors: pd.DataFrame) -> pd.DataFrame:
    """给每个格子取地标名：距离 + 类型惩罚取最优；超过 1.2 km 时追加方位。"""
    if anchors.empty:
        cells["name"] = "武汉网格"
        cells["cluster"] = "武汉"
        return cells

    # 用等距圆柱近似算距离：武汉纬度附近 1° 经度≈95.9 km、1° 纬度≈110.9 km
    cos_lat = math.cos(math.radians(float(cells["lat"].mean())))
    ax = anchors["lng"].to_numpy() * cos_lat
    ay = anchors["lat"].to_numpy()
    penalty = ANCHOR_PENALTY[anchors["kind"].to_numpy()]
    names: list[str] = []
    clusters: list[str] = []
    for lng, lat in zip(cells["lng"].to_numpy(), cells["lat"].to_numpy()):
        dx = (ax - lng * cos_lat) * 111.0
        dy = (ay - lat) * 111.0
        dist = np.hypot(dx, dy)
        i = int(np.argmin(dist + penalty))
        anchor_name = str(anchors["name"].iloc[i])[:14]
        clusters.append(anchor_name)
        if dist[i] <= 1.2 or anchor_name.endswith(DIRECTION_SUFFIXES):
            # 地标名本身已带方位（如「乌龙泉南」）时不再叠加后缀
            names.append(anchor_name)
        else:
            names.append(f"{anchor_name}{direction_of(float(dx[i]), float(dy[i]))}")
    cells["name"] = names
    cells["cluster"] = clusters
    return cells


def aggregate(segments: pd.DataFrame, cell_lng: float, cell_lat: float) -> tuple[pd.DataFrame, list[float]]:
    """按网格聚合路段，返回（格子表, 覆盖范围 [minLng, minLat, maxLng, maxLat]）。"""
    lng0 = math.floor(float(segments["lng"].min()) / cell_lng) * cell_lng
    lat0 = math.floor(float(segments["lat"].min()) / cell_lat) * cell_lat
    col = np.floor((segments["lng"].to_numpy() - lng0) / cell_lng).astype(int)
    row = np.floor((segments["lat"].to_numpy() - lat0) / cell_lat).astype(int)

    weighted = segments.copy()
    weighted["w"] = weighted["length_m"].clip(lower=1e-6)
    for col_name in ("score", "s_safety", "s_green", "s_slope", "s_cross", "s_fac", "s_air"):
        weighted[f"w_{col_name}"] = weighted[col_name] * weighted["w"]
    weighted["row"] = row
    weighted["col"] = col

    grouped = weighted.groupby(["row", "col"], sort=True)
    cells = grouped.agg(
        nSeg=("w", "size"),
        lenM=("w", "sum"),
        **{f"w_{c}": (f"w_{c}", "sum") for c in
           ("score", "s_safety", "s_green", "s_slope", "s_cross", "s_fac", "s_air")},
    ).reset_index()

    for c in ("score", "s_safety", "s_green", "s_slope", "s_cross", "s_fac", "s_air"):
        cells[c] = cells[f"w_{c}"] / cells["lenM"]
    cells = cells.drop(columns=[f"w_{c}" for c in
                                ("score", "s_safety", "s_green", "s_slope", "s_cross", "s_fac", "s_air")])

    cells["lng"] = (lng0 + (cells["col"] + 0.5) * cell_lng).round(6)
    cells["lat"] = (lat0 + (cells["row"] + 0.5) * cell_lat).round(6)
    cells["id"] = "G" + cells["row"].astype(str) + "_" + cells["col"].astype(str)
    cells["widthLng"] = round(cell_lng, 6)
    cells["heightLat"] = round(cell_lat, 6)
    cells["score"] = cells["score"].round(2)
    for c in ("s_safety", "s_green", "s_slope", "s_cross", "s_fac", "s_air"):
        cells[c] = cells[c].round(2)

    view = [
        round(lng0, 6),
        round(lat0, 6),
        round(lng0 + (int(cells["col"].max()) + 1) * cell_lng, 6),
        round(lat0 + (int(cells["row"].max()) + 1) * cell_lat, 6),
    ]
    return cells, view


def cell_km(cell_lng: float) -> float:
    """经度跨度换算成公里（武汉纬度 ≈ 30.55°，1° 经度 ≈ 95.9 km）。"""
    return cell_lng * 111.32 * math.cos(math.radians(30.55))


def build_payload(cells: pd.DataFrame, view: list[float], cell_lng: float, cell_lat: float,
                  segments: pd.DataFrame) -> dict:
    """把聚合结果整理成前端 /api/hotspot 的响应结构。"""
    cells["grade"] = cells["score"].map(grade_of)
    cells["isHotspot"] = (cells["score"] >= 65) & (cells["lenM"] >= 1000)

    # 榜单口径：样本长度 ≥ 1 km 才参与排序，避免一格只有几十米路段却排第一
    cells["rank"] = 0
    rankable = cells.index[cells["lenM"] >= 1000]
    order = cells.loc[rankable].sort_values("score", ascending=False).index
    ranks = {idx: i + 1 for i, idx in enumerate(order)}
    cells.loc[rankable, "rank"] = cells.loc[rankable].index.map(ranks)

    records = []
    # 榜单口径下 rank 从 1 开始；样本不足 1 km 的格子 rank=0，排在最后
    ordered = cells.assign(_key=cells["rank"].where(cells["rank"] > 0, 10**6)).sort_values(
        ["_key", "score"], ascending=[True, False]
    )
    for _, r in ordered.iterrows():
        records.append(
            {
                "id": r["id"],
                "name": r["name"],
                "cluster": r["cluster"],
                "lng": float(r["lng"]),
                "lat": float(r["lat"]),
                "widthLng": float(r["widthLng"]),
                "heightLat": float(r["heightLat"]),
                "score": float(r["score"]),
                "grade": r["grade"],
                "rank": int(r["rank"]),
                "nSeg": int(r["nSeg"]),
                "lenM": round(float(r["lenM"]), 1),
                "isHotspot": bool(r["isHotspot"]),
                "subs": {
                    "s_safety": float(r["s_safety"]),
                    "s_green": float(r["s_green"]),
                    "s_slope": float(r["s_slope"]),
                    "s_cross": float(r["s_cross"]),
                    "s_fac": float(r["s_fac"]),
                    "s_air": float(r["s_air"]),
                },
            }
        )

    hotspots = cells[cells["isHotspot"]]
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": str(SEGMENTS.relative_to(paths.PROJECT)).replace("\\", "/"),
        "note": f"{cell_km(cell_lng):.0f} km 网格 · 全城 · 评分按路段长度加权",
        "cell": {"widthLng": round(cell_lng, 6), "heightLat": round(cell_lat, 6)},
        "view": view,
        "summary": {
            "cells": int(len(cells)),
            "hotspots": int(len(hotspots)),
            "totalLengthKm": round(float(cells["lenM"].sum()) / 1000.0, 1),
            "meanScore": round(float((cells["score"] * cells["lenM"]).sum() / cells["lenM"].sum()), 1),
            "maxScore": round(float(cells["score"].max()), 1),
            "hotspotRule": "综合分 ≥ 65（好及以上）且样本长度 ≥ 1000 m",
        },
        "cells": records,
    }


def write_geojson(cells: pd.DataFrame, path: Path, cell_lng: float, cell_lat: float) -> None:
    """输出供 GIS 核对的网格面 GeoJSON（WGS84）。"""
    features = []
    for _, r in cells.iterrows():
        x0 = r["lng"] - cell_lng / 2
        x1 = r["lng"] + cell_lng / 2
        y0 = r["lat"] - cell_lat / 2
        y1 = r["lat"] + cell_lat / 2
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]],
                },
                "properties": {
                    "id": r["id"],
                    "name": r["name"],
                    "cluster": r["cluster"],
                    "score": round(float(r["score"]), 2),
                    "grade": r["grade"],
                    "rank": int(r["rank"]),
                    "n_seg": int(r["nSeg"]),
                    "len_m": round(float(r["lenM"]), 1),
                    "hotspot": bool(r["isHotspot"]),
                },
            }
        )
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="全城热点网格聚合（默认 2 km）")
    parser.add_argument("--cell-lng", type=float, default=CELL_LNG, help="经度跨度（默认 0.0208°≈2 km）")
    parser.add_argument("--cell-lat", type=float, default=CELL_LAT, help="纬度跨度（默认 0.018°≈2 km）")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="输出目录")
    args = parser.parse_args()

    segments = load_segments()
    print(f"评分路段：{len(segments):,} 段，合计 {segments['length_m'].sum() / 1000:,.1f} km")

    anchors = load_anchors()
    print(f"命名锚点：{len(anchors):,} 个")

    cells, view = aggregate(segments, args.cell_lng, args.cell_lat)
    cells = label_cells(cells, anchors)
    payload = build_payload(cells, view, args.cell_lng, args.cell_lat, segments)

    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / OUT_JSON_NAME
    json_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    write_geojson(cells, args.out / OUT_GEO_NAME, args.cell_lng, args.cell_lat)

    summary = payload["summary"]
    print(
        f"网格：{summary['cells']:,} 格（热点 {summary['hotspots']:,} 格），"
        f"覆盖 {summary['totalLengthKm']:,.1f} km，均分 {summary['meanScore']}，最高 {summary['maxScore']}"
    )
    print(f"范围：{view}")
    print(f"已写入 {json_path}（{json_path.stat().st_size / 1024:.0f} KB）")
    print(f"已写入 {args.out / OUT_GEO_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
