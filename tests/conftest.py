# -*- coding: utf-8 -*-
"""共用 fixture：跑步图与评分表只加载一次。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

RUN = ROOT / "data" / "processed" / "running" / "v1"


@pytest.fixture(scope="session")
def graph():
    from app import running

    return running.load_or_build()


@pytest.fixture(scope="session")
def segments():
    import geopandas as gpd
    import pyogrio

    path = RUN / "segments.gpkg"
    if not path.exists():
        pytest.skip("segments.gpkg 不存在，先跑 build_running_dataset.py")
    return pyogrio.read_dataframe(path, layer="segments")


@pytest.fixture(scope="session")
def loops(graph):
    from app import running

    found = running.generate_loops(graph, 114.3547, 30.5342, 5000)
    if not found:
        pytest.skip("该起点没有生成环线")
    return found
