# -*- coding: utf-8 -*-
"""高德地点搜索适配层的单元测试（不联网）。

覆盖：Key 读取优先级、GCJ-02 → WGS84、POI 解析、缓存、错误码映射。
"""
from __future__ import annotations

import pytest
import requests

from app import amap


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """每个用例都从「没有 Key、缓存为空」开始，避免 .env 与全局缓存串扰。"""
    for name in amap.KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(amap, "_dotenv", lambda: {})
    amap._CACHE.clear()
    yield
    amap._CACHE.clear()


def _poi(**overrides):
    poi = {
        "id": "B001",
        "name": "武汉大学",
        "address": "八一路299号",
        "pname": "湖北省",
        "cityname": "武汉市",
        "adname": "武昌区",
        "type": "科教文化服务;学校;高等院校",
        "typecode": "141201",
        # 高德实际返回的「武汉大学」原始坐标（GCJ-02），来自 /api/places/search 实测
        "location": "114.364514,30.536243",
    }
    poi.update(overrides)
    return poi


def test_api_key_priority_and_dotenv_fallback(monkeypatch):
    assert amap.api_key() == ""

    monkeypatch.setenv("AMAP_WEB_KEY", "web")
    monkeypatch.setenv("GAODE_KEY", "gaode")
    assert amap.api_key() == "web"

    monkeypatch.delenv("AMAP_WEB_KEY")
    assert amap.api_key() == "gaode"

    monkeypatch.delenv("GAODE_KEY")
    monkeypatch.setenv("AMAP_KEY", "amap")
    assert amap.api_key() == "amap"

    monkeypatch.delenv("AMAP_KEY")
    monkeypatch.setattr(amap, "_dotenv", lambda: {"GAODE_KEY": "from-dotenv"})
    assert amap.api_key() == "from-dotenv"


def test_gcj02_to_wgs84_matches_live_amap_record():
    # 高德「武汉大学」实测坐标（GCJ-02）；转出的 WGS84 必须与
    # /api/places/search 的返回逐位一致，否则起点会偏离路网
    gcj_lng, gcj_lat = 114.364514, 30.536243
    lng, lat = amap.gcj02_to_wgs84(gcj_lng, gcj_lat)

    # 武汉一带两者相差约 300–600 m；经度必然往西，纬度方向随位置而变
    assert 0.003 < gcj_lng - lng < 0.006
    assert abs(gcj_lat - lat) < 0.006
    assert abs(lng - 114.358986) < 1e-6
    assert abs(lat - 30.538568) < 1e-6


def test_to_place_converts_coordinates_and_normalizes_fields():
    place = amap._to_place(_poi())

    assert place is not None
    assert place["id"] == "B001"
    assert place["name"] == "武汉大学"
    assert place["district"] == "武昌区"
    assert place["lng"] == pytest.approx(114.358986, abs=1e-5)
    assert place["lat"] == pytest.approx(30.538568, abs=1e-5)
    assert place["lng"] < place["amap_lng"]
    assert place["amap_lng"] == pytest.approx(114.364514)
    assert place["amap_lat"] == pytest.approx(30.536243)


def test_to_place_handles_missing_or_empty_values():
    assert amap._to_place(_poi(location="[]")) is None
    assert amap._to_place(_poi(location="")) is None
    assert amap._to_place(_poi(location=None)) is None
    assert amap._to_place(_poi(location="not-a-point")) is None

    # 高德无值时会返回 JSON 的空数组 []（列表），统一成空字符串
    place = amap._to_place(_poi(id=[], address=[]))
    assert place is not None
    # 高德无 id 时用名称 + 高德原始坐标兜底，保证前端列表 key 稳定
    assert place["id"].startswith("武汉大学@114.364514,30.536243")
    assert place["address"] == ""


def test_search_places_parses_payload_and_uses_cache(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None, headers=None):
        calls.append(params)
        return FakeResponse(
            {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "pois": [
                    _poi(id="B001", name="武汉大学"),
                    _poi(id="B002", name="武汉大学图书馆", location="114.361,30.541"),
                    _poi(id="B001", name="重复项"),
                    _poi(id="B003", name="没有坐标", location="[]"),
                ],
            }
        )

    monkeypatch.setattr(amap.requests, "get", fake_get)
    monkeypatch.setenv("GAODE_KEY", "test-key")

    first = amap.search_places("武汉大学", limit=5)
    second = amap.search_places("武汉大学", limit=5)

    assert len(calls) == 1  # 第二次命中缓存，不再消耗配额
    assert [place["id"] for place in first] == ["B001", "B002"]
    assert second == first
    assert calls[0]["key"] == "test-key"
    assert calls[0]["keywords"] == "武汉大学"
    assert calls[0]["city"] == amap.DEFAULT_CITY


def test_search_places_stops_at_limit(monkeypatch):
    def fake_get(url, params=None, timeout=None, headers=None):
        return FakeResponse(
            {
                "status": "1",
                "pois": [_poi(id=f"B{i:03d}") for i in range(6)],
            }
        )

    monkeypatch.setattr(amap.requests, "get", fake_get)
    monkeypatch.setenv("GAODE_KEY", "test-key")

    assert len(amap.search_places("武大", limit=3)) == 3


def test_search_places_requires_key():
    with pytest.raises(amap.AmapConfigError):
        amap.search_places("武汉大学")


def test_search_places_validates_arguments(monkeypatch):
    monkeypatch.setenv("GAODE_KEY", "test-key")
    with pytest.raises(ValueError):
        amap.search_places("   ")
    with pytest.raises(ValueError):
        amap.search_places("武汉大学", limit=0)
    with pytest.raises(ValueError):
        amap.search_places("武汉大学", limit=amap.MAX_LIMIT + 1)


def test_search_places_maps_amap_error_code(monkeypatch):
    monkeypatch.setattr(
        amap.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            {"status": "0", "info": "DAILY_QUERY_OVER_LIMIT", "infocode": "10003"}
        ),
    )
    monkeypatch.setenv("GAODE_KEY", "test-key")

    with pytest.raises(amap.AmapUnavailableError) as excinfo:
        amap.search_places("武汉大学")
    assert "配额" in str(excinfo.value)


def test_search_places_maps_timeout_and_http_error(monkeypatch):
    monkeypatch.setenv("GAODE_KEY", "test-key")

    def raise_timeout(*args, **kwargs):
        raise requests.Timeout("timed out")

    monkeypatch.setattr(amap.requests, "get", raise_timeout)
    with pytest.raises(amap.AmapTimeoutError):
        amap.search_places("武汉大学")

    monkeypatch.setattr(
        amap.requests, "get", lambda *args, **kwargs: FakeResponse({}, status_code=500)
    )
    with pytest.raises(amap.AmapUnavailableError):
        amap.search_places("武汉大学")

    monkeypatch.setattr(
        amap.requests, "get", lambda *args, **kwargs: FakeResponse(ValueError("bad json"))
    )
    with pytest.raises(amap.AmapUnavailableError):
        amap.search_places("武汉大学")


def test_search_places_does_not_cache_failures(monkeypatch):
    calls = []

    def fake_get(*args, **kwargs):
        calls.append(1)
        return FakeResponse(
            {"status": "0", "info": "INVALID_PARAMS", "infocode": "20000"}
        )

    monkeypatch.setattr(amap.requests, "get", fake_get)
    monkeypatch.setenv("GAODE_KEY", "test-key")

    for _ in range(2):
        with pytest.raises(amap.AmapUnavailableError):
            amap.search_places("武汉大学")
    assert len(calls) == 2
