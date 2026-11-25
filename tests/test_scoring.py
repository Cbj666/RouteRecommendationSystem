# -*- coding: utf-8 -*-
"""评分数据的不变量。卡片 6 认领人可在此基础上补更多断言。"""
from __future__ import annotations

import numpy as np
import pytest

SUBS = ["s_safety", "s_green", "s_slope", "s_cross", "s_fac"]


def test_row_count(segments):
    assert len(segments) > 90_000


def test_score_range(segments):
    assert segments["score"].between(0, 100).all()
    assert segments["score"].isna().sum() == 0


def test_subscores_range(segments):
    for col in SUBS:
        assert segments[col].between(0, 100).all(), col


def test_raw_indicators_sane(segments):
    assert (segments["slope_mean_pct"] >= 0).all()
    assert segments["tree_share"].between(0, 1).all()
    assert (segments["cross_200m"] >= 0).all()
    assert (segments["d_fac_m"] >= 0).all()


def test_known_woodland_has_canopy():
    """武大、磨山这种林地，树冠应显著高于全城均值（回归：拼图错位过）。"""
    from pathlib import Path

    import geopandas as gpd
    import pyogrio
    from shapely.geometry import Point

    path = Path(__file__).resolve().parents[1] / "data" / "processed" / "running" / "v1" / "segments.gpkg"
    if not path.exists():
        pytest.skip("segments.gpkg 不存在，先跑 build_running_dataset.py")

    seg = pyogrio.read_dataframe(path, layer="segments")
    city = float(seg["tree_share"].mean())
    # WGS84 下量距离不可靠，按 AGENTS.md 投到 EPSG:32650 再取磨山 1 km 内的路段
    moshan = gpd.GeoSeries([Point(114.4210, 30.5450)], crs=4326).to_crs(32650).iloc[0]
    near = seg.to_crs(32650)[lambda df: df.distance(moshan) < 1000]
    assert len(near) > 20
    assert float(near["tree_share"].mean()) > city * 1.8


def test_grade_matches_score(segments):
    import pandas as pd

    # v2 口径（2026-11-17 定版）：差 <35、一般 35–50、较好 50–65、好 65–80、很好 ≥80
    bins = pd.cut(
        segments["score"], bins=[0, 35, 50, 65, 80, 100],
        labels=["差", "一般", "较好", "好", "很好"], include_lowest=True,
    )
    mismatch = (bins.astype(str) != segments["grade"]).sum()
    assert mismatch == 0
