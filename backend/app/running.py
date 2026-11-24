# -*- coding: utf-8 -*-
"""慢跑路网构建与闭合环线生成模块。

所属模块：跑步路线算法层。

作用：从评分路段表构建双向跑步图，根据用户偏好计算边代价，在目标距离
半程附近选择折点，并生成回到起点且尽量避免原路往返的候选环线。

图结构：
    评分路段的首尾顶点作为图节点，相邻顶点形成双向边，边上携带路段评分、
    树冠、坡度、路口数和设施距离等属性。

边代价：
    ``距离 × (1 + (100 - 偏好子分) / 40)``。
    偏好子分越低，边权越大，单个低分路段最多按约 3.5 倍距离计费。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]

# 跑步评分数据目录与可重建图缓存目录
RUN = ROOT / "data" / "processed" / "running" / "v1"
CACHE = ROOT / "data" / "processed" / "running" / "graph"

RUN_SPEED_MPS = 2.78          # 路线预计用时采用的基准速度，约 10 km/h
RETRACE_PENALTY = 4.0         # 回程重走去程边的代价倍数；4 与 20 的残余率相近，
                              # 但 20 会明显减少候选数量，因此取 4

# 长度容差（与接口层 LENGTH_TOLERANCE 一致）：候选路线总长须落在 0.85–1.15 倍目标内
LENGTH_LOW = 0.85
LENGTH_HIGH = 1.15

# 折点带：目标距离半程 ±12%
BAND_HALF = 0.12

# 边代价上限：偏好子分取 0 时 1 + (100 - 0) / 40 = 3.5 倍距离
MAX_COST_RATIO = 1.0 + 100.0 / 40.0

# 局部子图半径系数：合法环线总长不超过 1.15 倍目标，环上任一点到起点的直线
# 距离不超过总长一半（0.575 倍目标）；再留 15% 余量，避免贴边路径被误裁
LOOP_RADIUS_RATIO = 0.5 * LENGTH_HIGH * 1.15

# 路线沿线汇总使用的路段属性
ATTRS = ["score", "tree_share", "slope_mean_pct", "cross_200m", "d_fac_m"]

# 用户偏好键到路段子分字段的映射
PREF_KEYS = {"green": "s_green", "flat": "s_slope", "safe": "s_safety"}


@dataclass
class RunGraph:
    """慢跑路网的内存表示。

    所有边数组与 CSR 的非零元素顺序一一对应。
    """

    csr_len: csr_matrix        # 边长度矩阵，单位米
    csr_cost: csr_matrix       # 偏好代价矩阵；每个请求按用户偏好重新构建
    x: np.ndarray              # UTM 50N 东坐标，单位米
    y: np.ndarray              # UTM 50N 北坐标，单位米
    lng: np.ndarray            # WGS84 经度
    lat: np.ndarray            # WGS84 纬度
    edge_attr: dict[str, np.ndarray]   # 每条有向边的原始环境属性
    subs: dict[str, np.ndarray]        # 每条有向边的安全、绿化、坡度子分
    n: int                            # 图节点总数
    # 最近邻 KD 树只在首次吸附时构建；不参与 npz 缓存序列化
    _tree: cKDTree | None = field(default=None, init=False, repr=False)

    def warm(self) -> None:
        """预建最近邻 KD 树；服务启动时调用，避免首个请求承担建树开销。"""
        if self._tree is None:
            self._tree = cKDTree(np.column_stack([self.x, self.y]))

    def nearest(self, lng: float, lat: float) -> tuple[int, float]:
        """把用户坐标吸附到最近图节点，并返回节点索引与距离。"""
        self.warm()
        x, y = _utm(lng, lat)
        d, i = self._tree.query([x, y], k=1)
        return int(i), float(d)


def _utm(lng, lat):
    """把 WGS84 坐标投影到 UTM 50N；同时支持标量和数组。"""
    from pyproj import Transformer

    tr = Transformer.from_crs("EPSG:4326", "EPSG:32650", always_xy=True)
    x, y = tr.transform(lng, lat)
    if np.ndim(lng) == 0:
        return float(x), float(y)
    return np.asarray(x, dtype=float), np.asarray(y, dtype=float)


@dataclass
class LocalGraph:
    """以某节点为中心的局部子图，用于把最短路限制在目标距离附近。

    只保留两端都落在欧氏球内的有向边；节点按全局编号升序排列，因此子图里
    算出的路径可以原样映射回全局节点，继续复用全局属性做路线汇总。
    """

    nodes: np.ndarray        # 局部编号 -> 全局节点编号
    lookup: np.ndarray       # 全局编号 -> 局部编号；球外为 -1
    keep: np.ndarray         # 全局边 -> 是否落在子图内
    length: csr_matrix       # 子图的边长度矩阵
    origin: int              # 起点在子图中的编号

    def subset(self, csr: csr_matrix) -> csr_matrix:
        """按同一结构裁剪任意边矩阵（如偏好代价），保证值与边一一对应。"""
        return csr_matrix(
            (csr.data[self.keep], self.length.indices, self.length.indptr),
            shape=self.length.shape,
        )


def _build_local(g: RunGraph, origin: int, radius: float) -> LocalGraph:
    """裁出以 ``origin`` 为圆心、半径 ``radius`` 米的局部子图。"""
    g.warm()
    nodes = np.asarray(
        g._tree.query_ball_point([g.x[origin], g.y[origin]], radius), dtype=np.int64
    )
    nodes.sort()
    mask = np.zeros(g.n, dtype=bool)
    mask[nodes] = True

    indptr, indices = g.csr_len.indptr, g.csr_len.indices
    counts = np.diff(indptr)
    # 只保留两端都在球内的边；CSR 每行的列已升序，掩码不会打乱原有顺序
    keep = mask[indices] & np.repeat(mask, counts)
    lookup = np.full(g.n, -1, dtype=np.int32)
    lookup[nodes] = np.arange(len(nodes), dtype=np.int32)

    row_of_edge = np.repeat(np.arange(g.n, dtype=np.int64), counts)
    sub_counts = np.bincount(row_of_edge[keep], minlength=g.n)
    sub_indptr = np.zeros(len(nodes) + 1, dtype=np.int64)
    sub_counts_nodes = sub_counts[nodes]
    np.cumsum(sub_counts_nodes, out=sub_indptr[1:])
    cols = np.asarray(lookup[indices[keep]], dtype=np.int64)
    length = csr_matrix(
        (g.csr_len.data[keep], cols, sub_indptr), shape=(len(nodes), len(nodes))
    )
    return LocalGraph(nodes, lookup, keep, length, int(lookup[origin]))


def build(verbose: bool = True) -> RunGraph:
    """根据评分路段表重建慢跑图。"""
    import geopandas as gpd

    def say(m: str) -> None:
        if verbose:
            print(m, flush=True)

    seg = gpd.read_file(RUN / "segments.gpkg", layer="segments").to_crs(32650)
    say(f"[run-graph] {len(seg):,} segments")

    coords_all = []
    rows, cols, lens = [], [], []       # 汇集 CSR 的行、列和边权数据
    attr_vals = {k: [] for k in ATTRS}  # 汇集每条有向边的环境属性
    sub_vals = {k: [] for k in PREF_KEYS.values()}  # 汇集偏好子分
    key_map: dict[tuple[float, float], int] = {}    # 坐标键到连续节点编号
    node_xy: list[tuple[float, float]] = []         # 节点 WGS84 坐标表

    def node_id(lon: float, lat: float) -> int:
        """按六位小数坐标去重，并为新顶点分配连续节点编号。"""
        key = (round(lon, 6), round(lat, 6))
        i = key_map.get(key)
        if i is None:
            i = len(node_xy)
            key_map[key] = i
            node_xy.append((lon, lat))
        return i

    geoms = seg.geometry.to_numpy()
    lls = seg.to_crs(4326).geometry.to_numpy()
    for k, (gm, gl) in enumerate(zip(geoms, lls)):
        xy = np.asarray(shapely.get_coordinates(gm))
        ll = np.asarray(shapely.get_coordinates(gl))
        if len(xy) < 2:
            continue
        u = np.array([node_id(*p) for p in ll[:-1]])
        v = np.array([node_id(*p) for p in ll[1:]])
        step = np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1]))
        ok = step > 0.01
        u, v, step = u[ok], v[ok], step[ok]
        if not len(u):
            continue
        # 同一条道路片段同时加入正向和反向边
        rows += [u, v]
        cols += [v, u]
        lens += [step, step]
        for a in ATTRS:
            attr_vals[a] += [np.full(len(u), seg[a].iloc[k])] * 2
        for a in PREF_KEYS.values():
            sub_vals[a] += [np.full(len(u), seg[a].iloc[k])] * 2

    n = len(node_xy)
    arr = np.array(node_xy)
    x, y = _utm(arr[:, 0], arr[:, 1])
    row = np.concatenate(rows).astype(np.int64)
    col = np.concatenate(cols).astype(np.int64)
    length = np.concatenate(lens).astype(np.float32)
    attr_all = {k: np.concatenate(v).astype(np.float32) for k, v in attr_vals.items()}
    sub_all = {k: np.concatenate(v).astype(np.float32) for k, v in sub_vals.items()}

    # 同一 (u, v) 可能来自多条 OSM 道路，先按端点对去重，再按 (row, col)
    # 排序，确保 CSR 数据顺序与属性数组顺序一致
    key = row * n + col
    _, first = np.unique(key, return_index=True)
    row, col, length = row[first], col[first], length[first]
    attr_all = {k: v[first] for k, v in attr_all.items()}
    sub_all = {k: v[first] for k, v in sub_all.items()}
    order = np.lexsort((col, row))
    row, col, length = row[order], col[order], length[order]
    attr_all = {k: v[order] for k, v in attr_all.items()}
    sub_all = {k: v[order] for k, v in sub_all.items()}
    counts = np.bincount(row, minlength=n)
    indptr = np.concatenate([[0], np.cumsum(counts)]).astype(np.int32)
    csr_len = csr_matrix((length, col.astype(np.int32), indptr), shape=(n, n))
    say(f"[run-graph] {n:,} nodes, {csr_len.nnz:,} directed edges (deduped)")

    g = RunGraph(
        csr_len=csr_len,
        csr_cost=csr_len.copy(),
        x=np.asarray(x),
        y=np.asarray(y),
        lng=arr[:, 0],
        lat=arr[:, 1],
        edge_attr=attr_all,
        subs=sub_all,
        n=n,
    )
    return g


# --------------------------------------------------------------------- 图缓存
def save(g: RunGraph, path: Path = CACHE / "v1" / "run_graph.npz") -> None:
    """把跑步图矩阵、坐标和逐边属性写入压缩缓存。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        data=g.csr_len.data,
        indices=g.csr_len.indices,
        indptr=g.csr_len.indptr,
        x=g.x, y=g.y, lng=g.lng, lat=g.lat,
        **{f"attr_{k}": v for k, v in g.edge_attr.items()},
        **{f"sub_{k}": v for k, v in g.subs.items()},
    )


