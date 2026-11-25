# -*- coding: utf-8 -*-
r"""城市慢跑后端 HTTP 接口模块。

所属模块：接口层。

作用：启动 FastAPI 服务，在进程内加载跑步图与地图数据，并向前端提供
路段、面状底图、设施点、公共厕所、图层目录、评分说明，以及环线和
A→B 单行线推荐接口。前端不再直接读取 ``data/`` 下的文件。

主要接口：
    GET  /health                    服务和数据加载状态
    GET  /api/segments              按范围返回评分路段
    GET  /api/segments/{osm_id}     返回单条路段的全部属性
    GET  /api/water-green           返回水体与绿地多边形
    GET  /api/pois                  返回运动场馆点
    GET  /api/facilities            /api/pois 的兼容别名
    GET  /api/toilets               返回公共厕所点
    GET  /api/places/search         代理高德关键字搜索（返回 WGS84 坐标）
    GET  /api/layers                返回机器可读的图层目录
    GET  /api/meta                  返回权重、分数统计与数据口径
    POST /api/routes                生成环线或 A→B 单行线
    POST /api/loops                 /api/routes 的环线兼容别名

坐标统一使用 WGS84（EPSG:4326）。GeoJSON 响应在客户端支持时会启用 gzip。

启动：
    .\.venv\Scripts\python.exe -m uvicorn app.api:app --app-dir backend --port 8000
文档：
    http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import json
import logging
import math
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from shapely.geometry import mapping

from . import amap, datasets, paths, running

logger = logging.getLogger(__name__)

# 进程级共享状态；服务启动时写入图、数据集加载时间和可用状态
STATE: dict[str, Any] = {}

# GeoJSON 接口的 OpenAPI 响应声明
GEOJSON_RESPONSE = {
    200: {
        "description": "GeoJSON FeatureCollection / Feature（WGS84）",
        "content": {"application/geo+json": {}},
    }
}

# 路线接口的边界参数。42 km 对应需求 NFR-04（1–42 km）。
MIN_TARGET_M = 1000.0
MAX_TARGET_M = 42000.0
MAX_SNAP_M = 500.0
DEFAULT_PREFS = {"green": 1.0, "safe": 1.0, "flat": 0.6}
LENGTH_TOLERANCE = (0.85, 1.15)

# 六个评分维度的来源、代理性质与局限，供 /api/meta 做数据说明。
SCORING_DIMENSIONS = [
    {
        "key": "safety",
        "field": "s_safety",
        "label": "安全",
        "weight_key": "safety",
        "source": "OSM 道路等级 + 距主干道距离",
        "proxy": "用道路等级和主干道距离代理机动车干扰",
        "limitation": "没有路段车流量，不能等同于真实暴露",
    },
    {
        "key": "green",
        "field": "s_green",
        "label": "绿化",
        "weight_key": "green",
        "source": "ESA WorldCover 10 m 树冠 + 到绿地距离",
        "proxy": "树冠覆盖率和绿地邻近度",
        "limitation": "不识别单排行道树和季节变化",
    },
    {
        "key": "slope",
        "field": "s_slope",
        "label": "坡度",
        "weight_key": "slope",
        "source": "SRTM 1″ 高程，150 m 平滑后求梯度",
        "proxy": "路段平均坡度",
        "limitation": "城区精度约 ±1 个百分点，不反映单点路面",
    },
    {
        "key": "cross",
        "field": "s_cross",
        "label": "过街",
        "weight_key": "cross",
        "source": "200 m 内道路网络路口数",
        "proxy": "路口密度代理过街次数",
        "limitation": "不等同于实际等红灯次数",
    },
    {
        "key": "fac",
        "field": "s_fac",
        "label": "设施",
        "weight_key": "fac",
        "source": "高德运动场馆 + 高德公共厕所 + OSM 公园/便利店等设施点",
        "proxy": "到最近设施点的步行距离指数衰减",
        "limitation": "远城区设施覆盖较稀",
    },
    {
        "key": "air",
        "field": "s_air",
        "label": "空气",
        "weight_key": "air",
        "source": "CHAP 1 km 年均 NO₂（2024）",
        "proxy": "区域年均空气污染水平",
        "limitation": "只做区域校正，不能辨别同区域路段",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """管理应用生命周期：启动时加载图和图层，关闭时释放进程状态。"""
    t0 = time.time()
    STATE["graph"] = running.load_or_build()
    STATE["loaded_at"] = time.time()
    print(
        f"[api] run graph loaded in {time.time() - t0:.1f}s: "
        f"{STATE['graph'].n:,} nodes",
        flush=True,
    )
    # 预建最近邻 KD 树，避免首个路线请求额外承担建树开销
    STATE["graph"].warm()

    t1 = time.time()
    errors = datasets.preload()
    STATE["datasets_loaded_at"] = time.time()
    print(
        f"[api] datasets loaded in {time.time() - t1:.1f}s: {datasets.status()}",
        flush=True,
    )
    for name, message in errors.items():
        print(f"[api] WARNING dataset {name} unavailable: {message}", flush=True)

    # 预建水体并集，避免首个路线请求额外承担 shapely 并集开销
    try:
        datasets.water_union()
    except Exception as exc:  # noqa: BLE001 - 预热失败不能阻塞服务启动
        print(f"[api] WARNING water union unavailable: {exc}", flush=True)

    yield
    STATE.clear()


# FastAPI 应用实例；模块级对象供 uvicorn 直接加载
app = FastAPI(
    title="城市慢跑适宜性 API",
    description=(
        "路段评分、水绿底图、运动场馆、公共厕所、闭合环线与 A→B 单行线。"
        "坐标一律 WGS84；数据由后端统一提供，前端不再直接读取 data/ 下的文件。"
    ),
    version="0.4.0",
    lifespan=lifespan,
)

# 先注册 GZip、再注册 CORS：CORS 位于外层，异常响应也能带跨域头。
# Starlette 只会压缩达到 minimum_size 的响应体。
app.add_middleware(GZipMiddleware, minimum_size=1024)

# TODO(卡片2): 生产环境请把允许来源改成前端实际域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(datasets.DatasetUnavailable)
async def _dataset_unavailable(
    _request: Request, exc: datasets.DatasetUnavailable
) -> JSONResponse:
    """把数据文件缺失或损坏转换为 503，而不是算法异常的 500。"""
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """访问服务根路径时跳转到 Swagger 文档。"""
    return RedirectResponse(url="/docs", status_code=307)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """响应浏览器自动请求的站点图标，避免日志出现无意义的 404。"""
    return Response(status_code=204)


def _graph() -> running.RunGraph:
    """获取已加载的跑步图；直接导入应用时按需补加载。"""
    g = STATE.get("graph")
    if g is None:  # 未执行 lifespan（例如直接 import 测试）
        g = running.load_or_build()
        STATE["graph"] = g
    return g


class RouteRequest(BaseModel):
    """环线 / 单行线生成请求。

    - ``target_m`` 支持 1–42 km（NFR-04）。
    - ``mode=loop``：闭合环线，起点即终点。
    - ``mode=oneway``：A→B 单行线；可给 ``end_lng/end_lat`` 指定终点，
      不给时由系统在目标距离附近自动选择终点。
    """

    lng: float = Field(..., description="起点经度（WGS84）")
    lat: float = Field(..., description="起点纬度（WGS84）")
    target_m: float = Field(
        5000,
        ge=MIN_TARGET_M,
        le=MAX_TARGET_M,
        description="目标距离（米），1–42 km",
    )
    mode: Literal["loop", "oneway"] = Field(
        "loop", description="loop=闭合环线；oneway=A→B 单行线"
    )
    prefs: dict[str, float] = Field(
        default_factory=lambda: dict(DEFAULT_PREFS),
        description="偏好权重：green / safe / flat，可只给其中若干项",
    )
    max_candidates: int = Field(
        8, ge=2, le=16, description="最多返回候选数（oneway 指定终点时固定 1 条）"
    )
    end_lng: float | None = Field(None, description="单行线终点经度；与 end_lat 同时给")
    end_lat: float | None = Field(None, description="单行线终点纬度；与 end_lng 同时给")


class LoopRequest(BaseModel):
    """``/api/loops`` 兼容请求，字段与旧版保持一致。"""

    lng: float = Field(..., description="起点经度（WGS84）")
    lat: float = Field(..., description="起点纬度（WGS84）")
    target_m: float = Field(
        5000, ge=MIN_TARGET_M, le=MAX_TARGET_M, description="目标距离（米）"
    )
    prefs: dict[str, float] = Field(
        default_factory=lambda: dict(DEFAULT_PREFS),
        description="偏好权重：green / safe / flat，可只给其中若干项",
    )
    max_candidates: int = Field(8, ge=2, le=16)


# ---------------------------------------------------------------------------
# 通用辅助函数
# ---------------------------------------------------------------------------
# 经纬度范围元组：(min_lng, min_lat, max_lng, max_lat)
BBox = tuple[float, float, float, float]


def _bbox(
    min_lng: float | None,
    min_lat: float | None,
    max_lng: float | None,
    max_lat: float | None,
    *,
    default: BBox | None = None,
) -> BBox | None:
    """校验四个范围参数：要么全部提供，要么全部省略并使用默认值。"""
    values = (min_lng, min_lat, max_lng, max_lat)
    if all(value is None for value in values):
        return default
    if any(value is None for value in values):
        raise HTTPException(
            status_code=422,
            detail="bbox 四个参数必须同时提供：min_lng / min_lat / max_lng / max_lat",
        )
    assert min_lng is not None and min_lat is not None
    assert max_lng is not None and max_lat is not None
    if not (min_lng < max_lng and min_lat < max_lat):
        raise HTTPException(
            status_code=422,
            detail="bbox 不合法：要求 min_lng < max_lng 且 min_lat < max_lat",
        )
    return (float(min_lng), float(min_lat), float(max_lng), float(max_lat))


def _geojson(body: str, *, max_age: int = 60) -> Response:
    """构建带缓存策略的 GeoJSON HTTP 响应。"""
    return Response(
        content=body,
        media_type="application/geo+json",
        headers={"Cache-Control": f"public, max-age={max_age}"},
    )


def _select(gdf: Any, fields: list[str] | tuple[str, ...]) -> Any:
    """选择指定属性列，并确保活动几何列始终保留。"""
    geometry = gdf.geometry.name
    columns = [name for name in fields if name in gdf.columns]
    if geometry not in columns:
        columns.append(geometry)
    return gdf[columns]


def _plain(value: Any) -> Any:
    """把 NumPy 标量和非有限浮点数转换为 JSON 可安全输出的值。"""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return None if math.isnan(number) or math.isinf(number) else number
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    return value


def _relative(path: Path) -> str:
    """尽量返回相对项目根目录的路径，便于接口稳定展示数据来源。"""
    try:
        return path.relative_to(paths.PROJECT).as_posix()
    except ValueError:
        return path.as_posix()


def _file_meta(path: Path) -> dict[str, Any]:
    """返回数据文件的相对路径、大小和 UTC 更新时间。"""
    if not path.exists():
        return {}
    stat = path.stat()
    return {
        "source": _relative(path),
        "size_bytes": stat.st_size,
        "updated_at": datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
    }


def _bounds(gdf: Any) -> list[float] | None:
    """返回图层的经纬度总范围；空图层返回 None。"""
    if len(gdf) == 0:
        return None
    return [round(float(value), 6) for value in gdf.total_bounds]


def _geometry_types(gdf: Any) -> list[str]:
    """返回图层中出现的全部几何类型名称。"""
    return sorted({str(value) for value in gdf.geom_type.dropna().unique()})


def _field_docs(
    gdf: Any, names: list[str], labels: dict[str, str]
) -> list[dict[str, str]]:
    """生成字段名、中文标签和数据类型说明，供图层目录接口使用。"""
    return [
        {
            "name": name,
            "label": labels.get(name, name),
            "dtype": str(gdf[name].dtype),
        }
        for name in names
        if name in gdf.columns
    ]


def _pois_response(
    bbox: BBox | None,
    *,
    kinds: Literal["sport", "all"],
    exclude_leisure: bool,
    limit: int,
) -> Response:
    """按范围、类别和数量限制生成设施点 GeoJSON 响应。"""
    gdf = datasets.pois()
    subset = datasets.clip(gdf, bbox)
    if kinds == "sport":
        subset = subset[subset["type"].fillna("").str.startswith("体育", na=False)]
    if exclude_leisure:
        drop = subset["type"].fillna("").str.contains(
            datasets.EXCLUDED_POI_PATTERN, regex=True, na=False
        )
        subset = subset[~drop]

    total = len(subset)
    subset = subset.head(limit)
    subset = _select(subset, datasets.poi_fields())
    body = datasets.feature_collection(
        subset,
        total=total,
        truncated=total > limit,
        bbox=bbox,
        extra={"kinds": kinds, "exclude_leisure": exclude_leisure},
    )
    return _geojson(body, max_age=300)


def _check_prefs(prefs: dict[str, float]) -> dict[str, float]:
    """校验偏好键和权重，返回只含合法键的浮点字典。"""
    if not prefs:
        return dict(DEFAULT_PREFS)
    allowed = set(running.PREF_KEYS)
    unknown = sorted(set(prefs) - allowed)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                f"不支持的偏好键：{', '.join(unknown)}；"
                f"允许的键为 {', '.join(sorted(allowed))}"
            ),
        )
    clean: dict[str, float] = {}
    for key, value in prefs.items():
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise HTTPException(
                status_code=422,
                detail=f"偏好权重 {key}={value} 不合法：必须是大于等于 0 的有限数",
            )
        clean[key] = number
    if sum(clean.values()) <= 0:
        raise HTTPException(
            status_code=422, detail="偏好权重之和必须大于 0，至少给一个正权重"
        )
    return clean


def _check_point(lng: float, lat: float, label: str) -> tuple[int, float]:
    """校验一个用户点并吸附到路网。

    依次检查经纬度、武汉市数据范围、水体和路网吸附距离；失败时返回带
    可操作提示的 422，而不是让算法在几百公里外生成一条空路线。
    """
    if not (math.isfinite(lng) and math.isfinite(lat)):
        raise HTTPException(status_code=422, detail=f"{label}经纬度不是有限数")
    if not (-180.0 <= lng <= 180.0 and -90.0 <= lat <= 90.0):
        raise HTTPException(
            status_code=422, detail=f"{label}经纬度超出合法范围：({lng}, {lat})"
        )

    bounds = datasets.segments().total_bounds  # minx, miny, maxx, maxy
    margin = 0.02
    if not (
        bounds[0] - margin <= lng <= bounds[2] + margin
        and bounds[1] - margin <= lat <= bounds[3] + margin
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                f"{label}不在武汉市数据范围内（当前路网约 "
                f"{bounds[0]:.3f}–{bounds[2]:.3f}E，"
                f"{bounds[1]:.3f}–{bounds[3]:.3f}N）"
            ),
        )

    if datasets.point_in_water(lng, lat):
        raise HTTPException(
            status_code=422,
            detail=f"{label}位于水体内部，请选择靠近道路的岸边位置",
        )

    graph = _graph()
    node, snap = graph.nearest(lng, lat)
    if snap > MAX_SNAP_M:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{label}距最近道路 {snap:.0f} m，超过 {MAX_SNAP_M:.0f} m 上限；"
                "请把点移到道路附近后重试"
            ),
        )
    return node, snap


def _route_catalog() -> dict[str, Any]:
    """返回路线接口的机器可读参数说明。"""
    return {
        "endpoint": "/api/routes",
        "alias": "/api/loops",
        "modes": ["loop", "oneway"],
        "params": [
            "lng",
            "lat",
            "target_m",
            "mode",
            "prefs",
            "max_candidates",
            "end_lng",
            "end_lat",
        ],
        "target_m": {
            "min": MIN_TARGET_M,
            "max": MAX_TARGET_M,
            "recommended": [3000, 5000, 10000],
            "unit": "m",
        },
        "prefs": {
            "allowed": ["green", "safe", "flat"],
            "default": dict(DEFAULT_PREFS),
            "range": "每个权重 >= 0，总和 > 0",
        },
        "max_candidates": {"min": 2, "max": 16, "default": 8},
        "length_tolerance": {
            "low": LENGTH_TOLERANCE[0],
            "high": LENGTH_TOLERANCE[1],
            "note": "target_ok=false 时仍返回路线，但应在界面提示实际距离偏差",
        },
        "speed_mps": running.RUN_SPEED_MPS,
        "max_snap_m": MAX_SNAP_M,
    }


def _build_routes(req: RouteRequest) -> dict:
    """把请求参数转成路线生成调用，并组装 GeoJSON 顶层元数据。"""
    if req.mode == "loop":
        if req.end_lng is not None or req.end_lat is not None:
            raise HTTPException(
                status_code=422, detail="loop 模式不接受 end_lng/end_lat；单行线请用 mode=oneway"
            )
    elif (req.end_lng is None) != (req.end_lat is None):
        raise HTTPException(
            status_code=422, detail="end_lng 与 end_lat 必须同时提供，或同时省略"
        )

    prefs = _check_prefs(req.prefs)
    origin, origin_snap = _check_point(req.lng, req.lat, "起点")
    graph = _graph()

    destination: int | None = None
    destination_snap: float | None = None
    if req.mode == "oneway" and req.end_lng is not None and req.end_lat is not None:
        destination, destination_snap = _check_point(req.end_lng, req.end_lat, "终点")

    if req.mode == "loop":
        found = running.generate_loops(
            graph,
            req.lng,
            req.lat,
            req.target_m,
            prefs=prefs,
            max_candidates=req.max_candidates,
            origin=origin,
            origin_snap_m=origin_snap,
        )
    else:
        found = running.generate_oneway(
            graph,
            req.lng,
            req.lat,
            req.target_m,
            prefs=prefs,
            max_candidates=req.max_candidates,
            end_lng=req.end_lng,
            end_lat=req.end_lat,
            origin=origin,
            origin_snap_m=origin_snap,
            destination=destination,
            destination_snap_m=destination_snap,
        )

    body = running.to_geojson(graph, found)
    body.update(
        {
            "dataset": "running/v1",
            "crs": "EPSG:4326",
            "mode": req.mode,
            "target_m": round(float(req.target_m), 1),
            "count": len(found),
            "origin": {
                "lng": round(float(req.lng), 6),
                "lat": round(float(req.lat), 6),
                "snap_m": round(float(origin_snap), 1),
                "snapped_lng": round(float(graph.lng[origin]), 6),
                "snapped_lat": round(float(graph.lat[origin]), 6),
            },
        }
    )
    if destination is not None:
        assert req.end_lng is not None and req.end_lat is not None
        assert destination_snap is not None
        body["destination"] = {
            "lng": round(float(req.end_lng), 6),
            "lat": round(float(req.end_lat), 6),
            "snap_m": round(float(destination_snap), 1),
            "snapped_lng": round(float(graph.lng[destination]), 6),
            "snapped_lat": round(float(graph.lat[destination]), 6),
        }

    if not found:
        if req.mode == "loop":
            message = (
                "该起点在目标距离附近没有合适的折点，无法形成闭合环线；"
                "请调整起点或目标距离"
            )
        else:
            message = (
                "该起点在目标距离附近没有合适的终点，无法形成 A→B 路线；"
                "请调整起点、目标距离或指定终点"
            )
        body.update(
            {
                "reason": "no_candidates",
                "message": message,
                "suggestions": [
                    "把目标距离改为 3 / 5 / 10 km 等常用档位",
                    "把起点移到道路附近",
                    "若已指定终点，确认终点与目标距离大致匹配",
                ],
            }
        )
    elif req.mode == "oneway" and destination is not None and not all(
        feature["properties"].get("target_ok", False) for feature in body["features"]
    ):
        body["notice"] = (
            "A→B 模式以指定终点为准，实际距离与目标距离存在偏差；"
            "请查看每条路线的 length_m 与 length_error_pct"
        )
    return body


def _toilets_response(
    bbox: BBox | None, *, accessible: bool | None, limit: int
) -> Response:
    """按范围返回公共厕所点；accessible 为 None 时不过滤。"""
    gdf = datasets.toilets()
    subset = datasets.clip(gdf, bbox)
    if accessible is not None:
        subset = subset[subset["accessible"] == accessible]
    total = len(subset)
    subset = subset.head(limit)
    subset = _select(subset, datasets.toilet_fields())
    body = datasets.feature_collection(
        subset,
        total=total,
        truncated=total > limit,
        bbox=bbox,
        extra={"accessible": accessible},
    )
    return _geojson(body, max_age=300)


# ---------------------------------------------------------------------------
# HTTP 接口
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    g = _graph()
    return {
        "status": "ok",
        "nodes": g.n,
        "edges": int(g.csr_len.nnz),
        "graph_loaded_at": STATE.get("loaded_at"),
        "datasets": datasets.status(),
        "datasets_loaded_at": STATE.get("datasets_loaded_at"),
    }


@app.get(
    "/api/segments",
    response_class=Response,
    responses=GEOJSON_RESPONSE,
    summary="bbox 内的评分路段",
)
def segments(
    min_lng: float | None = Query(None, description="bbox 西边界；不传则用默认视口"),
    min_lat: float | None = Query(None, description="bbox 南边界；不传则用默认视口"),
    max_lng: float | None = Query(None, description="bbox 东边界；不传则用默认视口"),
    max_lat: float | None = Query(None, description="bbox 北边界；不传则用默认视口"),
    limit: int = Query(20000, ge=1, le=60000, description="最多返回要素数"),
    detail: Literal["basic", "full"] = Query(
        "basic",
        description="basic=14 个评分字段；full=全部 26 个属性（inf 已转 null）",
    ),
) -> Response:
    """返回 bbox 内的路段；不传 bbox 时返回原型视口（约 8,000 段）。

    先按 bbox 过滤再 ``head(limit)``；``truncated=true`` 表示还有更多。
    ``detail=full`` 会带坡度、树冠、距离、空气等原始指标。
    """
    bbox = _bbox(
        min_lng, min_lat, max_lng, max_lat, default=datasets.DEFAULT_SEGMENT_BBOX
    )
    gdf = datasets.segments()
    subset = datasets.clip(gdf, bbox)
    total = len(subset)
    subset = subset.head(limit)
    subset = _select(subset, datasets.segment_fields(detail))
    body = datasets.feature_collection(
        subset,
        total=total,
        truncated=total > limit,
        bbox=bbox,
        extra={"detail": detail},
    )
    return _geojson(body, max_age=60)


@app.get(
    "/api/segments/{osm_id}",
    responses=GEOJSON_RESPONSE,
    summary="单条路段的全部属性",
)
def segment_detail(osm_id: int) -> JSONResponse:
    """按 ``osm_id`` 返回一个完整 Feature；不存在返回 404。"""
    gdf = datasets.segments()
    hit = gdf[gdf["osm_id"] == osm_id]
    if hit.empty:
        raise HTTPException(status_code=404, detail=f"osm_id={osm_id} 不存在")
    row = hit.iloc[0]
    properties = {
        key: _plain(value)
        for key, value in row.items()
        if key != gdf.geometry.name
    }
    return JSONResponse(
        content={
            "type": "Feature",
            "properties": properties,
            "geometry": mapping(row.geometry),
        },
        media_type="application/geo+json",
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.get(
    "/api/water-green",
    response_class=Response,
    responses=GEOJSON_RESPONSE,
    summary="水体 / 绿地底图",
)
def water_green(
    min_lng: float | None = Query(None, description="bbox 西边界"),
    min_lat: float | None = Query(None, description="bbox 南边界"),
    max_lng: float | None = Query(None, description="bbox 东边界"),
    max_lat: float | None = Query(None, description="bbox 北边界"),
    kind: Literal["water", "green", "all"] = Query(
        "all", description="water / green / all"
    ),
    simplify: float = Query(
        0.0,
        ge=0.0,
        le=0.001,
        description="几何简化容差（度）；0=不简化，0.0002 约 22 m",
    ),
    limit: int = Query(10000, ge=1, le=10000, description="最多返回要素数"),
) -> Response:
    """返回水体 / 绿地多边形；不传 bbox 时返回全市 3,586 个面。"""
    bbox = _bbox(min_lng, min_lat, max_lng, max_lat)
    gdf = datasets.water_green()
    subset = datasets.clip(gdf, bbox)
    if kind != "all":
        subset = subset[subset["kind"] == kind]

    total = len(subset)
    subset = subset.head(limit)
    if simplify > 0 and len(subset):
        subset = subset.copy()
        subset["geometry"] = subset.geometry.simplify(
            simplify, preserve_topology=True
        )

    body = datasets.feature_collection(
        subset,
        total=total,
        truncated=total > limit,
        bbox=bbox,
        extra={"kind": kind},
    )
    return _geojson(body, max_age=300)


@app.get(
    "/api/pois",
    response_class=Response,
    responses=GEOJSON_RESPONSE,
    summary="运动场馆 POI",
)
def pois(
    min_lng: float | None = Query(None, description="bbox 西边界"),
    min_lat: float | None = Query(None, description="bbox 南边界"),
    max_lng: float | None = Query(None, description="bbox 东边界"),
    max_lat: float | None = Query(None, description="bbox 北边界"),
    kinds: Literal["sport", "all"] = Query(
        "all",
        description="sport=运动场馆；all=当前全部（同一数据源）；support 尚未接入",
    ),
    exclude_leisure: bool = Query(
        True,
        description="剔除台球/棋牌/游戏/歌舞/夜总会/网吧/KTV；false 返回全量 5,137",
    ),
    limit: int = Query(10000, ge=1, le=10000, description="最多返回要素数"),
) -> Response:
    """返回高德运动场馆点；默认与评分口径一致，剔除休闲娱乐类。"""
    bbox = _bbox(min_lng, min_lat, max_lng, max_lat)
    return _pois_response(
        bbox, kinds=kinds, exclude_leisure=exclude_leisure, limit=limit
    )


@app.get(
    "/api/facilities",
    response_class=Response,
    responses=GEOJSON_RESPONSE,
    summary="设施点（兼容别名，等价 /api/pois）",
)
def facilities(
    min_lng: float = Query(..., description="bbox 西边界"),
    min_lat: float = Query(..., description="bbox 南边界"),
    max_lng: float = Query(..., description="bbox 东边界"),
    max_lat: float = Query(..., description="bbox 北边界"),
    kinds: Literal["sport", "all"] = Query(
        "sport", description="sport | all；support 尚未接入"
    ),
    limit: int = Query(10000, ge=1, le=10000, description="最多返回要素数"),
) -> Response:
    """旧版前端使用的端点，保留以便平滑迁移；建议改用 ``/api/pois``。"""
    bbox = _bbox(min_lng, min_lat, max_lng, max_lat)
    return _pois_response(
        bbox, kinds=kinds, exclude_leisure=True, limit=limit
    )


@app.get(
    "/api/toilets",
    response_class=Response,
    responses=GEOJSON_RESPONSE,
    summary="公共厕所点（可按无障碍筛选）",
)
def toilets(
    min_lng: float | None = Query(None, description="bbox 西边界；四参需同时给"),
    min_lat: float | None = Query(None, description="bbox 南边界"),
    max_lng: float | None = Query(None, description="bbox 东边界"),
    max_lat: float | None = Query(None, description="bbox 北边界"),
    accessible: bool | None = Query(
        None, description="true=只看无障碍厕所；false=只看普通；省略=全部"
    ),
    limit: int = Query(10000, ge=1, le=10000, description="最多返回要素数"),
) -> Response:
    """返回高德公共厕所 POI；已剔除停车场出口等噪声。"""
    bbox = _bbox(min_lng, min_lat, max_lng, max_lat)
    try:
        return _toilets_response(bbox, accessible=accessible, limit=limit)
    except datasets.DatasetUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get(
    "/api/places/search",
    summary="高德地点搜索（后端代理，返回 WGS84 坐标）",
)
def place_search(
    q: str = Query(
        ...,
        min_length=1,
        max_length=64,
        description="搜索关键词，例如「东湖绿道」「武汉大学」「汉口江滩」",
    ),
    limit: int = Query(
        8, ge=1, le=amap.MAX_LIMIT, description="返回地点数，1–20，默认 8"
    ),
) -> JSONResponse:
    """代理高德关键字搜索，前端不接触高德 Key。

    高德返回 GCJ-02，这里统一转成项目使用的 WGS84 再返回；`amap_lng/amap_lat`
    保留高德原始坐标仅用于排错。相同关键词在服务端缓存 5 分钟。

    错误：未配置 Key → 503；高德业务错误/不可用 → 502；请求超时 → 504。
    """
    keywords = q.strip()
    if not keywords:
        raise HTTPException(status_code=422, detail="搜索关键词不能为空")

    try:
        places = amap.search_places(keywords, limit=limit)
    except amap.AmapConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except amap.AmapTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except amap.AmapUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return JSONResponse(
        content={
            "provider": "amap",
            "query": keywords,
            "count": len(places),
            "places": places,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/layers", summary="数据目录（字段、数量、来源、更新时间）")
def layers() -> dict:
    """前端可用它判断图层是否就绪、字段含义，以及数据文件更新时间。"""
    # 各图层独立构建目录；单个图层失败只标记为不可用，不影响其它图层。
    catalog: dict[str, Any] = {}

    try:
        gdf = datasets.segments()
        catalog["segments"] = {
            "available": True,
            "endpoint": "/api/segments",
            "params": ["min_lng", "min_lat", "max_lng", "max_lat", "limit", "detail"],
            "count": int(len(gdf)),
            "bbox": _bounds(gdf),
            "geometry_type": _geometry_types(gdf),
            "basic_fields": [
                name for name in datasets.BASIC_SEGMENT_FIELDS if name in gdf.columns
            ],
            "fields": _field_docs(
                gdf,
                datasets.segment_fields("full"),
                datasets.SEGMENT_FIELD_LABELS,
            ),
            "notes": (
                "detail=basic 返回 14 个评分字段；detail=full 返回全部属性。"
                " d_green_m / d_water_m / d_main_m 的 null 表示超出搜索半径。"
            ),
            **_file_meta(datasets.SEGMENTS_GPKG),
        }
    except datasets.DatasetUnavailable as exc:
        catalog["segments"] = {
            "available": False,
            "endpoint": "/api/segments",
            "error": str(exc),
        }

    try:
        gdf = datasets.water_green()
        catalog["water_green"] = {
            "available": True,
            "endpoint": "/api/water-green",
            "params": [
                "min_lng",
                "min_lat",
                "max_lng",
                "max_lat",
                "kind",
                "simplify",
                "limit",
            ],
            "count": int(len(gdf)),
            "kinds": {
                kind: int((gdf["kind"] == kind).sum())
                for kind in ("water", "green")
            },
            "bbox": _bounds(gdf),
            "geometry_type": _geometry_types(gdf),
            "fields": _field_docs(
                gdf, ["kind"], datasets.WATER_GREEN_FIELD_LABELS
            ),
            **_file_meta(datasets.WATER_GREEN_GEOJSON),
        }
    except datasets.DatasetUnavailable as exc:
        catalog["water_green"] = {
            "available": False,
            "endpoint": "/api/water-green",
            "error": str(exc),
        }

    try:
        gdf = datasets.pois()
        kept = gdf[
            ~gdf["type"].fillna("").str.contains(
                datasets.EXCLUDED_POI_PATTERN, regex=True, na=False
            )
        ]
        catalog["pois"] = {
            "available": True,
            "endpoint": "/api/pois",
            "params": [
                "min_lng",
                "min_lat",
                "max_lng",
                "max_lat",
                "kinds",
                "exclude_leisure",
                "limit",
            ],
            "count": int(len(gdf)),
            "count_after_default_filter": int(len(kept)),
            "bbox": _bounds(gdf),
            "geometry_type": _geometry_types(gdf),
            "fields": _field_docs(gdf, datasets.poi_fields(), datasets.POI_FIELD_LABELS),
            "notes": (
                "默认剔除台球/棋牌/游戏/歌舞/夜总会/网吧/KTV；"
                "?exclude_leisure=false 返回全量。"
            ),
            **_file_meta(datasets.POI_CSV),
        }
    except datasets.DatasetUnavailable as exc:
        catalog["pois"] = {
            "available": False,
            "endpoint": "/api/pois",
            "error": str(exc),
        }

    try:
        gdf = datasets.toilets()
        catalog["toilets"] = {
            "available": True,
            "endpoint": "/api/toilets",
            "params": [
                "min_lng",
                "min_lat",
                "max_lng",
                "max_lat",
                "accessible",
                "limit",
            ],
            "count": int(len(gdf)),
            "accessible_count": int(gdf["accessible"].sum()),
            "bbox": _bounds(gdf),
            "geometry_type": _geometry_types(gdf),
            "fields": _field_docs(
                gdf, datasets.toilet_fields(), datasets.TOILET_FIELD_LABELS
            ),
            "notes": "保留 type 含“公共厕所/洗手间”的 POI；accessible 由名称/类型关键词推断。",
            **_file_meta(datasets.TOILET_CSV),
        }
    except datasets.DatasetUnavailable as exc:
        catalog["toilets"] = {
            "available": False,
            "endpoint": "/api/toilets",
            "error": str(exc),
        }

    return {
        "dataset": "running/v1",
        "crs": "EPSG:4326",
        "default_segment_bbox": list(datasets.DEFAULT_SEGMENT_BBOX),
        "routes": _route_catalog(),
        "search": {
            "provider": "amap",
            "endpoint": "/api/places/search",
            "params": ["q", "limit"],
            "configured": amap.configured(),
            "crs": "EPSG:4326",
            "notes": (
                "后端代理高德 Web 服务；高德 GCJ-02 已转 WGS84。"
                "Key 只从服务端 .env 的 GAODE_KEY 读取，不下发浏览器。"
            ),
        },
        "layers": catalog,
    }


@app.post(
    "/api/routes",
    summary="生成环线或 A→B 单行线（含指标与可解释子分）",
)
def routes(req: RouteRequest) -> Response:
    """按 ``mode`` 生成环线或单行线。

    - ``mode=loop``：起点即终点，返回闭合环线候选；
    - ``mode=oneway``：A→B 单行线，可指定终点，否则按目标距离自动选终点。

    返回 GeoJSON FeatureCollection，顶层附带 ``mode / target_m / count /
    origin``；没有候选时返回空 features，并给出 ``reason / message /
    suggestions``，前端应直接展示而不是留白。
    """
    try:
        payload = _build_routes(req)
        return JSONResponse(
            content=payload,
            media_type="application/geo+json",
            headers={"Cache-Control": "no-store"},
        )
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        logger.exception(
            "路线生成失败：mode=%s lng=%s lat=%s target_m=%s",
            req.mode,
            req.lng,
            req.lat,
            req.target_m,
        )
        raise HTTPException(
            status_code=500,
            detail="路线生成失败，请调整起点、目标距离或偏好后重试",
        ) from None


@app.post("/api/loops")
def loops(req: LoopRequest) -> Response:
    """生成环线；``/api/routes`` 的旧版兼容别名。"""
    return routes(
        RouteRequest(
            lng=req.lng,
            lat=req.lat,
            target_m=req.target_m,
            mode="loop",
            prefs=req.prefs,
            max_candidates=req.max_candidates,
        )
    )


@app.get("/api/meta")
def meta() -> dict:
    """数据版本与口径，前端用来显示“数据说明”。"""
    summary = running.RUN / "score_summary.json"
    payload = (
        json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else {}
    )
    weights = payload.get("weights") or {}
    dimensions = [
        {**dimension, "weight": weights.get(dimension["weight_key"])}
        for dimension in SCORING_DIMENSIONS
    ]
    return {
        "dataset": "running/v1",
        "weights": payload.get("weights"),
        "grade_bins": payload.get("grade_bins"),
        "grade_labels": payload.get("grade_labels"),
        "score_stats": payload.get("score"),
        "notes": payload.get("notes", []),
        "speed_mps": running.RUN_SPEED_MPS,
        "scoring": {
            "dimensions": dimensions,
            "weights": payload.get("weights"),
            "grade_bins": payload.get("grade_bins"),
            "grade_labels": payload.get("grade_labels"),
            "note": (
                "需求文档 FR-10 写“差<45”，当前数据集按 score_summary.json 的 "
                "grade_bins 生成 grade；接口与地图以实际返回的 bins 为准。"
            ),
        },
        "route_options": _route_catalog(),
        "data": {
            "segments": "/api/segments",
            "segment_detail": "/api/segments/{osm_id}",
            "water_green": "/api/water-green",
            "pois": "/api/pois",
            "facilities": "/api/facilities",
            "toilets": "/api/toilets",
            "place_search": "/api/places/search",
            "routes": "/api/routes",
            "loops": "/api/loops",
            "catalog": "/api/layers",
            "crs": "EPSG:4326",
            "default_segment_bbox": list(datasets.DEFAULT_SEGMENT_BBOX),
        },
    }
