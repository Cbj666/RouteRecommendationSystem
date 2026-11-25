# -*- coding: utf-8 -*-
"""HTTP 图层所需的只读数据缓存模块。

所属模块：数据访问与内存缓存层。

作用：为前端地图提供评分路段、水体与绿地、运动场馆三类数据。首访时读取
原始文件，之后复用内存中的 GeoDataFrame，每个请求只执行范围过滤和 GeoJSON
序列化。导入本模块不会立即读取文件；文件缺失或损坏时抛出
``DatasetUnavailable``，由 API 层转换为 503 响应。

统一坐标系统：EPSG:4326（WGS84）。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import Point

from . import paths

# 跑步评分数据目录与前端轻量地图图层目录
RUN = paths.DATA / "processed" / "running" / "v1"
WEB = paths.OUTPUT / "running" / "v1" / "web"

# 地图数据源：评分路段、水绿面、运动场馆、公共厕所
SEGMENTS_GPKG = RUN / "segments.gpkg"
WATER_GREEN_GEOJSON = WEB / "water_green.geojson"
POI_CSV = RUN / "amap_sport_poi.csv"
TOILET_CSV = RUN / "amap_toilet_poi.csv"

# 热点页的离线分析产物：全城 2 km 网格（build_hotspot_grid.py 生成）
HOTSPOT_JSON = paths.OUTPUT / "running" / "v1" / "hotspot" / "grid.json"

# 未显式传入 bbox 时使用的默认路段视口，与原型展示范围一致
DEFAULT_SEGMENT_BBOX = (114.305, 30.508, 114.405, 30.562)

# 路段接口在 detail=basic 时返回的常用评分字段
BASIC_SEGMENT_FIELDS = [
    "osm_id", "fclass", "name", "length_m", "score", "grade",
    "s_safety", "s_green", "s_slope", "s_cross", "s_fac", "s_air",
    "no2_ugm3", "pm25_ugm3",
]

# 设施点接口返回的字段
POI_FIELDS = [
    "poi_id", "name", "type", "typecode", "address", "adname",
    "tel", "in_boundary",
]

# 公共厕所接口字段；accessible 由类型/名称中的无障碍关键词派生
TOILET_FIELDS = POI_FIELDS + ["accessible"]

# 高德厕所数据中只有公共厕所/洗手间属于本系统要展示的设施
TOILET_PATTERN = "公共厕所|洗手间"

# 与评分口径一致，默认从地图设施层剔除的室内休闲娱乐类型
EXCLUDED_POI_PATTERN = "台球|棋牌|游戏|歌舞|夜总会|网吧|KTV"

# 六维权重与分档线：从 score_summary.json 读，避免字段说明与评分口径脱节。
# 读不到时退回当前定版口径（v5，2026-11-17），不让一个文档字段拖垮导入。
_WEIGHT_FALLBACK = {"safety": 0.36, "green": 0.26, "slope": 0.06,
                    "cross": 0.15, "fac": 0.06, "air": 0.11}
_BINS_FALLBACK = [35, 50, 65, 80]


def _scoring_meta() -> tuple[dict[str, float], list[int]]:
    """返回（六维权重、分档内线），来源 ``score_summary.json``。"""
    try:
        payload = json.loads((RUN / "score_summary.json").read_text(encoding="utf-8"))
        weights = {k: float(v) for k, v in payload["weights"].items()}
        bins = [int(b) for b in payload.get("grade_bins", _BINS_FALLBACK)]
        return weights, bins
    except Exception:  # noqa: BLE001 - 说明性字段缺失时退回定版口径
        return dict(_WEIGHT_FALLBACK), list(_BINS_FALLBACK)


_W, _BINS = _scoring_meta()

# 路段字段的中文说明，供 /api/layers 返回机器可读数据目录
SEGMENT_FIELD_LABELS = {
    "osm_id": "OSM way id",
    "fclass": "道路类型（OSM fclass）",
    "name": "路名",
    "length_m": "长度（米）",
    "walk_group": "步行组：foot / street",
    "in_boundary": "中点是否在市界内",
    "slope_mean_pct": "长度加权平均坡度（%）",
    "elev_gain_m": "正向累计爬升（米）",
    "tree_share": "120 m 窗口树冠覆盖率（0–1）",
    "green_share": "120 m 窗口绿地覆盖率（0–1）",
    "d_green_m": "到最近绿地距离（米）；null = 超出搜索半径",
    "d_water_m": "到最近水体距离（米）；null = 超出搜索半径",
    "d_main_m": "到最近主干道距离（米）；null = 超出搜索半径",
    "d_fac_m": "到最近设施距离（米）",
    "cross_200m": "200 m 内路口数",
    "fac_500m": "500 m 内设施数（参考值）",
    "no2_ugm3": "年均 NO₂（µg/m³，CHAP 2024）",
    "pm25_ugm3": "年均 PM2.5（µg/m³，CHAP 2024；只展示，不进评分）",
    "s_safety": f"安全子分 0–100（权重 {_W['safety']:.2f}）",
    "s_green": f"绿化子分 0–100（权重 {_W['green']:.2f}）",
    "s_slope": f"坡度子分 0–100（权重 {_W['slope']:.2f}）",
    "s_cross": f"过街子分 0–100（权重 {_W['cross']:.2f}）",
    "s_fac": f"设施子分 0–100（权重 {_W['fac']:.2f}）",
    "s_air": f"空气子分 0–100（权重 {_W['air']:.2f}）",
    "score": f"综合分 0–100（六维加权和，权重合计 {sum(_W.values()):.2f}）",
    "grade": ("等级：" + " / ".join(
        [f"{lab} <{_BINS[0]}" if i == 0 else
         (f"{lab} ≥{_BINS[-1]}" if i == len(_BINS) else
          f"{lab} {_BINS[i - 1]}–{_BINS[i]}")
         for i, lab in enumerate(["差", "一般", "较好", "好", "很好"])])),
}

# 水体与绿地图层字段说明
WATER_GREEN_FIELD_LABELS = {
    "kind": "面类型：water / green",
}

# 设施点字段说明
POI_FIELD_LABELS = {
    "poi_id": "高德 POI id",
    "name": "名称",
    "type": "三级分类，多标签用 | 连接",
    "typecode": "高德类型编码",
    "address": "地址",
    "adname": "区名",
    "tel": "电话（多为空）",
    "in_boundary": "是否在武汉市界内",
}

TOILET_FIELD_LABELS = {
    **POI_FIELD_LABELS,
    "accessible": "是否包含无障碍/残障洗手间关键词",
}


class DatasetUnavailable(RuntimeError):
    """数据源文件缺失、为空或无法解析时抛出的异常。"""


# 已加载图层缓存；键为 segments、water_green、pois
_cache: dict[str, gpd.GeoDataFrame] = {}

# 首访并发保护锁，避免多个请求同时重复加载同一图层
_lock = threading.Lock()


def _read_once(key: str, loader: Any) -> gpd.GeoDataFrame:
    """按图层键只加载一次，并用双重检查锁避免并发首访重复读取。"""
    if key in _cache:
        return _cache[key]
    with _lock:
        if key not in _cache:
            _cache[key] = loader()
        return _cache[key]


def _require(path: Path, hint: str) -> Path:
    """确认数据文件存在；不存在时生成包含构建提示的异常。"""
    if not path.exists():
        try:
            shown = path.relative_to(paths.PROJECT)
        except ValueError:
            shown = path
        raise DatasetUnavailable(f"{shown} 不存在；{hint}")
    return path


def _ensure_wgs84(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """确保 GeoDataFrame 使用 EPSG:4326。"""
    if gdf.crs is None:
        return gdf.set_crs(4326)
    if gdf.crs.to_epsg() != 4326:
        return gdf.to_crs(4326)
    return gdf


def _json_safe(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """把 NaN 和正负无穷转换为 ``None``，保证输出是浏览器可解析的 JSON。

    距离字段常用 ``inf`` 表示搜索半径内没有目标；``Infinity`` 不是合法
    JSON 数字，因此必须转换为 ``null``。
    """
    geom = gdf.geometry.name
    for col in gdf.columns:
        if col == geom:
            continue
        series = gdf[col]
        if pd.api.types.is_float_dtype(series.dtype):
            bad = series.isna() | np.isinf(series)
        else:
            bad = series.isna()
        if bool(bad.any()):
            gdf[col] = series.astype(object).where(~bad, None)
    return gdf


def _load_segments() -> gpd.GeoDataFrame:
    """读取并校验评分路段图层。"""
    path = _require(SEGMENTS_GPKG, "请先运行 backend/scripts/build_running_dataset.py")
    try:
        gdf = gpd.read_file(path, layer="segments")
    except Exception as exc:  # noqa: BLE001 - surface a useful 503 message
        raise DatasetUnavailable(f"读取 {path.name} 失败：{exc}") from exc
    if len(gdf) == 0:
        raise DatasetUnavailable(f"{path.name} 的 segments 图层为空")
    gdf = _ensure_wgs84(gdf)
    if "osm_id" not in gdf.columns:
        raise DatasetUnavailable(f"{path.name} 缺少 osm_id 字段")
    return _json_safe(gdf)


def _load_water_green() -> gpd.GeoDataFrame:
    """读取并校验水体与绿地多边形图层。"""
    path = _require(
        WATER_GREEN_GEOJSON,
        "请先运行 build/export_web_assets.py 生成 water_green.geojson",
    )
    try:
        gdf = gpd.read_file(path)
    except Exception as exc:  # noqa: BLE001
        raise DatasetUnavailable(f"读取 {path.name} 失败：{exc}") from exc
    if "kind" not in gdf.columns:
        raise DatasetUnavailable(f"{path.name} 缺少 kind 字段")
    gdf = _ensure_wgs84(gdf)
    return _json_safe(gdf)


def _load_pois() -> gpd.GeoDataFrame:
    """读取高德 POI CSV，并转换为 WGS84 点图层。"""
    path = _require(POI_CSV, "请先运行 backend/scripts/fetch_amap_sport_poi.py")
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except Exception as exc:  # noqa: BLE001
        raise DatasetUnavailable(f"读取 {path.name} 失败：{exc}") from exc

    missing = {"poi_id", "name", "type", "lng", "lat"} - set(df.columns)
    if missing:
        raise DatasetUnavailable(f"{path.name} 缺少字段：{', '.join(sorted(missing))}")
    df = df.dropna(subset=["lng", "lat"]).copy()
    for col in ("poi_id", "name", "type", "typecode", "address", "adname", "tel"):
        if col in df.columns:
            df[col] = df[col].fillna("")
    if "in_boundary" in df.columns and df["in_boundary"].dtype == object:
        df["in_boundary"] = (
            df["in_boundary"].astype(str).str.lower().isin(["true", "1", "yes"])
        )

    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["lng"], df["lat"]),
        crs=4326,
    )
    return _json_safe(gdf)


def _load_toilets() -> gpd.GeoDataFrame:
    """读取高德公共厕所 POI，并保留公共厕所/洗手间类型。"""
    path = _require(TOILET_CSV, "请先运行 backend/scripts/fetch_amap_toilet_poi.py")
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except Exception as exc:  # noqa: BLE001
        raise DatasetUnavailable(f"读取 {path.name} 失败：{exc}") from exc

    missing = {"poi_id", "name", "type", "lng", "lat"} - set(df.columns)
    if missing:
        raise DatasetUnavailable(f"{path.name} 缺少字段：{', '.join(sorted(missing))}")
    df = df.dropna(subset=["lng", "lat"]).copy()
    keep = df["type"].fillna("").str.contains(
        TOILET_PATTERN, regex=True, na=False
    )
    df = df[keep].copy()
    if df.empty:
        raise DatasetUnavailable(f"{path.name} 中没有公共厕所/洗手间记录")
    for col in ("poi_id", "name", "type", "typecode", "address", "adname", "tel"):
        if col in df.columns:
            df[col] = df[col].fillna("")
    if "in_boundary" in df.columns and df["in_boundary"].dtype == object:
        df["in_boundary"] = (
            df["in_boundary"].astype(str).str.lower().isin(["true", "1", "yes"])
        )
    text = df["type"].fillna("") + "|" + df["name"].fillna("")
    df["accessible"] = text.str.contains("无障碍|残障", regex=True, na=False)

    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["lng"], df["lat"]),
        crs=4326,
    )
    return _json_safe(gdf)


def segments() -> gpd.GeoDataFrame:
    """返回缓存的评分路段数据。"""
    return _read_once("segments", _load_segments)


def water_green() -> gpd.GeoDataFrame:
    """返回缓存的水体与绿地数据。"""
    return _read_once("water_green", _load_water_green)


def pois() -> gpd.GeoDataFrame:
    """返回缓存的设施点数据。"""
    return _read_once("pois", _load_pois)


def toilets() -> gpd.GeoDataFrame:
    """返回缓存的公共厕所点数据。"""
    return _read_once("toilets", _load_toilets)


# 热点网格 JSON 缓存；文件由 build_hotspot_grid.py 生成，服务端只读不重算
_hotspot: dict[str, Any] | None = None
_hotspot_lock = threading.Lock()


def _load_hotspot() -> dict[str, Any]:
    """读取并校验热点网格产物；缺文件时提示先跑构建脚本。"""
    path = _require(
        HOTSPOT_JSON, "请先运行 backend/scripts/build_hotspot_grid.py"
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise DatasetUnavailable(f"读取 {path.name} 失败：{exc}") from exc
    cells = payload.get("cells")
    if not isinstance(cells, list) or not cells:
        raise DatasetUnavailable(f"{path.name} 的 cells 为空")
    return payload


def hotspot() -> dict[str, Any]:
    """返回缓存的全城 1 km 热点网格（前端 /api/hotspot 的响应体）。"""
    global _hotspot
    if _hotspot is None:
        with _hotspot_lock:
            if _hotspot is None:
                _hotspot = _load_hotspot()
    return _hotspot


# 水体并集用于判断起点是否落在江/湖内部；只构建一次
_water_union = None
_water_lock = threading.Lock()


def water_union():
    """返回全部水体多边形的并集；用于起点合法性检查。"""
    global _water_union
    if _water_union is None:
        with _water_lock:
            if _water_union is None:
                gdf = water_green()
                geoms = [
                    geom
                    for geom, kind in zip(gdf.geometry, gdf["kind"])
                    if kind == "water" and geom is not None and not geom.is_empty
                ]
                _water_union = shapely.union_all(geoms) if geoms else None
    return _water_union


def point_in_water(lng: float, lat: float) -> bool:
    """判断 WGS84 点是否落在水体多边形内部。"""
    union = water_union()
    return bool(union is not None and union.contains(Point(lng, lat)))


def clip(gdf: gpd.GeoDataFrame, bbox: tuple[float, float, float, float] | None):
    """返回与 bbox 相交的要素；bbox 为空时返回全部数据。"""
    if bbox is None:
        return gdf
    min_lng, min_lat, max_lng, max_lat = bbox
    return gdf.cx[min_lng:max_lng, min_lat:max_lat]


def segment_fields(detail: str = "basic") -> list[str]:
    """按 basic 或 full 口径返回路段属性字段。"""
    gdf = segments()
    if detail == "full":
        return [c for c in gdf.columns if c != gdf.geometry.name]
    return [c for c in BASIC_SEGMENT_FIELDS if c in gdf.columns]


def poi_fields() -> list[str]:
    """返回当前数据中实际存在的设施点输出字段。"""
    gdf = pois()
    return [c for c in POI_FIELDS if c in gdf.columns]


def toilet_fields() -> list[str]:
    """返回当前数据中实际存在的公共厕所输出字段。"""
    gdf = toilets()
    return [c for c in TOILET_FIELDS if c in gdf.columns]


def feature_collection(
    gdf: gpd.GeoDataFrame,
    *,
    total: int | None = None,
    truncated: bool = False,
    bbox: tuple[float, float, float, float] | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """把 GeoDataFrame 序列化为带 total、truncated、bbox 等外层字段的 GeoJSON。

    使用 GeoDataFrame 自带序列化以减少大图层开销，并通过字符串拼接把附加
    元数据放入顶层对象，避免整体二次解析。
    """
    body = gdf.to_json(drop_id=True)
    meta: dict[str, Any] = dict(extra or {})
    if total is not None:
        meta["total"] = int(total)
    meta["truncated"] = bool(truncated)
    if bbox is not None:
        meta["bbox"] = [float(v) for v in bbox]
    prefix = json.dumps(meta, ensure_ascii=False)
    return "{" + prefix[1:-1] + ", " + body[1:]


def status() -> dict[str, int | None]:
    """返回已缓存图层的行数，不主动触发加载；供健康检查使用。"""
    return {
        name: (int(len(_cache[name])) if name in _cache else None)
        for name in ("segments", "water_green", "pois", "toilets")
    }


def preload() -> dict[str, str]:
    """在服务启动阶段预热缓存，并返回各图层的加载错误信息。"""
    errors: dict[str, str] = {}
    for name, loader in (
        ("segments", segments),
        ("water_green", water_green),
        ("pois", pois),
        ("toilets", toilets),
    ):
        try:
            loader()
        except Exception as exc:  # noqa: BLE001 - a bad layer must not kill the API
            errors[name] = f"{type(exc).__name__}: {exc}"
    return errors
