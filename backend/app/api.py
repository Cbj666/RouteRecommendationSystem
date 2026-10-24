# -*- coding: utf-8 -*-
"""FastAPI service for the running-suitability prototype.

骨架状态：所有端点都能跑通，但只做了最朴素实现。卡片 2 的认领人负责：
  - 响应缓存 / 限流 / 参数校验（当前只有最基本的 400）
  - `/api/segments` 的几何简化与分页（现在是 bbox 全量）
  - Swagger 文案、错误码规范、并发压测
  - 部署（uvicorn worker 数、反代、CORS 白名单）

启动：
    .\.venv\Scripts\python.exe -m uvicorn app.api:app --app-dir backend --port 8000
文档：
    http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Literal

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import running

STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.time()
    STATE["graph"] = running.load_or_build()
    STATE["loaded_at"] = time.time()
    print(f"[api] run graph loaded in {time.time() - t0:.1f}s: "
          f"{STATE['graph'].n:,} nodes", flush=True)
    yield
    STATE.clear()


app = FastAPI(
    title="城市慢跑适宜性 API",
    description="路段评分、环线推荐、设施查询。坐标一律 WGS84。",
    version="0.1.0",
    lifespan=lifespan,
)

# TODO(卡片2): 生产环境请把允许来源改成前端实际域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _graph() -> running.RunGraph:
    g = STATE.get("graph")
    if g is None:                       # 未执行 lifespan（例如直接 import 测试）
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


@app.get("/health")
def health() -> dict:
    g = _graph()
    return {
        "status": "ok",
        "nodes": g.n,
        "edges": int(g.csr_len.nnz),
        "graph_loaded_at": STATE.get("loaded_at"),
    }


@app.get("/api/segments")
def segments(
    min_lng: float = Query(..., description="bbox 西边界"),
    min_lat: float = Query(..., description="bbox 南边界"),
    max_lng: float = Query(..., description="bbox 东边界"),
    max_lat: float = Query(..., description="bbox 北边界"),
    limit: int = Query(20000, ge=1, le=60000),
) -> dict:
    """bbox 内的评分路段（GeoJSON）。

    TODO(卡片2): 现在是把整表读进内存再过滤，约 0.6 s；应改为
    预建 STRtree 或按瓦片切片，并支持 `simplify` 参数。
    """
    import geopandas as gpd

    if not (min_lng < max_lng and min_lat < max_lat):
        raise HTTPException(status_code=400, detail="bbox 边界不合法")

    path = running.RUN / "segments.gpkg"
    if not path.exists():
        raise HTTPException(status_code=503, detail="segments.gpkg 不存在，请先跑 build_running_dataset.py")

    gdf = gpd.read_file(path, layer="segments", bbox=(min_lng, min_lat, max_lng, max_lat))
    gdf = gdf.head(limit)
    keep = ["osm_id", "fclass", "name", "length_m", "score", "grade",
            "s_safety", "s_green", "s_slope", "s_cross", "s_fac", "geometry"]
    gdf = gdf[[c for c in keep if c in gdf.columns]]
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {k: _plain(v) for k, v in r.items() if k != "geometry"},
             "geometry": r["geometry"].__geo_interface__}
            for _, r in gdf.iterrows()
        ],
        "truncated": len(gdf) >= limit,
    }


@app.get("/api/facilities")
def facilities(
    min_lng: float = Query(...),
    min_lat: float = Query(...),
    max_lng: float = Query(...),
    max_lat: float = Query(...),
    kinds: str = Query("sport", description="sport | support | all"),
) -> dict:
    """bbox 内的设施点。

    TODO(卡片2): `kinds=support` 目前没有实现（需要把 OSM 的公园/厕所/便利店
    与高德场馆合并成一张表），可直接复用 build_running_dataset.py 里的筛选逻辑。
    """
    import pandas as pd

    csv = running.RUN / "amap_sport_poi.csv"
    if not csv.exists():
        raise HTTPException(status_code=503, detail="amap_sport_poi.csv 不存在")
    df = pd.read_csv(csv)
    df = df[(df.lng.between(min_lng, max_lng)) & (df.lat.between(min_lat, max_lat))]
    drop = df["type"].fillna("").str.contains("台球|棋牌|游戏|歌舞|夜总会|网吧|KTV", regex=True)
    df = df[~drop]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": r["name"], "type": r["type"]},
                "geometry": {"type": "Point", "coordinates": [float(r["lng"]), float(r["lat"])]},
            }
            for _, r in df.iterrows()
        ],
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
            g, req.lng, req.lat, req.target_m,
            prefs=req.prefs, max_candidates=req.max_candidates,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"环线生成失败: {exc}") from exc

    if not found:
        return {"type": "FeatureCollection", "features": [],
                "message": "该起点在目标距离附近没有合适的折点，请换个距离或起点"}

    fc = running.to_geojson(g, found)
    return fc


def _plain(v):
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


@app.get("/api/meta")
def meta() -> dict:
    """数据版本与口径，前端用来显示"数据说明"。"""
    import json

    summary = running.RUN / "score_summary.json"
    payload = json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else {}
    return {
        "dataset": "running/v1",
        "weights": payload.get("weights"),
        "score_stats": payload.get("score"),
        "notes": payload.get("notes", []),
        "speed_mps": running.RUN_SPEED_MPS,
    }
