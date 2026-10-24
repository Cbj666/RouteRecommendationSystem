# -*- coding: utf-8 -*-
"""评分数据的不变量。卡片 6 认领人可在此基础上补更多断言。"""
from __future__ import annotations

import numpy as np

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
    import geopandas as gpd
    from shapely.geometry import Point

    seg = gpd.read_file(
        "data/processed/running/v1/segments.gpkg",
        layer="segments",
        columns=["tree_share"],
    )
    city = float(seg["tree_share"].mean())
    near = seg[seg.distance(Point(114.4210, 30.5450)) < 0.01]   # 磨山
    assert len(near) > 20
    assert float(near["tree_share"].mean()) > city * 1.8


def test_grade_matches_score(segments):
    import pandas as pd

    bins = pd.cut(
        segments["score"], bins=[0, 40, 55, 70, 85, 100],
        labels=["差", "一般", "较好", "好", "很好"], include_lowest=True,
    )
    mismatch = (bins.astype(str) != segments["grade"]).sum()
    assert mismatch == 0
