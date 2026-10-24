# -*- coding: utf-8 -*-
"""Running route (loop) generation on the scored walk network.

A loop is built the way a runner would: pick a turning point roughly half the
target distance away, go out, and come back on a *different* path. Edges used
on the way out are penalised on the way back, which is what stops the round
trip collapsing into an out-and-back.

Graph
    vertices of `segments.gpkg`, consecutive pairs as directed edges, carrying
    the segment score, tree share, slope and facility distance.

Cost
    distance × (1 + (100 - preference score) / 40)
    so a low-scoring edge effectively costs up to 3.5× its length.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "data" / "processed" / "running" / "v1"
CACHE = ROOT / "data" / "processed" / "running" / "graph"

RUN_SPEED_MPS = 2.78          # 10 km/h
RETRACE_PENALTY = 4.0         # 回程重走去程边的代价倍数；实测 4 与 20 的残余率相同（~4%），
                              # 但 20 会把候选从 13 条压到 9 条，故取 4
ATTRS = ["score", "tree_share", "slope_mean_pct", "cross_200m", "d_fac_m"]
PREF_KEYS = {"green": "s_green", "flat": "s_slope", "safe": "s_safety"}


@dataclass
class RunGraph:
    csr_len: csr_matrix        # metres
    csr_cost: csr_matrix       # preference cost, rebuilt per request
    x: np.ndarray
    y: np.ndarray
    lng: np.ndarray
    lat: np.ndarray
    edge_attr: dict[str, np.ndarray]   # per directed-edge attributes
    subs: dict[str, np.ndarray]        # per directed-edge sub-scores
    n: int

    def nearest(self, lng: float, lat: float) -> tuple[int, float]:
        tree = cKDTree(np.column_stack([self.x, self.y]))
        x, y = _utm(lng, lat)
        d, i = tree.query([x, y], k=1)
        return int(i), float(d)


def _utm(lng, lat):
    """Project WGS84 to UTM 50N; works for scalars and arrays."""
    from pyproj import Transformer

    tr = Transformer.from_crs("EPSG:4326", "EPSG:32650", always_xy=True)
    x, y = tr.transform(lng, lat)
    if np.ndim(lng) == 0:
        return float(x), float(y)
    return np.asarray(x, dtype=float), np.asarray(y, dtype=float)


def build(verbose: bool = True) -> RunGraph:
    import geopandas as gpd

    def say(m: str) -> None:
        if verbose:
            print(m, flush=True)

    seg = gpd.read_file(RUN / "segments.gpkg", layer="segments").to_crs(32650)
    say(f"[run-graph] {len(seg):,} segments")

    coords_all = []
    rows, cols, lens = [], [], []
    attr_vals = {k: [] for k in ATTRS}
    sub_vals = {k: [] for k in PREF_KEYS.values()}
    key_map: dict[tuple[float, float], int] = {}
    node_xy: list[tuple[float, float]] = []

    def node_id(lon: float, lat: float) -> int:
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
        # add both directions
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

    # the same (u, v) can come from several OSM ways: keep one edge per pair and
    # sort by (row, col) so the CSR data order matches our attribute order
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


# --------------------------------------------------------------------- cache
def save(g: RunGraph, path: Path = CACHE / "v1" / "run_graph.npz") -> None:
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
    p = CACHE / "v1" / "run_graph.npz"
    if p.exists():
        return load(p)
    g = build()
    save(g)
    return g


# --------------------------------------------------------------------- loops
def _pref_score(g: RunGraph, prefs: dict[str, float]) -> np.ndarray:
    total = sum(prefs.values()) or 1.0
    s = np.zeros(g.csr_len.nnz, dtype=np.float64)
    for k, w in prefs.items():
        col = PREF_KEYS[k]
        s += (w / total) * g.subs[col]
    return s


def _cost_matrix(g: RunGraph, pref: np.ndarray) -> csr_matrix:
    penalty = 1.0 + (100.0 - pref) / 40.0
    data = (g.csr_len.data * penalty).astype(np.float32)
    return csr_matrix((data, g.csr_len.indices, g.csr_len.indptr), shape=g.csr_len.shape)


def _path(pred: np.ndarray, start: int, end: int) -> list[int]:
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


def generate_loops(
    g: RunGraph,
    lng: float,
    lat: float,
    target_m: float,
    prefs: dict[str, float] | None = None,
    max_candidates: int = 8,
) -> list[dict]:
    """Return up to `max_candidates` loops, best first."""
    prefs = prefs or {"green": 1.0, "safe": 1.0, "flat": 0.6}
    origin, snap = g.nearest(lng, lat)
    pref = _pref_score(g, prefs)
    cost = _cost_matrix(g, pref)

    # 1) distance field from origin -> candidate turning points at L/2
    dist_len = dijkstra(g.csr_len, directed=True, indices=origin)
    half = target_m / 2.0
    band = np.flatnonzero(np.isfinite(dist_len) & (np.abs(dist_len - half) <= 0.12 * target_m))
    if band.size == 0:
        return []
    # spatial diversity: keep the farthest-from-each-other nodes by angle
    ang = np.arctan2(g.y[band] - g.y[origin], g.x[band] - g.x[origin])
    order = np.argsort(ang)
    picked = [band[order[int(i * (len(order) - 1) / (max_candidates - 1))]]
              for i in range(max_candidates)]
    picked = list(dict.fromkeys(int(v) for v in picked))

    # 2) outbound paths share one predecessor tree
    _, pred_out = dijkstra(cost, directed=True, indices=origin, return_predecessors=True)

    loops = []
    for via in picked:
        out = _path(pred_out, origin, via)
        if len(out) < 2:
            continue
        # 3) penalise outbound edges, route back from via
        used = {(a, b) for a, b in zip(out[:-1], out[1:])}
        data = cost.data.copy()
        indptr, indices = cost.indptr, cost.indices
        for a, b in used:
            for u, v in ((a, b), (b, a)):      # penalise both directions
                lo, hi = indptr[u], indptr[u + 1]
                pos = lo + np.searchsorted(indices[lo:hi], v)
                if pos < hi and indices[pos] == v:
                    data[pos] *= RETRACE_PENALTY
        cost_back = csr_matrix((data, indices, indptr), shape=cost.shape)
        dd, pred_back = dijkstra(
            cost_back, directed=True, indices=via, return_predecessors=True
        )
        back = _path(pred_back, via, origin)
        if len(back) < 2:
            continue

        nodes = out + back[1:]
        length = sum(float(g.csr_len[a, b]) for a, b in zip(nodes[:-1], nodes[1:]))
        if not (0.85 * target_m <= length <= 1.15 * target_m):
            continue
        # dedupe: reject loops sharing half their nodes with a better one
        if any(len(set(nodes) & set(l["nodes"])) > 0.5 * len(set(nodes)) for l in loops):
            continue

        attrs = {k: 0.0 for k in ATTRS}
        sub = {k: 0.0 for k in PREF_KEYS.values()}
        for a, b in zip(nodes[:-1], nodes[1:]):
            lo, hi = g.csr_len.indptr[a], g.csr_len.indptr[a + 1]
            pos = lo + np.searchsorted(g.csr_len.indices[lo:hi], b)
            if pos < hi and g.csr_len.indices[pos] == b:
                L = float(g.csr_len.data[pos])
                for k in ATTRS:
                    attrs[k] += g.edge_attr[k][pos] * L
                for k in PREF_KEYS.values():
                    sub[k] += g.subs[k][pos] * L
        for k in ATTRS:
            attrs[k] /= max(length, 1e-6)
        for k in PREF_KEYS.values():
            sub[k] /= max(length, 1e-6)

        loops.append(
            {
                "nodes": nodes,
                "length_m": round(length, 1),
                "minutes": round(length / RUN_SPEED_MPS / 60, 1),
                "score": round(float(pref_score_of(sub, prefs)), 1),
                "tree_share": round(attrs["tree_share"], 3),
                "slope_mean_pct": round(attrs["slope_mean_pct"], 2),
                "facility_m": round(attrs["d_fac_m"], 0),
                "sub": {k: round(float(v), 1) for k, v in sub.items()},
                "origin_snap_m": round(snap, 1),
            }
        )

    loops.sort(key=lambda r: -r["score"])
    return loops


def pref_score_of(sub: dict[str, float], prefs: dict[str, float]) -> float:
    total = sum(prefs.values()) or 1.0
    return sum(prefs[k] / total * sub[PREF_KEYS[k]] for k in prefs)


def loop_geometry(g: RunGraph, loop: dict) -> list[list[float]]:
    return [[float(g.lng[i]), float(g.lat[i])] for i in loop["nodes"]]


def to_geojson(g: RunGraph, loops: list[dict], name: str = "loop") -> dict:
    feats = []
    for i, lp in enumerate(loops, 1):
        props = {
            k: (float(v) if isinstance(v, (float, np.floating)) else
                int(v) if isinstance(v, (int, np.integer)) else v)
            for k, v in lp.items() if k not in ("nodes", "sub")
        }
        props["sub"] = json.dumps(lp["sub"])
        props["rank"] = i
        feats.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": {"type": "LineString", "coordinates": loop_geometry(g, lp)},
            }
        )
    return {"type": "FeatureCollection", "features": feats}
