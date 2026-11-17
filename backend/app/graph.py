# -*- coding: utf-8 -*-
"""多模式交通图构建与缓存模块。

所属模块：基础图算法层（前版本保留能力）。

作用：把步行路网、公交和地铁组织为 SciPy CSR 稀疏图，统一保存节点类型、
空间坐标、换乘关系和以秒为单位的边权。当前项目主要复用其中的步行路网和
路口统计能力；历史等时圈计算仍依赖本模块，因此继续保留。

节点类型：
    0  步行路网顶点
    1  公交站点（道路层面的上车点）
    2  地铁站点（道路层面的上车点）
    3  公交站台（按线路、方向和站序展开）
    4  地铁站台

边权语义（全部为有向边，单位秒）：
    步行顶点 <-> 步行顶点       长度 / 步行速度
    步行顶点 <-> 站点           接驳距离 / 步行速度
    站点     -> 站台            候车时间
    站台(a)  -> 站台(b)         乘车时间（沿线里程 / 速度 + 停站）
    站台     -> 站点            0

站点与站台分离后，下车不额外计时，再次上车会重新计算候车时间，从而使
换乘成本自然体现在最短路结果中。
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyogrio
import shapely
from scipy.sparse import csr_matrix
from scipy.spatial import cKDTree

from .config import DEFAULT, Params
from .paths import GRAPH_CACHE as CACHE
from .paths import V1

# 图节点类型编码
WALK, BUS_STOP, METRO_STOP, BUS_PLATFORM, METRO_PLATFORM = 0, 1, 2, 3, 4

# 节点类型到可读名称的映射，主要用于调试和路径解释
KIND_NAMES = {
    WALK: "walk",
    BUS_STOP: "bus_stop",
    METRO_STOP: "metro_stop",
    BUS_PLATFORM: "bus_platform",
    METRO_PLATFORM: "metro_platform",
}


@dataclass
class Graph:
    """多模式交通图的内存表示。

    所有节点数组按同一索引对齐；``csr`` 的边权单位为秒。
    """

    csr: csr_matrix
    kind: np.ndarray          # int8，节点类型编码
    x: np.ndarray             # UTM 50N 东坐标，单位米
    y: np.ndarray             # UTM 50N 北坐标，单位米
    lng: np.ndarray           # WGS84 经度
    lat: np.ndarray           # WGS84 纬度
    named_idx: np.ndarray     # 带业务编号的节点索引，主要是站点和站台
    named_id: np.ndarray      # 带业务编号节点的唯一标识
    named_name: np.ndarray    # 带业务编号节点的显示名称
    walk_comp_size: np.ndarray  # 每个步行顶点所属连通分量的规模
    n_walk: int               # 步行路网顶点数量；其余节点从该位置开始
    params: Params            # 建图时使用的参数快照
    stats: dict               # 建图规模、接驳距离、连通性等统计信息
    _kd: object | None = None  # 最大步行连通分量的延迟构建 KD 树缓存

    def kdtree(self):
        """返回覆盖主要步行连通分量的 KD 树，并在实例内缓存。"""
        if self._kd is None:
            from scipy.spatial import cKDTree

            major = self.walk_comp_size[: self.n_walk] >= max(1000, 0.01 * self.n_walk)
            self._major_index = np.flatnonzero(major)
            self._kd = cKDTree(
                np.column_stack(
                    [self.x[self._major_index], self.y[self._major_index]]
                )
            )
        return self._kd

    @property
    def n_nodes(self) -> int:
        """图中节点总数。"""
        return int(self.kind.shape[0])

    def id_to_index(self) -> dict[str, int]:
        """把业务节点标识映射到图内索引。"""
        return dict(zip(self.named_id.tolist(), self.named_idx.tolist()))

    def nodes_of_kind(self, kind: int) -> np.ndarray:
        """返回指定节点类型对应的全部图索引。"""
        return np.flatnonzero(self.kind == kind)

    def save(self, path: Path) -> None:
        """把图数组和参数统计写入压缩缓存文件。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            data=self.csr.data.astype(np.float32),
            indices=self.csr.indices.astype(np.int32),
            indptr=self.csr.indptr.astype(np.int32),
            kind=self.kind,
            x=self.x,
            y=self.y,
            lng=self.lng,
            lat=self.lat,
            named_idx=self.named_idx,
            named_id=self.named_id,
            named_name=self.named_name,
            walk_comp_size=self.walk_comp_size,
            n_walk=np.array([self.n_walk]),
        )
        path.with_suffix(".meta.pkl").write_bytes(
            pickle.dumps({"params": self.params, "stats": self.stats})
        )

    @classmethod
    def load(cls, path: Path) -> "Graph":
        """从缓存文件恢复多模式交通图。"""
        z = np.load(path, allow_pickle=False)
        n = z["indptr"].shape[0] - 1
        csr = csr_matrix((z["data"], z["indices"], z["indptr"]), shape=(n, n))
        meta = pickle.loads(Path(path).with_suffix(".meta.pkl").read_bytes())
        return cls(
            csr=csr,
            kind=z["kind"],
            x=z["x"],
            y=z["y"],
            lng=z["lng"],
            lat=z["lat"],
            named_idx=z["named_idx"],
            named_id=z["named_id"],
            named_name=z["named_name"],
            walk_comp_size=z["walk_comp_size"],
            n_walk=int(z["n_walk"][0]),
            params=meta["params"],
            stats=meta["stats"],
        )


