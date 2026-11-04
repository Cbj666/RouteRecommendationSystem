"""演示脚本：环线 / 单行线 / 马拉松 三种路线模式 + 空气暴露剂量。

只做算法演示与出图，不改动 app/ 里的任何模块。
运行：.venv\\Scripts\\python.exe build\\demo_routes.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from scipy.sparse.csgraph import dijkstra
from scipy.sparse import csr_matrix

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app import running  # noqa: E402

RAW = ROOT / "data" / "raw" / "chap"
PROC = ROOT / "data" / "processed" / "running" / "v1"
OUT = ROOT / "data" / "output" / "running" / "v1" / "demo"
OUT.mkdir(parents=True, exist_ok=True)

RUN_SPEED_MPS = running.RUN_SPEED_MPS


# ---------------------------------------------------------------- 空气网格
def load_grid(name: str, var: str):
    path = RAW / name
    with rasterio.open(path) as src:
        arr = src.read(1)
        tr = src.transform
        scale = float(src.tags().get(f"{var}#scale_factor", 0.1))
        nodata = src.nodata if src.nodata is not None else 65535
    return arr, tr, scale, nodata


def sample_grid(arr, tr, scale, nodata, lng, lat):
    col = np.floor((lng - tr.c) / tr.a).astype(np.int64)
    row = np.floor((lat - tr.f) / tr.e).astype(np.int64)
    ok = (row >= 0) & (row < arr.shape[0]) & (col >= 0) & (col < arr.shape[1])
    out = np.full(lng.shape, np.nan, dtype=np.float64)
    v = arr[row[ok], col[ok]].astype(np.float64)
    v[v == nodata] = np.nan
    out[ok] = v * scale
    return out


def edge_endpoints(g):
    n = np.diff(g.csr_len.indptr)
    u = np.repeat(np.arange(g.csr_len.shape[0]), n)
    v = g.csr_len.indices
    return u, v


def air_on_edges(g):
    u, v = edge_endpoints(g)
    mid_lng = (g.lng[u] + g.lng[v]) * 0.5
    mid_lat = (g.lat[u] + g.lat[v]) * 0.5
    air = {}
    for key, fname, var in (
        ("pm25", "CHAP_PM2.5_Y1K_2024_V4.nc", "PM2.5"),
        ("no2", "CHAP_NO2_Y1K_2024_V2.nc", "NO2"),
    ):
        arr, tr, scale, nodata = load_grid(fname, var)
        air[key] = sample_grid(arr, tr, scale, nodata, mid_lng, mid_lat)
        fin = air[key][np.isfinite(air[key])]
        print(f"  {key}: 边覆盖 {fin.size / air[key].size:.1%}  中位 {np.median(fin):.1f}")
    return air


# ---------------------------------------------------------------- 路径工具
def _path(pred: np.ndarray, start: int, end: int) -> list[int]:
    if start == end:
        return [start]
    out, cur = [end], end
    while cur != start:
        cur = int(pred[cur])
        if cur < 0:
            return []
        out.append(cur)
    out.reverse()
    return out


def edge_pos(g, a: int, b: int) -> int:
    lo, hi = g.csr_len.indptr[a], g.csr_len.indptr[a + 1]
    pos = lo + int(np.searchsorted(g.csr_len.indices[lo:hi], b))
    if pos < hi and g.csr_len.indices[pos] == b:
        return pos
    return -1


def metrics(g, nodes, air, prefs):
    """沿节点的加权指标 + 空气暴露剂量。"""
    tot = 0.0
    acc = {k: 0.0 for k in running.ATTRS}
    sub = {k: 0.0 for k in running.PREF_KEYS.values()}
    expo = {"pm25": 0.0, "no2": 0.0, "pm25_m": 0.0, "no2_m": 0.0}
    for a, b in zip(nodes[:-1], nodes[1:]):
        p = edge_pos(g, a, b)
        if p < 0:
            continue
        L = float(g.csr_len.data[p])
        tot += L
        for k in running.ATTRS:
            acc[k] += g.edge_attr[k][p] * L
        for k in running.PREF_KEYS.values():
            sub[k] += g.subs[k][p] * L
        for key in ("pm25", "no2"):
            c = air[key][p]
            if np.isfinite(c):
                expo[key] += c * L
                expo[key + "_m"] += L
    for k in acc:
        acc[k] /= max(tot, 1e-6)
    for k in sub:
        sub[k] /= max(tot, 1e-6)
    return {
        "length_m": round(tot, 1),
        "minutes": round(tot / RUN_SPEED_MPS / 60, 1),
        "score": round(running.pref_score_of(sub, prefs), 1),
        "tree_share": round(acc["tree_share"], 3),
        "slope_mean_pct": round(acc["slope_mean_pct"], 2),
        "facility_m": round(acc["d_fac_m"], 0),
        "sub": {k: round(float(v), 1) for k, v in sub.items()},
        "pm25": round(expo["pm25"] / max(expo["pm25_m"], 1e-6), 1),
        "no2": round(expo["no2"] / max(expo["no2_m"], 1e-6), 1),
    }


def one_way(g, cost, air, lng, lat, target_m, prefs, n_dir=8):
    """单行线 A→B：在距离环带上挑终点，按偏好代价求路，不惩罚已走边。"""
    origin, snap = g.nearest(lng, lat)
    dist_len = dijkstra(g.csr_len, directed=True, indices=origin)
    band = np.flatnonzero(np.isfinite(dist_len) & (np.abs(dist_len - target_m) <= 0.12 * target_m))
    if band.size == 0:
        return []
    ang = np.arctan2(g.y[band] - g.y[origin], g.x[band] - g.x[origin])
    order = np.argsort(ang)
    picked = [band[order[int(i * (len(order) - 1) / (n_dir - 1))]] for i in range(n_dir)]
    picked = list(dict.fromkeys(int(v) for v in picked))

    _, pred = dijkstra(cost, directed=True, indices=origin, return_predecessors=True)
    out = []
    for dest in picked:
        nodes = _path(pred, origin, dest)
        if len(nodes) < 2:
            continue
        m = metrics(g, nodes, air, prefs)
        if not (0.85 * target_m <= m["length_m"] <= 1.15 * target_m):
            continue
        if any(len(set(nodes) & set(o["nodes"])) > 0.5 * len(set(nodes)) for o in out):
            continue
        m["nodes"] = nodes
        m["origin_snap_m"] = round(snap, 1)
        out.append(m)
    out.sort(key=lambda r: -r["score"])
    return out


def loops_with_air(g, air, lng, lat, target_m, prefs, **kw):
    out = []
    for lp in running.generate_loops(g, lng, lat, target_m, prefs, **kw):
        m = metrics(g, lp["nodes"], air, prefs)
        m["nodes"] = lp["nodes"]
        m["origin_snap_m"] = lp["origin_snap_m"]
        out.append(m)
    return out


def air_aware_route(g, base_cost, air, lng0, lat0, lng1, lat1, prefs,
                    key="no2", lo=15.0, hi=32.0, alpha=1.2):
    """同一对起终点：基准代价路 vs 加了空气惩罚的路。"""
    o, _ = g.nearest(lng0, lat0)
    d, _ = g.nearest(lng1, lat1)

    c = air[key].astype(np.float64).copy()
    c[~np.isfinite(c)] = np.nanmedian(c)
    w = np.clip((c - lo) / (hi - lo), 0.0, 1.0)
    data = (base_cost.data * (1.0 + alpha * w)).astype(np.float32)
    cost_air = csr_matrix((data, base_cost.indices, base_cost.indptr), shape=base_cost.shape)

    out = {}
    for tag, cm in (("baseline", base_cost), ("air_aware", cost_air)):
        _, pred = dijkstra(cm, directed=True, indices=o, return_predecessors=True)
        nodes = _path(pred, o, d)
        if len(nodes) < 2:
            continue
        m = metrics(g, nodes, air, prefs)
        m["nodes"] = nodes
        out[tag] = m
    return out


if __name__ == "__main__":
    t0 = time.time()
    g = running.load_or_build()
    print(f"图 {g.n:,} 节点 / {g.csr_len.nnz:,} 边（{time.time() - t0:.1f}s）")
    print("空气网格采样到边：")
    air_of_edges = air_on_edges(g)

    prefs = {"green": 1.0, "safe": 1.0, "flat": 0.6}
    pref = running._pref_score(g, prefs)
    cost = running._cost_matrix(g, pref)

    ORIGIN = (114.3547, 30.5342)  # 武汉大学 · 八一路珞珈山
    res = {}

    for name, tgt in (("loop5", 5000), ("loop10", 10000), ("mar42", 42195)):
        tt = time.time()
        lp = loops_with_air(g, air_of_edges, *ORIGIN, tgt, prefs, max_candidates=8)
        res[name] = lp
        print(f"\n[{name}] target {tgt} -> {len(lp)} 条  {time.time() - tt:.1f}s")
        for r in lp[:4]:
            print(f"   {r['length_m']:8.0f} m  {r['minutes']:5.1f} min  分 {r['score']:5.1f}  "
                  f"PM2.5 {r['pm25']:5.1f}  NO2 {r['no2']:5.1f}  树 {r['tree_share']:.2f}")

    ow = one_way(g, cost, air_of_edges, *ORIGIN, 10000, prefs)
    res["oneway10"] = ow
    print(f"\n[oneway10] -> {len(ow)} 条")
    for r in ow[:4]:
        print(f"   {r['length_m']:8.0f} m  {r['minutes']:5.1f} min  分 {r['score']:5.1f}  "
              f"PM2.5 {r['pm25']:5.1f}  NO2 {r['no2']:5.1f}")

    # 同一对起终点：基准路 vs 空气感知路
    aw = air_aware_route(g, cost, air_of_edges, 114.3547, 30.5342, 114.2950, 30.5850, prefs)
    res["air_aware"] = [aw[k] for k in ("baseline", "air_aware") if k in aw]
    print("\n[air_aware] 武大 → 汉口江滩")
    for k, r in aw.items():
        print(f"   {k:9s} {r['length_m']:8.0f} m  {r['minutes']:5.1f} min  分 {r['score']:5.1f}  "
              f"PM2.5 {r['pm25']:5.1f}  NO2 {r['no2']:5.1f}")
    if "baseline" in aw and "air_aware" in aw:
        b, a = aw["baseline"], aw["air_aware"]
        print(f"   → NO2 {b['no2']:.1f} → {a['no2']:.1f}（{(a['no2']/b['no2']-1)*100:+.1f}%）"
              f"  长度 {b['length_m']:.0f} → {a['length_m']:.0f} m（{a['length_m']/b['length_m']-1:+.1%}）")

    Path(OUT / "routes_demo.json").write_text(
        json.dumps({k: [{kk: vv for kk, vv in r.items() if kk != "nodes"} for r in v]
                    for k, v in res.items()}, ensure_ascii=False, indent=1, default=float),
        encoding="utf-8",
    )
    np.save(OUT / "_nodes_loop5.npy", np.array(res["loop5"][0]["nodes"], dtype=np.int64))
    print("\n总耗时 %.1fs" % (time.time() - t0))
