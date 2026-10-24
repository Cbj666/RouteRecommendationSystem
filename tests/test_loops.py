# -*- coding: utf-8 -*-
"""环线生成的不变量。"""
from __future__ import annotations


def test_graph_loaded(graph):
    assert graph.n > 900_000
    assert graph.csr_len.nnz > 2_000_000


def test_loop_is_closed(loops):
    for lp in loops:
        assert lp["nodes"][0] == lp["nodes"][-1], "环线首尾必须是同一个节点"


def test_loop_length_within_tolerance(loops):
    for lp in loops:
        assert 0.85 * 5000 <= lp["length_m"] <= 1.15 * 5000, lp["length_m"]


def test_loop_score_range(loops):
    for lp in loops:
        assert 0 <= lp["score"] <= 100


def test_loop_has_explainable_subscores(loops):
    for lp in loops:
        assert set(lp["sub"]) == {"s_safety", "s_green", "s_slope"}


def test_retrace_is_limited(graph, loops):
    """不要求 0（湖岸单线绕不开），但整体不能大面积原路返回。"""
    for lp in loops:
        nodes = lp["nodes"]
        pairs = list(zip(nodes[:-1], nodes[1:]))
        reverse = {(b, a) for a, b in pairs}
        hit = len({p for p in pairs if p in reverse})
        assert hit / len(pairs) < 0.20, f"{hit}/{len(pairs)} 条边原路返回"


def test_deterministic(graph):
    a = graph and __import__("app.running", fromlist=["x"]).generate_loops(
        graph, 114.3547, 30.5342, 5000
    )
    b = __import__("app.running", fromlist=["x"]).generate_loops(
        graph, 114.3547, 30.5342, 5000
    )
    assert [x["length_m"] for x in a] == [x["length_m"] for x in b]