def load(path: Path = CACHE / "v1" / "run_graph.npz") -> RunGraph:
    """从压缩缓存恢复跑步图。"""
    z = np.load(path, allow_pickle=False)
    n = z["indptr"].shape[0] - 1
    csr = csr_matrix((z["data"], z["indices"], z["indptr"]), shape=(n, n))
    return RunGraph(
        csr_len=csr,
        csr_cost=csr.copy(),
        x=z["x"], y=z["y"], lng=z["lng"], lat=z["lat"],
        edge_attr={k[5:]: z[k] for k in z.files if k.startswith("attr_")},
        subs={k[4:]: z[k] for k in z.files if k.startswith("sub_")},
        n=n,
    )


def load_or_build() -> RunGraph:
    """优先加载现有图缓存，不存在时重建并保存。"""
    p = CACHE / "v1" / "run_graph.npz"
    if p.exists():
        return load(p)
    g = build()
    save(g)
    return g


# --------------------------------------------------------------------- 环线生成
def _pref_score(g: RunGraph, prefs: dict[str, float]) -> np.ndarray:
    """按用户权重合成每条有向边的偏好子分。"""
    total = sum(prefs.values()) or 1.0
    s = np.zeros(g.csr_len.nnz, dtype=np.float64)
    for k, w in prefs.items():
        col = PREF_KEYS[k]
        s += (w / total) * g.subs[col]
    return s