# --------------------------------------------------------------------- 通用辅助函数
def _utm(lng: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """把 WGS84 经纬度转换为 UTM 50N 米制坐标。"""
    from pyproj import Transformer

    tr = Transformer.from_crs("EPSG:4326", "EPSG:32650", always_xy=True)
    x, y = tr.transform(np.asarray(lng, float), np.asarray(lat, float))
    return np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)


def _read_walk_network():
    """读取步行路网并返回去重顶点、相邻边、长度和米制坐标。"""
    gdf = pyogrio.read_dataframe(V1 / "osm_walk_roads.gpkg", layer="walk_roads")
    geoms = gdf.geometry.to_numpy()
    counts = shapely.get_num_coordinates(geoms)
    coords = shapely.get_coordinates(geoms)
    uk, inv = np.unique(np.round(coords, 6), axis=0, return_inverse=True)

    starts = np.concatenate(([0], np.cumsum(counts)[:-1]))
    a, b = inv[:-1], inv[1:]
    keep = np.ones(len(a), dtype=bool)
    keep[starts[1:] - 1] = False          # 不把相邻 OSM way 的端点强行连成边
    a, b = a[keep], b[keep]

    x, y = _utm(uk[:, 0], uk[:, 1])
    seg_len = np.hypot(x[b] - x[a], y[b] - y[a])
    ok = (seg_len > 0.01) & (a != b)
    return uk, a[ok], b[ok], seg_len[ok], x, y


def metro_wait_by_line() -> dict[str, float]:
    """按工作日最小发车间隔估算各条地铁线路的平均候车时间。"""
    sched = pd.read_csv(V1 / "metro_schedule.csv")
    out: dict[str, float] = {}
    for lid, grp in sched[sched["day_type"] == "weekday"].groupby("line_id"):
        out[str(lid)] = max(90.0, float(grp["interval_seconds"].min()) / 2.0)
    return out


