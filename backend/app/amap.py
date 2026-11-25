# -*- coding: utf-8 -*-
"""高德地点搜索适配层。

所属模块：外部服务适配层。

作用：把前端的地点搜索请求转发到高德开放平台 Web 服务
``/v3/place/text``，并把高德返回的 **GCJ-02** 坐标转换为项目统一使用的
**WGS84**。同时负责：

- 从服务端环境变量（``AMAP_WEB_KEY`` / ``GAODE_KEY`` / ``AMAP_KEY``）或项目
  根目录 ``.env`` 读取 Key，**绝不下发到浏览器**；
- 对相同的关键词做 5 分钟内存缓存，降低高德配额消耗；
- 把高德错误码、网络超时映射为可读的中文异常，由 API 层转成 4xx/5xx。

前端接口见 ``app.api`` 的 ``GET /api/places/search``。
"""
from __future__ import annotations

import logging
import math
import os
import re
import threading
import time
from functools import lru_cache
from typing import Any

import requests

from . import paths

logger = logging.getLogger(__name__)

# 高德 Web 服务：关键字搜索
PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text"

# 本项目只服务武汉；citylimit=true 防止搜到同名异地地点
DEFAULT_CITY = "武汉"

# Key 的环境变量 / .env 键名，按优先级排列
KEY_NAMES = ("AMAP_WEB_KEY", "GAODE_KEY", "AMAP_KEY")

# 高德 place/text 单页上限 25 条；本项目一次最多取 20 条
MAX_LIMIT = 20
DEFAULT_LIMIT = 8

# 搜索是交互式请求，连接 3 s、读取 6 s 足够；超时由 API 层转 504
REQUEST_TIMEOUT = (3.05, 6.0)

# 相同关键词的短时缓存，避免用户来回改字/重复聚焦时反复消耗配额
CACHE_TTL_SECONDS = 300.0
CACHE_MAX_ENTRIES = 128

# GCJ-02 偏移参数（与 backend/scripts/geo_utils.py 同一套算法）
_AXIS = 6378245.0
_EE = 0.00669342162296594323

# requests 的异常消息会把完整 URL 带进来，形如 /v3/place/text?key=xxxx&keywords=...
# 因此任何写日志、拼异常的路径都必须先过 _scrub，否则 Key 会经日志进入对话上下文。
_KEY_IN_TEXT = re.compile(r"(key=)[^&\s\"']+", re.IGNORECASE)


def _scrub(text: str) -> str:
    """把文本里的 ``key=...`` 值替换为 ``[REDACTED]``，只保留键名。"""
    return _KEY_IN_TEXT.sub(r"\1[REDACTED]", text)


class AmapError(RuntimeError):
    """高德搜索失败的基类。"""


class AmapConfigError(AmapError):
    """服务端没有配置可用的高德 Key。API 层应转 503。"""


class AmapUnavailableError(AmapError):
    """高德返回错误码、HTTP 异常或无法解析。API 层应转 502。"""


class AmapTimeoutError(AmapError):
    """请求高德超时。API 层应转 504。"""


# ---------------------------------------------------------------------------
# Key 读取
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _dotenv() -> dict[str, str]:
    """读取项目根目录 ``.env``；只做最简单的 KEY=VALUE 解析。

    没有装 python-dotenv，也不想为一个小功能增加依赖。文件不存在或读不了时
    返回空字典；服务启动后修改 ``.env`` 需要重启才生效。
    """
    path = paths.PROJECT / ".env"
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return {}

    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name:
            values[name] = value
    return values


def api_key() -> str:
    """返回高德 Web 服务 Key；环境变量优先于根目录 ``.env``。

    变量名按 ``AMAP_WEB_KEY`` → ``GAODE_KEY`` → ``AMAP_KEY`` 的顺序回退：
    项目根目录 ``.env`` 现有 ``GAODE_KEY``，同时兼容部署环境里更明确的名字。
    """
    for name in KEY_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    env = _dotenv()
    for name in KEY_NAMES:
        value = (env.get(name) or "").strip()
        if value:
            return value
    return ""


def configured() -> bool:
    """是否已配置高德 Key（只返回布尔值，不暴露 Key 本身）。"""
    return bool(api_key())


