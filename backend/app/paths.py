# -*- coding: utf-8 -*-
"""后端统一路径定义。

所属模块：基础设施与路径层。

作用：以项目根目录为基准集中定义后端、数据、原始输入、缓存和输出目录，
避免 API、算法与脚本重复拼接相对路径。涉及路径的代码应优先引用本模块。
"""
from __future__ import annotations

from pathlib import Path

# 后端目录与项目根目录
BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent

# 数据根目录及其主要分区
DATA = PROJECT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
OUTPUT = DATA / "output"

# 基础冻结数据与历史多模式图缓存
V1 = DATA / "processed" / "v1"
GRAPH_CACHE = DATA / "processed" / "graph"

# 原始地理输入
BOUNDARY = RAW / "boundary" / "武汉市_市.geojson"
OSM_GPKG = RAW / "hubei" / "hubei-261013-free-OpenMap" / "hubei.gpkg"
OSM_PBF = RAW / "hubei" / "hubei-261013.osm.pbf"

# 高德抓取后的中间表目录
AMAP_PILOT = INTERIM / "amap_pilot"
AMAP_METRO = INTERIM / "amap_metro"


def ensure_dirs() -> None:
    """创建数据流水线需要的可写目录；已存在的目录保持不变。"""
    for p in (OUTPUT, INTERIM, V1, GRAPH_CACHE):
        p.mkdir(parents=True, exist_ok=True)
