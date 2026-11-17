# -*- coding: utf-8 -*-
r"""FastAPI service for the running-suitability prototype.

The Vue app does **not** read files from ``data/``.  This process owns the
three map layers and exposes them as GeoJSON:

    GET  /health                     graph + dataset status
    GET  /api/segments               scored road segments (bbox + limit)
    GET  /api/segments/{osm_id}      one segment, all attributes
    GET  /api/water-green            water / green polygons
    GET  /api/pois                   sport POIs (points)
    GET  /api/facilities             compat alias of /api/pois
    GET  /api/layers                 machine-readable catalog
    GET  /api/meta                   weights / score stats
    POST /api/loops                  loop route generation

All coordinates are WGS84 (EPSG:4326).  Responses are ``application/geo+json``
and gzip-compressed by Starlette when the client asks for it.

启动：
    .\.venv\Scripts\python.exe -m uvicorn app.api:app --app-dir backend --port 8000
文档：
    http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import json
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

from . import datasets, paths, running

STATE: dict[str, Any] = {}

GEOJSON_RESPONSE = {
    200: {
        "description": "GeoJSON FeatureCollection / Feature（WGS84）",
        "content": {"application/geo+json": {}},
    }
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.time()
    STATE["graph"] = running.load_or_build()
    STATE["loaded_at"] = time.time()
    print(
        f"[api] run graph loaded in {time.time() - t0:.1f}s: "
        f"{STATE['graph'].n:,} nodes",
        flush=True,
    )

    t1 = time.time()
    errors = datasets.preload()
    STATE["datasets_loaded_at"] = time.time()
    print(
        f"[api] datasets loaded in {time.time() - t1:.1f}s: {datasets.status()}",
        flush=True,
    )
    for name, message in errors.items():
        print(f"[api] WARNING dataset {name} unavailable: {message}", flush=True)

    yield
    STATE.clear()


app = FastAPI(
    title="城市慢跑适宜性 API",
    description=(
        "路段评分、水绿底图、运动场馆、环线推荐。坐标一律 WGS84；"
        "数据由后端统一提供，前端不再直接读取 data/ 下的文件。"
    ),
    version="0.2.0",
    lifespan=lifespan,
)

# Add GZip first, CORS second: CORS is the outer layer, so 4xx/5xx responses
# still carry CORS headers.  Starlette only compresses bodies >= minimum_size.
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
    """A missing/corrupt data file is a server-side data problem, not a 500."""
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Open http://127.0.0.1:8000/ and land on the Swagger UI."""
    return RedirectResponse(url="/docs", status_code=307)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Browsers request this automatically; avoid a noisy 404 in the log."""
    return Response(status_code=204)


def _graph() -> running.RunGraph:
    g = STATE.get("graph")
    if g is None:  # 未执行 lifespan（例如直接 import 测试）
        g = running.load_or_build()
        STATE["graph"] = g
    return g


class LoopRequest(BaseModel):
    lng: float = Field(..., description="起点经度（WGS84）")
    lat: float = Field(..., description="起点纬度（WGS84）")
    target_m: float = Field(5000, ge=1000, le=20000, description="目标距离（米）")
    prefs: dict[str, float] = Field(
        default_factory=lambda: {"green": 1.0, "safe": 1.0, "flat": 0.6},
        description="偏好权重：green / safe / flat，可只给其中若干项",
    )
    max_candidates: int = Field(8, ge=2, le=16)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
BBox = tuple[float, float, float, float]


def _bbox(
    min_lng: float | None,
    min_lat: float | None,
    max_lng: float | None,
    max_lat: float | None,
    *,
    default: BBox | None = None,
) -> BBox | None:
    """Validate the four query params; all-or-none, or fall back to default."""
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
    return Response(
        content=body,
        media_type="application/geo+json",
        headers={"Cache-Control": f"public, max-age={max_age}"},
    )


def _select(gdf: Any, fields: list[str] | tuple[str, ...]) -> Any:
    """Select attribute columns plus the active geometry column."""
    geometry = gdf.geometry.name
    columns = [name for name in fields if name in gdf.columns]
    if geometry not in columns:
        columns.append(geometry)
    return gdf[columns]


def _plain(value: Any) -> Any:
    """Convert numpy scalars and non-finite floats to JSON-safe values."""
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
    try:
        return path.relative_to(paths.PROJECT).as_posix()
    except ValueError:
        return path.as_posix()


def _file_meta(path: Path) -> dict[str, Any]:
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
    if len(gdf) == 0:
        return None
    return [round(float(value), 6) for value in gdf.total_bounds]


def _geometry_types(gdf: Any) -> list[str]:
    return sorted({str(value) for value in gdf.geom_type.dropna().unique()})


def _field_docs(
    gdf: Any, names: list[str], labels: dict[str, str]
) -> list[dict[str, str]]:
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


# ---------------------------------------------------------------------------
# endpoints
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


@app.get("/api/layers", summary="数据目录（字段、数量、来源、更新时间）")
def layers() -> dict:
    """前端可用它判断图层是否就绪、字段含义，以及数据文件更新时间。"""
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

    return {
        "dataset": "running/v1",
        "crs": "EPSG:4326",
        "default_segment_bbox": list(datasets.DEFAULT_SEGMENT_BBOX),
        "layers": catalog,
    }


@app.post("/api/loops")
def loops(req: LoopRequest) -> dict:
    """生成环线（GeoJSON FeatureCollection + 指标）。

    TODO(卡片2):
      - 结果缓存（同一 (lng, lat, target) 复用）
      - 超时保护：极端参数下限制候选数
      - 返回 `origin_snap_m` 超过 100 m 时给出提示
    """
    g = _graph()
    try:
        found = running.generate_loops(
            g,
            req.lng,
            req.lat,
            req.target_m,
            prefs=req.prefs,
            max_candidates=req.max_candidates,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"环线生成失败: {exc}") from exc

    if not found:
        return {
            "type": "FeatureCollection",
            "features": [],
            "message": "该起点在目标距离附近没有合适的折点，请换个距离或起点",
        }

    return running.to_geojson(g, found)


@app.get("/api/meta")
def meta() -> dict:
    """数据版本与口径，前端用来显示“数据说明”。"""
    summary = running.RUN / "score_summary.json"
    payload = (
        json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else {}
    )
    return {
        "dataset": "running/v1",
        "weights": payload.get("weights"),
        "score_stats": payload.get("score"),
        "notes": payload.get("notes", []),
        "speed_mps": running.RUN_SPEED_MPS,
        "data": {
            "segments": "/api/segments",
            "segment_detail": "/api/segments/{osm_id}",
            "water_green": "/api/water-green",
            "pois": "/api/pois",
            "facilities": "/api/facilities",
            "catalog": "/api/layers",
            "crs": "EPSG:4326",
            "default_segment_bbox": list(datasets.DEFAULT_SEGMENT_BBOX),
        },
    }