# ----------------------------------------------------------------------- 图构建
def build(params: Params = DEFAULT, verbose: bool = True) -> Graph:
    """根据冻结基础数据和给定参数构建多模式交通图。"""

    def say(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    say("[graph] reading walk network ...")
    uk, seg_a, seg_b, seg_len, wx, wy = _read_walk_network()
    n_walk = len(uk)
    say(f"[graph] walk nodes {n_walk:,}, segments {len(seg_a):,}")

    # 以数组列表暂存所有边，最后统一拼接为 CSR
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    vals: list[np.ndarray] = []

    # 步行路网边权：相邻顶点之间的秒制通行时间
    w = seg_len / params.walk_speed_mps
    rows += [seg_a, seg_b]
    cols += [seg_b, seg_a]
    vals += [w, w]

    # 计算步行路网连通分量，后续站点吸附优先使用最大连通分量
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    w_csr = coo_matrix(
        (np.ones(len(seg_a), dtype=np.int8), (seg_a, seg_b)), shape=(n_walk, n_walk)
    ).tocsr()
    ncomp, labels = connected_components(w_csr, directed=False)
    sizes = np.bincount(labels)
    walk_comp = sizes[labels].astype(np.int32)
    big_index = np.flatnonzero(walk_comp == walk_comp.max())
    del w_csr
    say(
        f"[graph] walk components {ncomp:,}, largest {int(walk_comp.max()):,} vertices "
        f"({100 * walk_comp.max() / n_walk:.1f}%)"
    )

    # 读取公交和地铁站点，并把站点匹配到步行路网
    bus = pd.read_csv(V1 / "stops_bus.csv")
    metro = pd.read_csv(V1 / "stops_metro.csv")
    n_bus, n_metro = len(bus), len(metro)
    bus0 = n_walk
    metro0 = n_walk + n_bus
    next_node = metro0 + n_metro

    # 业务站点编号到图节点索引的映射
    stop_index: dict[str, int] = {}
    stop_index.update({nid: bus0 + i for i, nid in enumerate(bus["node_id"])})
    stop_index.update({nid: metro0 + i for i, nid in enumerate(metro["node_id"])})

    # 车站类节点及其业务标识、显示名称
    named_idx: list[int] = list(range(bus0, metro0)) + list(range(metro0, next_node))
    named_id: list[str] = list(bus["node_id"]) + list(metro["node_id"])
    named_name: list[str] = list(bus["name"].astype(str)) + list(metro["name"].astype(str))

    say("[graph] snapping stops to the walk network ...")
    tree = cKDTree(np.column_stack([wx[big_index], wy[big_index]]))
    tree_all = cKDTree(np.column_stack([wx, wy]))
    b_lng = bus["snap_lng"].fillna(bus["lng"]).to_numpy()
    b_lat = bus["snap_lat"].fillna(bus["lat"]).to_numpy()
    m_lng = metro["snap_lng"].fillna(metro["lng"]).to_numpy()
    m_lat = metro["snap_lat"].fillna(metro["lat"]).to_numpy()
    all_lng = np.concatenate([b_lng, m_lng])
    all_lat = np.concatenate([b_lat, m_lat])
    sx, sy = _utm(all_lng, all_lat)
    q = np.column_stack([sx, sy])
    acc_d, acc_i = (np.asarray(v) for v in tree.query(q, k=1))
    if tree_all is not None:
        acc_i = big_index[acc_i]
        # 对落在小连通片段附近的站点，退回全路网最近顶点
        far = acc_d > 400.0
        if far.any():
            d2, i2 = (np.asarray(v) for v in tree_all.query(q[far], k=1))
            acc_d[far] = d2
            acc_i[far] = i2
    stop_nodes = np.arange(bus0, next_node)
    ok = acc_d <= params.walk_access_max_m
    acc_w = acc_d[ok] / params.walk_speed_mps
    rows += [stop_nodes[ok], acc_i[ok]]
    cols += [acc_i[ok], stop_nodes[ok]]
    vals += [acc_w, acc_w]
    say(
        f"[graph] access edges {int(ok.sum())}/{len(ok)} "
        f"(median {np.median(acc_d):.1f} m, max {acc_d.max():.1f} m"
        f"{', dropped ' + str(int((~ok).sum())) if (~ok).any() else ''})"
    )

    # 把线路展开为站台节点，并建立候车、乘车和下车边
    say("[graph] expanding routes into platforms ...")
    bus_rs = pd.read_csv(V1 / "bus_route_stops.csv")
    bus_ed = pd.read_csv(V1 / "edges_bus.csv")
    met_rs = pd.read_csv(V1 / "metro_route_stops.csv")
    met_ed = pd.read_csv(V1 / "edges_metro.csv")

    # 站台节点属性；地铁站台另存索引，便于回填节点类型
    platform_rows: list[int] = []
    platform_ids: list[str] = []
    platform_names: list[str] = []
    platform_lng: list[float] = []
    platform_lat: list[float] = []
    metro_platform_rows: list[int] = []

    def add_routes(
        rs: pd.DataFrame,
        ed: pd.DataFrame,
        mode: str,
        kind_code: int,
        wait: float | dict[str, float],
        metro_flag: bool,
    ) -> tuple[int, float, float]:
        """把一条交通线路的站序展开为站台节点和乘车边。"""

        nonlocal next_node
        # 相邻站序的沿线里程；缺少沿线值时用直线距离乘经验系数估算
        ride = {
            (str(r.line_id), int(r.from_sequence), int(r.to_sequence)): (
                float(r.dist_route_m)
                if np.isfinite(r.dist_route_m)
                else float(r.distance_m) * 1.2
            )
            for r in ed.itertuples()
        }
        n_plat = 0
        sum_wait = 0.0
        sum_ride = 0.0
        for lid, grp in rs.groupby("line_id"):
            grp = grp.sort_values("sequence")
            w_line = (
                wait if isinstance(wait, float)
                else wait.get(str(lid), params.metro_wait_fallback_s)
            )
            nodes: list[int] = []
            seqs = grp["sequence"].to_numpy()
            node_ids = grp["node_id"].tolist()
            names = grp["station_name"].astype(str).tolist()
            lngs = grp["lng_wgs84"].to_numpy()
            lats = grp["lat_wgs84"].to_numpy()
            for seq, node_id, name, plng, plat in zip(seqs, node_ids, names, lngs, lats):
                p = next_node
                next_node += 1
                platform_rows.append(p)
                platform_ids.append(f"P-{mode}-{lid}-{seq}")
                platform_names.append(name)
                platform_lng.append(float(plng))
                platform_lat.append(float(plat))
                nodes.append(p)
                n_plat += 1
                stop = stop_index.get(node_id)
                if stop is not None:
                    rows.append(np.array([stop]))
                    cols.append(np.array([p]))
                    vals.append(np.array([w_line]))
                    rows.append(np.array([p]))
                    cols.append(np.array([stop]))
                    vals.append(np.array([0.0]))
                    sum_wait += w_line
                if metro_flag:
                    metro_platform_rows.append(p)
            for k in range(1, len(nodes)):
                d = ride.get((str(lid), int(seqs[k - 1]), int(seqs[k])))
                if d is None:
                    continue
                t = params.ride_time(mode, d)
                rows.append(np.array([nodes[k - 1]]))
                cols.append(np.array([nodes[k]]))
                vals.append(np.array([t]))
                sum_ride += t
        return n_plat, sum_wait, sum_ride

    p_bus, w_bus, r_bus = add_routes(
        bus_rs, bus_ed, "bus", BUS_PLATFORM, params.bus_wait_s, False
    )
    say(f"[graph] bus platforms {p_bus:,}")
    m_wait = metro_wait_by_line()
    p_met, w_met, r_met = add_routes(
        met_rs, met_ed, "metro", METRO_PLATFORM, m_wait, True
    )
    say(f"[graph] metro platforms {p_met:,} (wait {min(m_wait.values()):.0f}–{max(m_wait.values()):.0f} s)")

    n_nodes = next_node
    row = np.concatenate(rows)
    col = np.concatenate(cols)
    val = np.concatenate(vals).astype(np.float32)
    csr = csr_matrix((val, (row, col)), shape=(n_nodes, n_nodes))

    kind = np.zeros(n_nodes, dtype=np.int8)
    kind[bus0:metro0] = BUS_STOP
    kind[metro0:metro0 + n_metro] = METRO_STOP
    kind[np.asarray(platform_rows, dtype=np.int64)] = BUS_PLATFORM
    kind[np.asarray(metro_platform_rows, dtype=np.int64)] = METRO_PLATFORM

    plng = np.asarray(platform_lng, dtype=np.float64)
    plat = np.asarray(platform_lat, dtype=np.float64)
    px, py = _utm(plng, plat)

    lng = np.concatenate([uk[:, 0], all_lng, plng])
    lat = np.concatenate([uk[:, 1], all_lat, plat])
    x = np.concatenate([wx, sx, px])
    y = np.concatenate([wy, sy, py])

    named_idx_arr = np.asarray(named_idx + platform_rows, dtype=np.int64)
    named_id_arr = np.asarray(named_id + platform_ids, dtype="U48")
    named_name_arr = np.asarray(named_name + platform_names, dtype="U48")

    walk_comp_size = np.zeros(n_nodes, dtype=np.int32)
    walk_comp_size[:n_walk] = walk_comp

    # 建图结果摘要，便于日志检查、缓存复核和报告引用
    stats = {
        "n_nodes": int(n_nodes),
        "n_walk_nodes": int(n_walk),
        "n_bus_stops": int(n_bus),
        "n_metro_stops": int(n_metro),
        "n_platforms": int(p_bus + p_met),
        "n_edges": int(csr.nnz),
        "n_directed_walk": int(2 * len(seg_a)),
        "access_median_m": round(float(np.median(acc_d)), 2),
        "access_max_m": round(float(acc_d.max()), 2),
        "access_dropped": int((~ok).sum()),
        "walk_components": int(ncomp),
        "walk_largest_component": int(walk_comp.max()),
    }
    say(f"[graph] done: {stats}")

    return Graph(
        csr=csr,
        kind=kind,
        x=x,
        y=y,
        lng=lng,
        lat=lat,
        named_idx=named_idx_arr,
        named_id=named_id_arr,
        named_name=named_name_arr,
        walk_comp_size=walk_comp_size,
        n_walk=n_walk,
        params=params,
        stats=stats,
    )


def load_or_build(cache: bool = True, params: Params = DEFAULT, verbose: bool = True) -> Graph:
    """优先加载图缓存；缓存不存在时重新构建并按需写回。"""
    path = CACHE / "v1" / "multimodal.npz"
    if cache and path.exists():
        if verbose:
            print(f"[graph] loading cache {path}", flush=True)
        return Graph.load(path)
    g = build(params=params, verbose=verbose)
    if cache:
        g.save(path)
        if verbose:
            print(f"[graph] cached -> {path}", flush=True)
    return g
