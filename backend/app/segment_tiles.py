"""预切瓦片式的路段索引（``GET /api/segments`` 的快速通道）。

9.1 万段路网在第一次请求时整理成三样东西，之后按 bbox 直接拼字符串返回：

1. 每段的外包框（numpy 数组，向量化相交判断）；
2. 0.01° 的网格索引（格 → 段下标），只扫视口覆盖的格子；
3. basic 口径下每段预序列化好的 GeoJSON Feature 片段（坐标保留 5 位小数，
   约 1 m 精度），属性只留 ``osm_id / score / grade`` 三个字段。

这样每次请求不再走 ``GeoDataFrame.cx`` 全表扫描与 ``to_json``，只做
「取候选 → bbox 相交 → 截断 → 逗号拼接」；同样内容连续请求再命中一层
LRU，配合 ``ETag`` / ``If-None-Match`` 直接 304。

``detail=full``（路段详情探查）仍走原来的 geopandas 路径，
返回字段与语义都不变。
"""

from __future__ import annotations

import gzip
import json
import math
from collections import OrderedDict
from typing import Any

import numpy as np

from . import datasets

# 索引格边长（度）：0.01° 约 1.1 km × 0.9 km
STEP = 0.01
# 预序列化片段与响应体的 LRU 上限（条）
MAX_BODIES = 96
# 响应体缓存总字符上限（约 200 MB）
MAX_BODY_CHARS = 200_000_000
# 坐标小数位（5 位约 1 m，肉眼与冒烟都够用）
COORD_DIGITS = 5

BASIC_FIELDS = tuple(datasets.BASIC_SEGMENT_FIELDS)

BODIES: OrderedDict[tuple[Any, ...], tuple[str, bytes]] = OrderedDict()
_BODY_CHARS = 0


def _coords_json(geom: Any) -> str:
    """把 LineString 坐标压成最短的 JSON 片段（5 位小数）。"""
    parts: list[str] = []
    for x, y in geom.coords:
        parts.append(f"[{round(x, COORD_DIGITS)},{round(y, COORD_DIGITS)}]")
    return "[" + ",".join(parts) + "]"


def _feature_json(row: Any, geom: Any) -> str:
    """预序列化一条 Feature。

    ``osm_id`` 是整数，``score`` 保留 1 位小数（与展示一致），``grade`` 直接输出
    中文字符串；字段顺序固定，方便肉眼比对。
    """
    osm_id = int(row["osm_id"])
    score = float(row["score"])
    if not math.isfinite(score):
        score = 0.0
    props = (
        '{"osm_id":%d,"score":%.1f,"grade":%s}'
        % (osm_id, round(score, 1), json.dumps(str(row["grade"]), ensure_ascii=False))
    )
    return (
        '{"type":"Feature","properties":'
        + props
        + ',"geometry":{"type":"LineString","coordinates":'
        + _coords_json(geom)
        + "}}"
    )


class SegmentIndex:
    """路段的 bbox 数组 + 网格索引 + 预序列化片段。"""

    def __init__(self, gdf: Any) -> None:
        bounds = np.asarray(gdf.geometry.bounds, dtype=float)
        self.minx = bounds[:, 0]
        self.miny = bounds[:, 1]
        self.maxx = bounds[:, 2]
        self.maxy = bounds[:, 3]
        self.count = len(gdf)

        ix0 = np.floor(self.minx / STEP).astype(np.int64)
        iy0 = np.floor(self.miny / STEP).astype(np.int64)
        ix1 = np.floor(self.maxx / STEP).astype(np.int64)
        iy1 = np.floor(self.maxy / STEP).astype(np.int64)

        cells: dict[tuple[int, int], list[int]] = {}
        for k in range(self.count):
            for i in range(int(ix0[k]), int(ix1[k]) + 1):
                for j in range(int(iy0[k]), int(iy1[k]) + 1):
                    cells.setdefault((i, j), []).append(k)
        self.cells = {key: np.asarray(ids, dtype=np.int32) for key, ids in cells.items()}

        self.fragments: list[str] = []
        columns = [c for c in BASIC_FIELDS if c in gdf.columns]
        subset = gdf[columns + [gdf.geometry.name]]
        for row, geom in zip(subset.itertuples(index=False), subset.geometry):
            if geom is None or geom.is_empty:
                self.fragments.append("")
                continue
            self.fragments.append(_feature_json(dict(zip(columns, row[: len(columns)])), geom))

    def query(self, bbox: tuple[float, float, float, float], limit: int) -> tuple[list[int], int]:
        """返回 (命中的路段下标, 候选总数)，下标保持原始顺序。"""
        min_lng, min_lat, max_lng, max_lat = bbox
        i0 = math.floor(min_lng / STEP)
        i1 = math.floor(max_lng / STEP)
        j0 = math.floor(min_lat / STEP)
        j1 = math.floor(max_lat / STEP)

        chunks = [
            self.cells[(i, j)]
            for i in range(i0, i1 + 1)
            for j in range(j0, j1 + 1)
            if (i, j) in self.cells
        ]
        if not chunks:
            return [], 0
        candidates = np.unique(np.concatenate(chunks))
        hit = (
            (self.minx[candidates] <= max_lng)
            & (self.maxx[candidates] >= min_lng)
            & (self.miny[candidates] <= max_lat)
            & (self.maxy[candidates] >= min_lat)
        )
        ids = candidates[hit]
        total = int(ids.size)
        if total > limit:
            ids = ids[:limit]
        return [int(v) for v in ids], total