# ---------------------------------------------------------------------------
# 坐标转换：GCJ-02 → WGS84
# ---------------------------------------------------------------------------

def _out_of_china(lng: float, lat: float) -> bool:
    return not (73.66 < lng < 135.05 and 3.86 < lat < 53.55)


def _transform_lat(x: float, y: float) -> float:
    ret = (
        -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y
        + 0.2 * math.sqrt(abs(x))
    )
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(x: float, y: float) -> float:
    ret = (
        300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y
        + 0.1 * math.sqrt(abs(x))
    )
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def gcj02_to_wgs84(lng: float, lat: float) -> tuple[float, float]:
    """把高德的 GCJ-02 坐标转换为 WGS84，供路线算法与 SVG 地图直接使用。

    武汉城区两者相差约 300–500 m；不转换会导致“搜索到的起点”落到路网外，
    触发 500 m 吸附校验失败或生成错误路线。
    """
    if _out_of_china(lng, lat):
        return lng, lat

    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - _EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_AXIS * (1 - _EE)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (_AXIS / sqrtmagic * math.cos(radlat) * math.pi)
    return lng - dlng, lat - dlat


# ---------------------------------------------------------------------------
# 结果缓存
# ---------------------------------------------------------------------------

_CACHE: dict[tuple[str, int], tuple[float, tuple[dict[str, Any], ...]]] = {}
_CACHE_LOCK = threading.Lock()


def _cache_get(key: tuple[str, int]) -> list[dict[str, Any]] | None:
    now = time.monotonic()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is None:
            return None
        expires_at, items = hit
        if expires_at <= now:
            _CACHE.pop(key, None)
            return None
        return [dict(item) for item in items]


def _cache_put(key: tuple[str, int], items: list[dict[str, Any]]) -> None:
    with _CACHE_LOCK:
        if len(_CACHE) >= CACHE_MAX_ENTRIES:
            # 简单淘汰最早写入的一项；搜索缓存不需要严格的 LRU
            _CACHE.pop(next(iter(_CACHE)), None)
        _CACHE[key] = (
            time.monotonic() + CACHE_TTL_SECONDS,
            tuple(dict(item) for item in items),
        )


# ---------------------------------------------------------------------------
# 响应解析
# ---------------------------------------------------------------------------

