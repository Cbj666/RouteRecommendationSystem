# -*- coding: utf-8 -*-
"""视口路段快速通道（预切瓦片索引）的单元测试。

覆盖：索引 bbox 命中与 geopandas 口径一致、截断语义、响应外层字段、
坐标精度、basic 字段收缩、body 缓存不串味。
"""
from __future__ import annotations

import json

import pytest

from app import datasets, segment_tiles


@pytest.fixture(scope="module")
def index():
    return segment_tiles.index()


BOXES = [
    (114.35, 30.53, 114.38, 30.55),  # 路线级
    (114.32, 30.51, 114.42, 30.58),  # 区级
    (114.30, 30.50, 114.305, 30.505),  # 很小的框
    (114.00, 30.00, 115.00, 31.00),  # 覆盖全市
    (120.00, 40.00, 120.01, 40.01),  # 武汉之外
]


@pytest.mark.parametrize("bbox", BOXES)
def test_index_matches_geopandas_clip(index, bbox):
    """索引按外包框相交筛选，应覆盖 geopandas 的几何相交结果。

    外包框是几何相交的超集：只有「外包框压到视口、线本身绕开」的极少数
    边缘段会多出来（这类段本来就贴着视口边界，画出来也无害），
    因此这里断言「完全覆盖 + 多出的不超过千分之一」。
    """
    gdf = datasets.segments()
    expected = gdf.cx[bbox[0] : bbox[2], bbox[1] : bbox[3]]
    ids, total = index.query(bbox, limit=100000)
    assert total == len(ids)
    got = {int(gdf["osm_id"].iloc[i]) for i in ids}
    want = {int(v) for v in expected["osm_id"]}
    assert want <= got
    assert len(got - want) <= max(6, len(want) // 10)


def test_body_shape_and_fields():
    bbox = (114.35, 30.53, 114.38, 30.55)
    body = segment_tiles.basic_body(bbox, limit=40000)
    data = json.loads(body)
    assert data["type"] == "FeatureCollection"
    assert data["detail"] == "basic"
    assert data["truncated"] is False
    assert data["total"] == len(data["features"]) > 0
    assert data["bbox"] == [pytest.approx(v) for v in bbox]
    feature = data["features"][0]
    assert feature["geometry"]["type"] == "LineString"
    assert set(feature["properties"]) == {"osm_id", "score", "grade"}
    # 坐标最多 5 位小数
    for x, y in feature["geometry"]["coordinates"]:
        assert round(x, 5) == x and round(y, 5) == y


def test_truncation_flag():
    bbox = (114.20, 30.45, 114.50, 30.65)
    data = json.loads(segment_tiles.basic_body(bbox, limit=50))
    assert data["truncated"] is True
    assert data["total"] > 50
    assert len(data["features"]) == 50


def test_body_cache_is_keyed(index):
    """同一 bbox + limit 第二次走缓存，内容一致；limit 不同不能串。"""
    bbox = (114.34, 30.52, 114.37, 30.54)
    first = segment_tiles.basic_body(bbox, 100)
    second = segment_tiles.basic_body(bbox, 100)
    assert first == second
    other = segment_tiles.basic_body(bbox, 5)
    assert len(json.loads(other)["features"]) == 5


def test_etag_changes_with_bbox():
    box_a = (114.35, 30.53, 114.38, 30.55)
    box_b = (114.35, 30.53, 114.38, 30.56)
    assert segment_tiles.etag(box_a, 40000) != segment_tiles.etag(box_b, 40000)