_index: SegmentIndex | None = None


def index() -> SegmentIndex:
    """返回（必要时构建一次）路段索引。"""
    global _index
    if _index is None:
        _index = SegmentIndex(datasets.segments())
    return _index


def _remember(key: tuple[Any, ...], body: str, gz: bytes) -> None:
    global _BODY_CHARS
    BODIES[key] = (body, gz)
    _BODY_CHARS += len(body) + len(gz)
    while len(BODIES) > MAX_BODIES or _BODY_CHARS > MAX_BODY_CHARS:
        _, old = BODIES.popitem(last=False)
        _BODY_CHARS -= len(old[0]) + len(old[1])


def _build(bbox: tuple[float, float, float, float], limit: int) -> tuple[str, bytes]:
    """拼出 basic 口径的 FeatureCollection，并预先压好 gzip。"""
    idx = index()
    ids, total = idx.query(bbox, limit)
    head = (
        '{"total":%d,"truncated":%s,"bbox":[%s],"detail":"basic",'
        '"type":"FeatureCollection","features":['
        % (
            total,
            "true" if total > limit else "false",
            ",".join(repr(float(v)) for v in bbox),
        )
    )
    parts = [idx.fragments[i] for i in ids]
    parts = [p for p in parts if p]
    body = head + ",".join(parts) + "]}"
    # mtime=0：响应体一次成形、后面不再变，gzip 头里的时间戳没有意义。
    gz = gzip.compress(body.encode("utf-8"), compresslevel=6, mtime=0)
    return body, gz


def _cached(bbox: tuple[float, float, float, float], limit: int) -> tuple[str, bytes]:
    key = (tuple(round(float(v), 6) for v in bbox), int(limit))
    hit = BODIES.get(key)
    if hit is not None:
        BODIES.move_to_end(key)
        return hit
    body, gz = _build(bbox, limit)
    _remember(key, body, gz)
    return body, gz


def basic_body(bbox: tuple[float, float, float, float], limit: int) -> str:
    """拼出 basic 口径的 FeatureCollection 文本（命中 LRU 时零计算）。"""
    return _cached(bbox, limit)[0]


def basic_payload(bbox: tuple[float, float, float, float], limit: int) -> tuple[str, bytes]:
    """同上，但同时返回预压缩的 gzip 字节，供响应直接复用。"""
    return _cached(bbox, limit)


def version() -> str:
    """数据版本：用 segments.gpkg 的 mtime + 大小做 ETag 的稳定后缀。"""
    stat = datasets.SEGMENTS_GPKG.stat()
    return f"{int(stat.st_mtime)}-{stat.st_size}"


def etag(bbox: tuple[float, float, float, float], limit: int) -> str:
    """basic 口径的强校验 ETag（与缓存 key 一一对应）。"""
    box = "-".join(f"{float(v):.6f}" for v in bbox)
    return f'W/"segments-basic-{box}-{int(limit)}-{version()}"'


def stats() -> dict[str, Any]:
    """索引规模，供 /api/meta 或排查使用。"""
    idx = index()
    return {
        "segments": idx.count,
        "cells": len(idx.cells),
        "step_deg": STEP,
        "bodies_cached": len(BODIES),
    }