def _text(value: Any) -> str:
    """高德在“无值”时可能返回空列表 ``[]``，统一成空字符串。"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return ""
    if value is None:
        return ""
    return str(value).strip()


def _parse_location(raw: Any) -> tuple[float, float] | None:
    """解析高德 ``"lng,lat"`` 字符串；不合法时返回 None。"""
    text = _text(raw)
    if not text or "," not in text:
        return None
    lng_text, lat_text = text.split(",", 1)
    try:
        lng, lat = float(lng_text), float(lat_text)
    except ValueError:
        return None
    if not (-180.0 <= lng <= 180.0 and -90.0 <= lat <= 90.0):
        return None
    return lng, lat


# 高德常见错误码 → 前端可读提示。不要把 Key 写进任何提示或日志。
_ERROR_MESSAGES = {
    "10001": "高德 Key 无效，请检查项目根目录 .env 的 GAODE_KEY（需 Web 服务 Key）",
    "10002": "高德 Key 已过期或被停用，请重新申请",
    "10003": "高德搜索今日配额已用尽，请明天再试或更换 Key",
    "10004": "高德搜索请求过于频繁，请稍后再试",
    "10009": "高德 Key 与服务类型不匹配，请使用 Web 服务 Key",
    "10010": "高德搜索 IP 访问超限，请稍后再试",
    "10044": "高德搜索今日调用量超限，请明天再试",
    "20000": "高德搜索参数错误，请换个关键词再试",
    "20800": "高德搜索服务维护中，请稍后再试",
    "20802": "高德搜索服务暂不可用，请稍后再试",
}


def _error_message(infocode: str, info: str) -> str:
    known = _ERROR_MESSAGES.get(infocode)
    if known:
        return known
    suffix = f"（{info}）" if info else ""
    return f"高德搜索失败{suffix}，请稍后重试"


def _to_place(poi: dict[str, Any]) -> dict[str, Any] | None:
    """把一条高德 POI 转成前端地点结构；坐标同时保留 GCJ-02 供排错。"""
    location = _parse_location(poi.get("location"))
    if location is None:
        return None

    lng, lat = location
    wgs_lng, wgs_lat = gcj02_to_wgs84(lng, lat)
    poi_id = _text(poi.get("id"))
    if not poi_id:
        # 高德偶尔不给 id；用名称+坐标做稳定键
        poi_id = f"{_text(poi.get('name'))}@{lng:.6f},{lat:.6f}"

    return {
        "id": poi_id,
        "name": _text(poi.get("name")) or "未命名地点",
        "address": _text(poi.get("address")),
        "province": _text(poi.get("pname")),
        "city": _text(poi.get("cityname")),
        "district": _text(poi.get("adname")),
        "type": _text(poi.get("type")),
        "typecode": _text(poi.get("typecode")),
        # 项目统一坐标：WGS84
        "lng": round(wgs_lng, 6),
        "lat": round(wgs_lat, 6),
        # 高德原始坐标：GCJ-02，便于排查偏移
        "amap_lng": round(lng, 6),
        "amap_lat": round(lat, 6),
    }


# ---------------------------------------------------------------------------
# 对外搜索
# ---------------------------------------------------------------------------

def search_places(keywords: str, *, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    """按关键词搜索高德地点，返回 WGS84 坐标的列表。

    参数：
        keywords：搜索词，去掉首尾空格后不能为空。
        limit：1–20，默认 8。

    异常：
        ValueError：参数为空或越界（API 层会先校验）。
        AmapConfigError：服务端没有 Key。
        AmapTimeoutError：请求高德超时。
        AmapUnavailableError：高德返回错误码 / HTTP 异常 / 响应无法解析。
    """
    query = (keywords or "").strip()
    if not query:
        raise ValueError("搜索关键词不能为空")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit 必须在 1–{MAX_LIMIT} 之间")

    cache_key = (query, limit)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    key = api_key()
    if not key:
        raise AmapConfigError(
            "高德地点搜索未配置：请在项目根目录 .env 写入 GAODE_KEY"
            "（或 AMAP_WEB_KEY，高德开放平台「Web 服务」类型的 Key），然后重启后端。"
        )

    params = {
        "key": key,
        "keywords": query,
        "city": DEFAULT_CITY,
        "citylimit": "true",
        "offset": str(limit),
        "page": "1",
        "extensions": "base",
    }

    try:
        response = requests.get(
            PLACE_TEXT_URL,
            params=params,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "city-running-suitability/1.0"},
        )
    except requests.Timeout:
        # 刻意不链接原异常：requests 的异常消息含完整 URL（带 key=...），
        # 一旦被 logger.exception / debug traceback 打印出去就会泄漏 Key。
        raise AmapTimeoutError("高德搜索超时，请检查网络后重试") from None
    except requests.RequestException as exc:
        logger.warning(
            "高德地点搜索请求失败：%s: %s",
            type(exc).__name__,
            _scrub(str(exc)),
        )
        raise AmapUnavailableError("无法连接高德地图，请检查网络后重试") from None

    if response.status_code != 200:
        logger.warning("高德地点搜索 HTTP %s", response.status_code)
        raise AmapUnavailableError(f"高德地图服务返回 HTTP {response.status_code}")

    try:
        payload = response.json()
    except ValueError:
        raise AmapUnavailableError("高德地图返回了无法解析的响应") from None

    if _text(payload.get("status")) != "1":
        # info 同样来自远端，先脱敏再进日志与异常消息，防止高德/网关回显请求参数
        info = _scrub(_text(payload.get("info")))
        infocode = _text(payload.get("infocode"))
        logger.warning("高德地点搜索失败：infocode=%s info=%s", infocode, info)
        raise AmapUnavailableError(_error_message(infocode, info))

    places: list[dict[str, Any]] = []
    seen: set[str] = set()
    for poi in payload.get("pois") or []:
        if not isinstance(poi, dict):
            continue
        place = _to_place(poi)
        if place is None or place["id"] in seen:
            continue
        seen.add(place["id"])
        places.append(place)
        if len(places) >= limit:
            break

    _cache_put(cache_key, places)
    logger.info("高德地点搜索：query=%r limit=%s -> %s 条", query, limit, len(places))
    return places