def _cost_matrix(g: RunGraph, pref: np.ndarray) -> csr_matrix:
    """根据偏好子分构建用于最短路计算的边代价矩阵。"""
    penalty = 1.0 + (100.0 - pref) / 40.0
    data = (g.csr_len.data * penalty).astype(np.float32)
    return csr_matrix((data, g.csr_len.indices, g.csr_len.indptr), shape=g.csr_len.shape)


def _path(pred: np.ndarray, start: int, end: int) -> list[int]:
    """根据 Dijkstra 前驱数组回溯从起点到终点的节点序列。"""
    if start == end:
        return [start]
    out = [end]
    cur = end
    while cur != start:
        cur = int(pred[cur])
        if cur < 0:
            return []
        out.append(cur)
    out.reverse()
    return out


def _angular_picks(
    g: RunGraph, origin: int, band: np.ndarray, count: int
) -> list[int]:
    """在候选节点带内按方位角均匀抽样，避免所有路线朝同一方向。"""
    if band.size == 0 or count <= 0:
        return []
    ang = np.arctan2(g.y[band] - g.y[origin], g.x[band] - g.x[origin])
    order = np.argsort(ang)
    count = min(count, len(order))
    if count == 1:
        return [int(band[order[len(order) // 2]])]
    picked = [
        int(band[order[int(i * (len(order) - 1) / (count - 1))]])
        for i in range(count)
    ]
    return list(dict.fromkeys(picked))


def _path_summary(
    g: RunGraph,
    nodes: list[int],
    prefs: dict[str, float],
    *,
    mode: str,
    target_m: float,
    origin_snap_m: float,
    destination_snap_m: float | None = None,
) -> dict | None:
    """把节点路径汇总为带距离、用时、偏好分与解释指标的路线字典。"""
    if len(nodes) < 2:
        return None

    length = 0.0
    attrs = {k: 0.0 for k in ATTRS}
    sub = {k: 0.0 for k in PREF_KEYS.values()}
    for a, b in zip(nodes[:-1], nodes[1:]):
        lo, hi = g.csr_len.indptr[a], g.csr_len.indptr[a + 1]
        pos = lo + np.searchsorted(g.csr_len.indices[lo:hi], b)
        if pos >= hi or g.csr_len.indices[pos] != b:
            continue
        edge_len = float(g.csr_len.data[pos])
        length += edge_len
        for k in ATTRS:
            attrs[k] += g.edge_attr[k][pos] * edge_len
        for k in PREF_KEYS.values():
            sub[k] += g.subs[k][pos] * edge_len

    if length <= 0:
        return None
    for k in ATTRS:
        attrs[k] /= length
    for k in PREF_KEYS.values():
        sub[k] /= length

    pref_score = round(float(pref_score_of(sub, prefs)), 1)
    error = length - target_m
    route = {
        "nodes": nodes,
        "mode": mode,
        "length_m": round(length, 1),
        "target_m": round(float(target_m), 1),
        "target_ok": bool(0.85 * target_m <= length <= 1.15 * target_m),
        "length_error_m": round(error, 1),
        "length_error_pct": round(error / target_m * 100.0, 1),
        "minutes": round(length / RUN_SPEED_MPS / 60.0, 1),
        "score": pref_score,
        "pref_score": pref_score,
        "mean_segment_score": round(float(attrs["score"]), 1),
        "tree_share": round(float(attrs["tree_share"]), 3),
        "slope_mean_pct": round(float(attrs["slope_mean_pct"]), 2),
        "facility_m": round(float(attrs["d_fac_m"]), 0),
        "cross_200m": round(float(attrs["cross_200m"]), 1),
        "sub": {k: round(float(v), 1) for k, v in sub.items()},
        "origin_snap_m": round(float(origin_snap_m), 1),
    }
    if destination_snap_m is not None:
        route["destination_snap_m"] = round(float(destination_snap_m), 1)
    return route


def generate_loops(
    g: RunGraph,
    lng: float,
    lat: float,
    target_m: float,
    prefs: dict[str, float] | None = None,
    max_candidates: int = 8,
    *,
    origin: int | None = None,
    origin_snap_m: float | None = None,
) -> list[dict]:
    """生成最多 ``max_candidates`` 条候选环线，并按偏好匹配分从高到低返回。

    ``origin`` 与 ``origin_snap_m`` 可由接口层传入，避免重复做最近邻吸附。
    """
    prefs = prefs or {"green": 1.0, "safe": 1.0, "flat": 0.6}
    if origin is None:
        origin, snap = g.nearest(lng, lat)
    else:
        snap = float(origin_snap_m or 0.0)
    pref = _pref_score(g, prefs)
    cost = _cost_matrix(g, pref)

    # 1. 从起点计算纯距离场，在目标距离半程附近选取折点；
    #    limit 让搜索在带上界处停下，带上界以外的节点距离为 inf，不参与选点
    half = target_m / 2.0
    band_high = half + BAND_HALF * target_m
    dist_len = dijkstra(g.csr_len, directed=True, indices=origin, limit=band_high)
    band = np.flatnonzero(
        np.isfinite(dist_len) & (np.abs(dist_len - half) <= BAND_HALF * target_m)
    )
    if band.size == 0:
        return []
    picked = _angular_picks(g, origin, band, max_candidates)

    # 2. 合法环线总长不超过 1.15 倍目标，环上任一点到起点的直线距离因此不超过
    #    总长的一半；据此把去程与回程限制在起点附近的局部子图内，单次最短路
    #    从全图 97.9 万节点降到数万节点
    local = _build_local(g, origin, LOOP_RADIUS_RATIO * target_m)
    cost_local = local.subset(cost)
    local_origin = local.origin
    nodes_of = local.nodes

    # 3. 所有折点共用一棵从起点出发的偏好最短路前驱树
    _, pred_out = dijkstra(
        cost_local, directed=True, indices=local_origin, return_predecessors=True
    )

    loops = []
    for via in picked:
        via_local = int(local.lookup[via])
        if via_local < 0:
            continue
        out = [int(nodes_of[i]) for i in _path(pred_out, local_origin, via_local)]
        if len(out) < 2:
            continue
        # 4. 提高去程边在回程中的代价，再从折点寻找返回路径
        used = set()
        for a, b in zip(out[:-1], out[1:]):
            la, lb = int(local.lookup[a]), int(local.lookup[b])
            if la >= 0 and lb >= 0:
                used.add((la, lb))
        data = cost_local.data.copy()
        indptr, indices = cost_local.indptr, cost_local.indices
        for a, b in used:
            for u, v in ((a, b), (b, a)):      # 正向和反向同时惩罚
                lo, hi = indptr[u], indptr[u + 1]
                pos = lo + np.searchsorted(indices[lo:hi], v)
                if pos < hi and indices[pos] == v:
                    data[pos] *= RETRACE_PENALTY
        cost_back = csr_matrix((data, indices, indptr), shape=cost_local.shape)
        _, pred_back = dijkstra(
            cost_back, directed=True, indices=via_local, return_predecessors=True
        )
        back = [int(nodes_of[i]) for i in _path(pred_back, via_local, local_origin)]
        if len(back) < 2:
            continue

        nodes = out + back[1:]
        route = _path_summary(
            g,
            nodes,
            prefs,
            mode="loop",
            target_m=target_m,
            origin_snap_m=snap,
        )
        if route is None or not route["target_ok"]:
            continue
        # 候选去重：与已保留环线共享超过一半节点时拒绝
        if any(
            len(set(nodes) & set(other["nodes"])) > 0.5 * len(set(nodes))
            for other in loops
        ):
            continue
        loops.append(route)

    loops.sort(key=lambda r: -r["score"])
    return loops


def generate_oneway(
    g: RunGraph,
    lng: float,
    lat: float,
    target_m: float,
    prefs: dict[str, float] | None = None,
    max_candidates: int = 8,
    *,
    end_lng: float | None = None,
    end_lat: float | None = None,
    origin: int | None = None,
    origin_snap_m: float | None = None,
    destination: int | None = None,
    destination_snap_m: float | None = None,
) -> list[dict]:
    """生成 A→B 单行线。

    未给终点时，在距起点 0.85–1.15 倍目标距离的节点带内按方位角选择
    候选终点；给了 ``end_lng/end_lat`` 时以该终点为准，实际距离可能偏离
    目标距离，因此返回 ``target_ok`` 供前端提示。
    """
    prefs = prefs or {"green": 1.0, "safe": 1.0, "flat": 0.6}
    if origin is None:
        origin, snap = g.nearest(lng, lat)
    else:
        snap = float(origin_snap_m or 0.0)
    pref = _pref_score(g, prefs)
    cost = _cost_matrix(g, pref)

    if end_lng is not None and end_lat is not None:
        if destination is None:
            destination, dest_snap = g.nearest(end_lng, end_lat)
        else:
            dest_snap = float(destination_snap_m or 0.0)
        if destination == origin:
            return []
        _, pred = dijkstra(cost, directed=True, indices=origin, return_predecessors=True)
        nodes = _path(pred, origin, destination)
        route = _path_summary(
            g,
            nodes,
            prefs,
            mode="oneway",
            target_m=target_m,
            origin_snap_m=snap,
            destination_snap_m=dest_snap,
        )
        return [route] if route is not None else []

    # 自动选择终点：纯距离场落在目标距离 85%–115% 的节点；
    # limit 让搜索在带上界处停下，带上界以外的节点距离为 inf，不参与选点
    dist_len = dijkstra(
        g.csr_len, directed=True, indices=origin, limit=LENGTH_HIGH * target_m
    )
    band = np.flatnonzero(
        np.isfinite(dist_len)
        & (dist_len >= LENGTH_LOW * target_m)
        & (dist_len <= LENGTH_HIGH * target_m)
    )
    if band.size == 0:
        return []

    # 多取一些终点再过滤，避免偏好路径因绕行而超出长度容差；
    # 单条路径的代价不超过 3.5 倍长度，限到 3.5×1.15×目标即可保证最优解不被裁掉
    picked = _angular_picks(g, origin, band, max(max_candidates * 4, 8))
    _, pred = dijkstra(
        cost,
        directed=True,
        indices=origin,
        limit=MAX_COST_RATIO * LENGTH_HIGH * target_m,
        return_predecessors=True,
    )

    routes = []
    for via in picked:
        nodes = _path(pred, origin, via)
        route = _path_summary(
            g,
            nodes,
            prefs,
            mode="oneway",
            target_m=target_m,
            origin_snap_m=snap,
        )
        if route is None or not route["target_ok"]:
            continue
        if any(
            len(set(nodes) & set(other["nodes"])) > 0.5 * len(set(nodes))
            for other in routes
        ):
            continue
        routes.append(route)
        if len(routes) >= max_candidates:
            break

    routes.sort(key=lambda r: -r["score"])
    return routes


def pref_score_of(sub: dict[str, float], prefs: dict[str, float]) -> float:
    """按用户偏好权重计算一组路线子分的加权匹配分。"""
    total = sum(prefs.values()) or 1.0
    return sum(prefs[k] / total * sub[PREF_KEYS[k]] for k in prefs)


def loop_geometry(g: RunGraph, loop: dict) -> list[list[float]]:
    """把环线节点索引转换为 WGS84 经纬度坐标序列。"""
    return [[float(g.lng[i]), float(g.lat[i])] for i in loop["nodes"]]


def to_geojson(g: RunGraph, routes: list[dict], name: str = "route") -> dict:
    """把候选路线转换为带排序、起终点和解释属性的 GeoJSON FeatureCollection。"""
    feats = []
    for i, route in enumerate(routes, 1):
        props = {
            k: (float(v) if isinstance(v, (float, np.floating)) else
                int(v) if isinstance(v, (int, np.integer)) and not isinstance(v, (bool, np.bool_))
                else bool(v) if isinstance(v, (bool, np.bool_)) else v)
            for k, v in route.items() if k not in ("nodes", "sub")
        }
        nodes = route["nodes"]
        props["sub"] = json.dumps(route["sub"])
        props["rank"] = i
        props["name"] = name
        props["start_lng"] = round(float(g.lng[nodes[0]]), 6)
        props["start_lat"] = round(float(g.lat[nodes[0]]), 6)
        props["end_lng"] = round(float(g.lng[nodes[-1]]), 6)
        props["end_lat"] = round(float(g.lat[nodes[-1]]), 6)
        feats.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": {"type": "LineString", "coordinates": loop_geometry(g, route)},
            }
        )
    return {"type": "FeatureCollection", "features": feats}
