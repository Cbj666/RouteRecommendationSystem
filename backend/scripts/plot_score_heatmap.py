# -*- coding: utf-8 -*-
"""Weight-iteration heatmap: rescore the road network from stored sub-scores and
draw one comparable heatmap per weight version.

Why this exists
    The six sub-scores (`s_safety ... s_air`) are the expensive part of
    `build_running_dataset.py`; the composite `score` is only their weighted sum.
    So weights can be iterated in seconds instead of re-running the pipeline,
    as long as the weights are explicit and sum to 1.0.

What it draws (one PNG per version)
    左   核心城区路段评分热力图（色标固定，跨版本可直接对比）
    右   分数直方图（叠加 v1 基线）+ 分档占比 + 区分度指标表
    左下 各道路等级的均分：验证"人行道 > 主干道"的口径没被权重改坏

Outputs (data/output/running/v1/weights/)
    <tag>/heatmap.png      the picture
    <tag>/stats.json       full metrics for that version
    iterations.csv         one ledger row per version (append / replace by tag)
    compare_<tags>.png     only when several versions are rendered together

Usage
    # one version, explicit weights (auto-normalised; the raw sum is printed)
    python backend/scripts/plot_score_heatmap.py --tag v2 \\
        --w safety=0.36,green=0.22,slope=0.10,cross=0.16,fac=0.08,air=0.08

    # named presets, rendered together + a comparison sheet
    python backend/scripts/plot_score_heatmap.py --preset v1,v2a,v2b

    # a JSON file of {版本名: {维度: 权重}}
    python backend/scripts/plot_score_heatmap.py --config my_weights.json

    # statistics only (~1 s instead of ~3 s per version)
    python backend/scripts/plot_score_heatmap.py --tag quick --w ... --no-map
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pyogrio  # noqa: E402
import shapely  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
MONO = ["Consolas", "Microsoft YaHei"]      # 等宽数字 + 中文回退

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "data" / "processed" / "running" / "v1"
GPKG = RUN / "segments.gpkg"
LANDUSE = ROOT / "data" / "raw" / "hubei" / "hubei-261013-free-OpenMap" / "hubei.gpkg"
OUT = ROOT / "data" / "output" / "running" / "v1" / "weights"
LEDGER = OUT / "iterations.csv"

DIMS = ["safety", "green", "slope", "cross", "fac", "air"]
DIM_CN = {"safety": "安全", "green": "绿化", "slope": "坡度",
          "cross": "过街", "fac": "设施", "air": "空气"}
SUBS = [f"s_{k}" for k in DIMS]

# v1 口径：六维合计 0.95（满分 95）。既是对照基线，也是"旧版"。
V1 = {"safety": 0.25, "green": 0.25, "slope": 0.15,
      "cross": 0.10, "fac": 0.05, "air": 0.15}

WEIGHT_SETS = OrderedDict([
    ("v1", V1),
    ("v2a", {"safety": 0.30, "green": 0.25, "slope": 0.14,
             "cross": 0.13, "fac": 0.07, "air": 0.11}),
    ("v2b", {"safety": 0.36, "green": 0.22, "slope": 0.10,
             "cross": 0.16, "fac": 0.08, "air": 0.08}),
    ("v2c", {"safety": 0.42, "green": 0.21, "slope": 0.08,
             "cross": 0.14, "fac": 0.07, "air": 0.08}),
])

GRADE_BINS = [0, 40, 55, 70, 85, 100]
GRADE_LABELS = ["差", "一般", "较好", "好", "很好"]
GRADE_COLORS = ["#b03a2e", "#e08214", "#d4c94a", "#5ba85b", "#1e6b34"]

CORE = (114.190, 30.460, 114.460, 30.620)      # 核心城区（50 起点扫描范围）
SHOWCASE = (114.285, 30.495, 114.455, 30.585)  # 东湖 / 珞珈山 / 水果湖
GREEN_FCLASS = {"park", "forest", "grass", "meadow", "scrub", "recreation_ground"}
FCLASS_CN = {"footway": "人行道", "path": "小径", "cycleway": "自行车道",
             "residential": "居住区路", "tertiary": "次干道",
             "secondary": "主干道", "primary": "主要道路", "trunk": "快速路"}

LW = {"primary": 2.1, "secondary": 1.8, "tertiary": 1.5, "trunk": 2.3,
      "residential": 1.15, "unclassified": 0.95, "service": 0.85,
      "footway": 1.0, "path": 0.95, "cycleway": 1.3, "pedestrian": 1.1,
      "steps": 0.9, "living_street": 1.0, "track": 0.9}


# ------------------------------------------------------------------ weights
def parse_weights(text: str) -> dict[str, float]:
    """'safety=0.3,green=0.2' -> dict; unknown keys are a hard error."""
    out = {}
    for chunk in text.replace(" ", "").split(","):
        if not chunk:
            continue
        if "=" not in chunk:
            raise SystemExit(f"权重写法应是 key=value：{chunk!r}")
        k, v = chunk.split("=", 1)
        k = k.strip()
        k = k[2:] if k.startswith("s_") else k
        if k not in DIMS:
            raise SystemExit(f"未知维度 {k!r}；可用 {DIMS}")
        out[k] = float(v)
    missing = [k for k in DIMS if k not in out]
    if missing:
        raise SystemExit(f"缺少维度 {missing}；六维必须写全")
    return out


def normalise(w: dict[str, float]) -> tuple[dict[str, float], float]:
    total = float(sum(w.values()))
    if not np.isfinite(total) or total <= 0:
        raise SystemExit(f"权重合计非法：{total}")
    return {k: w[k] / total for k in DIMS}, total


def fmt_w(w: dict[str, float]) -> str:
    return "  ".join(f"{DIM_CN[k]} {w[k]:.2f}" for k in DIMS)


# -------------------------------------------------------------------- data
class Data:
    """Everything the figures need, loaded once and reused for every version."""

    def __init__(self, no_map: bool = False):
        print("[heat] 读取路段表 ...", flush=True)
        cols = ["fclass", "in_boundary", "length_m", "score"] + SUBS
        gdf = gpd.read_file(GPKG, layer="segments", columns=cols)
        self.sub = gdf[SUBS].to_numpy(dtype=float)
        self.fclass = gdf["fclass"].fillna("unclassified").to_numpy()
        self.inb = gdf["in_boundary"].to_numpy(dtype=bool)
        self.length = gdf["length_m"].to_numpy(dtype=float)
        self.score_v1 = np.round(gdf["score"].to_numpy(dtype=float), 1)
        self.n = len(gdf)
        self.baseline = self.composite({k: V1[k] / 0.95 for k in DIMS})
        self.core_box = self._utm_box(CORE)
        print(f"[heat] {self.n:,} 段，边界内 {int(self.inb.sum()):,} 段", flush=True)
        self.basemap = None
        if no_map:
            return

        print("[heat] 读取几何 ...", flush=True)
        geoms = gpd.read_file(GPKG, layer="segments", columns=["geometry"])["geometry"]
        geoms = geoms.to_crs(32650)          # 绘制/统计一律在米制坐标下
        self._prep_pieces(geoms)
        self.basemap = self._basemap()

    # --- geometry pieces: one 2-point array per vertex pair ---------------
    def _prep_pieces(self, geoms) -> None:
        coords, idx = shapely.get_coordinates(geoms.to_numpy(), return_index=True)
        keep = idx[1:] == idx[:-1]
        self.pieces = np.stack([coords[:-1][keep], coords[1:][keep]], axis=1)
        self.piece_idx = idx[:-1][keep]
        (x0, y0, x1, y1) = self.core_box
        px, py = self.pieces[:, :, 0], self.pieces[:, :, 1]
        self.core_mask = (
            (px.min(1) < x1) & (px.max(1) > x0) & (py.min(1) < y1) & (py.max(1) > y0)
        )
        print(f"[heat] {len(self.pieces):,} 个绘制小段，核心区 "
              f"{int(self.core_mask.sum()):,}", flush=True)

    def _utm_box(self, bbox):
        box = gpd.GeoSeries([shapely.box(*bbox)], crs=4326).to_crs(32650).iloc[0]
        return box.bounds

    def _basemap(self):
        if not LANDUSE.exists():
            print("[heat] ! 缺少 hubei.gpkg，跳过绿地/水体底图", flush=True)
            return None
        try:
            land = pyogrio.read_dataframe(LANDUSE, layer="gis_osm_landuse_a_free",
                                          bbox=SHOWCASE)
            green = land[land["fclass"].isin(GREEN_FCLASS)].to_crs(32650)
            water = pyogrio.read_dataframe(LANDUSE, layer="gis_osm_water_a_free",
                                           bbox=SHOWCASE).to_crs(32650)
        except Exception as exc:                           # pragma: no cover
            print(f"[heat] ! 底图读取失败（{exc}），继续", flush=True)
            return None
        return {"green": green, "water": water}

    # --- scoring ----------------------------------------------------------
    def composite(self, w: dict[str, float], raw: bool = False) -> np.ndarray:
        """Weighted sum of the six sub-scores, rounded like the pipeline."""
        s = np.zeros(self.n)
        for i, k in enumerate(DIMS):
            s += w[k] * self.sub[:, i]
        return s if raw else np.round(s, 1)

    def by_fclass(self, score: np.ndarray) -> dict[str, float]:
        df = pd.DataFrame({"fclass": self.fclass, "s": score})[self.inb]
        m = df.groupby("fclass")["s"].mean()
        return {k: round(float(m.get(k, np.nan)), 1) for k in FCLASS_CN}


# ----------------------------------------------------------------- metrics
def compute_stats(score: np.ndarray, baseline: np.ndarray) -> dict:
    p = np.percentile(score, [1, 2, 5, 10, 25, 50, 75, 90, 95, 98, 99])
    counts = np.histogram(score, GRADE_BINS)[0]
    share = counts / len(score)
    ent = -np.sum([x * np.log(x) for x in share if x > 0]) / np.log(len(GRADE_LABELS))
    tops = len(score) // 10
    t_new = set(np.argsort(-score, kind="stable")[:tops])
    t_old = set(np.argsort(-baseline, kind="stable")[:tops])
    return {
        "segments": int(len(score)),
        "score": {
            "mean": float(score.mean()), "std": float(score.std()),
            "min": float(score.min()), "max": float(score.max()),
            "p1": float(p[0]), "p2": float(p[1]), "p5": float(p[2]),
            "p10": float(p[3]), "p25": float(p[4]), "p50": float(p[5]),
            "p75": float(p[6]), "p90": float(p[7]), "p95": float(p[8]),
            "p98": float(p[9]), "p99": float(p[10]),
        },
        "discrimination": {
            "cv": float(score.std() / score.mean()),
            "iqr": float(p[6] - p[4]),
            "p10_p90": float(p[7] - p[3]),
            "p5_p95": float(p[8] - p[2]),
            "grade_entropy": float(ent),
            "share_ge70": float(share[3:].sum() * 100),
            "share_ge85": float(share[4] * 100),
            "share_lt40": float(share[0] * 100),
        },
        "grades": {lab: int(c) for lab, c in zip(GRADE_LABELS, counts)},
        "grade_share": {lab: round(float(c / len(score) * 100), 2)
                        for lab, c in zip(GRADE_LABELS, counts)},
        "vs_v1n": {
            "spearman": float(spearmanr(baseline, score).statistic),
            "top10_overlap": float(len(t_new & t_old) / max(tops, 1)),
            "d_mean": float(score.mean() - baseline.mean()),
            "d_std": float(score.std() - baseline.std()),
        },
    }


# ------------------------------------------------------------------- plots
def _band_colors(ax) -> None:
    for lo, hi, c in zip(GRADE_BINS[:-1], GRADE_BINS[1:], GRADE_COLORS):
        ax.axvspan(lo, hi, color=c, alpha=0.10, lw=0)


def _disp_len(text: str) -> int:
    """Display width: CJK / full-width glyphs count as two columns."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def _pad(text: str, width: int, align: str = "left") -> str:
    gap = max(width - _disp_len(text), 0)
    return " " * gap + text if align == "right" else text + " " * gap


def draw_map(ax, d: Data, score: np.ndarray, norm: Normalize) -> None:
    cmap = plt.get_cmap("RdYlGn")
    m = d.core_mask
    idx = d.piece_idx[m]
    if d.basemap:
        d.basemap["water"].plot(ax=ax, color="#cfe3f3", edgecolor="#a9c8e0",
                                linewidth=0.3, zorder=1)
        d.basemap["green"].plot(ax=ax, color="#dcecd6", edgecolor="#b7d4ad",
                                linewidth=0.2, zorder=1)
    lc = LineCollection(d.pieces[m], cmap=cmap, norm=norm)
    lc.set_array(score[idx])
    lc.set_linewidths(np.array([LW.get(c, 0.9) for c in d.fclass[idx]]))
    lc.set_alpha(0.9)
    lc.set_zorder(3)
    ax.add_collection(lc)
    x0, y0, x1, y1 = d.core_box
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_title("核心城区路段评分热力图（东湖—珞珈山—水果湖，24.5×16.6 km）\n"
                 f"占全网 {int(d.core_mask.sum() / len(d.pieces) * 100)}% 路段；颜色越绿越适合跑步",
                 fontsize=10.5, loc="left", pad=5, linespacing=1.55)
    handles = [
        Line2D([0], [0], color=cmap(0.88), lw=2.6, label="高分路段"),
        Line2D([0], [0], color=cmap(0.10), lw=2.6, label="低分路段"),
        Patch(color="#dcecd6", label="绿地"),
        Patch(color="#cfe3f3", label="水体"),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=7.5, framealpha=0.85, ncol=2)


def draw_hist(ax, d: Data, score: np.ndarray, tag: str) -> None:
    _band_colors(ax)
    bins = np.arange(0, 101, 2)
    ax.hist(d.baseline, bins=bins, histtype="step", color="#b03a2e", lw=1.4,
            label="v1（归一化到 1.0）", zorder=4)
    ax.hist(score, bins=bins, color="#2f6f8f", alpha=0.70, label=tag, zorder=3)
    for b in GRADE_BINS[1:-1]:
        ax.axvline(b, color="#555555", lw=0.8, ls=":", zorder=2)
    top = ax.get_ylim()[1]
    for lab, lo, hi in zip(GRADE_LABELS, GRADE_BINS[:-1], GRADE_BINS[1:]):
        ax.text((lo + hi) / 2, top * 0.96, lab, ha="center", va="top",
                fontsize=8.5, color="#444444")
    ax.set_xlim(0, 100)
    ax.set_xlabel("综合适宜性评分", fontsize=9)
    ax.set_ylabel("路段数", fontsize=9)
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax.set_title("分数分布（越左右铺开 = 区分度越高）", fontsize=11, loc="left", pad=6)


def draw_grades(ax, st: dict, base_st: dict, tag: str) -> None:
    x = np.arange(len(GRADE_LABELS))
    w = 0.38
    base = [base_st["grade_share"][g] for g in GRADE_LABELS]
    new = [st["grade_share"][g] for g in GRADE_LABELS]
    ax.bar(x - w / 2, base, w, color="#dddddd", edgecolor="#888888",
           linewidth=0.7, label="v1（归一化）")
    ax.bar(x + w / 2, new, w, color=GRADE_COLORS, edgecolor="#555555",
           linewidth=0.5, label=tag)
    for xi, v in zip(x, new):
        ax.text(xi + w / 2, v + 0.8, f"{v:.0f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(GRADE_LABELS, fontsize=9)
    ax.set_ylabel("路段占比 %", fontsize=9)
    ax.set_title("分档占比", fontsize=11, loc="left", pad=6)
    ax.legend(fontsize=8, framealpha=0.9)
    ax.set_ylim(0, max(max(new), max(base)) * 1.34)
    ax.grid(axis="y", color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)


def draw_byclass(ax, st: dict, base_st: dict, tag: str) -> None:
    keys = list(FCLASS_CN)
    x = np.arange(len(keys))
    w = 0.38
    b = [base_st["by_fclass"][k] for k in keys]
    n = [st["by_fclass"][k] for k in keys]
    ax.bar(x - w / 2, b, w, color="#999999", alpha=0.45, label="v1（归一化）")
    ax.bar(x + w / 2, n, w, color="#2f6f8f", label=tag)
    ax.set_xticks(x)
    ax.set_xticklabels([FCLASS_CN[k] for k in keys], fontsize=7.8)
    ax.set_ylabel("均分", fontsize=8.5)
    ax.tick_params(axis="y", labelsize=8)
    ax.set_ylim(0, 100)
    ax.grid(axis="y", color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)
    ax.legend(fontsize=7.5, ncol=2, loc="upper right", framealpha=0.9)
    ax.set_title("各道路等级均分（口径自检：人行道/小径应高于主干道）",
                 fontsize=10.5, loc="left", pad=4)


def draw_metrics(ax, st: dict, base_st: dict) -> None:
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    dsc, bd = st["discrimination"], base_st["discrimination"]
    rows = [
        ("均值 mean", st["score"]["mean"], base_st["score"]["mean"],
         st["vs_v1n"]["d_mean"], 2),
        ("标准差 std", st["score"]["std"], base_st["score"]["std"],
         st["vs_v1n"]["d_std"], 2),
        ("变异系数 CV", dsc["cv"], bd["cv"], dsc["cv"] - bd["cv"], 3),
        ("四分位距 IQR", dsc["iqr"], bd["iqr"], dsc["iqr"] - bd["iqr"], 1),
        ("p10–p90", dsc["p10_p90"], bd["p10_p90"], dsc["p10_p90"] - bd["p10_p90"], 1),
        ("占比 ≥70 分 %", dsc["share_ge70"], bd["share_ge70"],
         dsc["share_ge70"] - bd["share_ge70"], 1),
        ("占比 <40 分 %", dsc["share_lt40"], bd["share_lt40"],
         dsc["share_lt40"] - bd["share_lt40"], 1),
        ("分档熵 H", dsc["grade_entropy"], bd["grade_entropy"],
         dsc["grade_entropy"] - bd["grade_entropy"], 3),
        ("秩相关 ρ(v1)", st["vs_v1n"]["spearman"], 1.0,
         st["vs_v1n"]["spearman"] - 1.0, 3),
        ("前10%重合", st["vs_v1n"]["top10_overlap"], 1.0,
         st["vs_v1n"]["top10_overlap"] - 1.0, 3),
    ]
    lines = [f"  {_pad('指标', 15)}{_pad('本版', 8, 'right')}"
             f"{_pad('v1归一', 9, 'right')}{_pad('变化', 9, 'right')}",
             "  " + "-" * 42]
    for name, val, ref, delta, nd in rows:
        fmt = f"{{:.{nd}f}}"
        lines.append("  " + _pad(name, 15) + _pad(fmt.format(val), 8, "right")
                     + _pad(fmt.format(ref), 9, "right")
                     + _pad(f"{delta:+.{nd}f}", 9, "right"))
    ax.text(0.0, 0.99, "\n".join(lines), family=MONO, fontsize=8.8, va="top",
            ha="left", linespacing=1.50)
    ax.text(0.0, 0.015,
            "ρ / 前 10% 重合：新权重有没有改掉原有结论（越接近 1 越稳）",
            fontsize=7.6, va="bottom", ha="left", color="#666666")
    ax.set_title("区分度指标", fontsize=11, loc="left", pad=6)


def render_one(d: Data, tag: str, w: dict[str, float], wsum: float,
               st: dict, base_st: dict, norm: Normalize, dpi: int) -> Path:
    fig = plt.figure(figsize=(15.6, 10.4))
    outer = fig.add_gridspec(1, 2, width_ratios=[1.72, 1.0], wspace=0.05,
                             left=0.02, right=0.985, top=0.90, bottom=0.085)
    left = outer[0].subgridspec(2, 1, height_ratios=[1.0, 0.38], hspace=0.26)
    right = outer[1].subgridspec(3, 1, height_ratios=[1.0, 0.80, 1.05], hspace=0.36)

    ax_map = fig.add_subplot(left[0])
    ax_cls = fig.add_subplot(left[1])
    ax_hist = fig.add_subplot(right[0])
    ax_grade = fig.add_subplot(right[1])
    ax_met = fig.add_subplot(right[2])

    draw_map(ax_map, d, st["_score"], norm)
    draw_byclass(ax_cls, st, base_st, tag)
    draw_hist(ax_hist, d, st["_score"], tag)
    draw_grades(ax_grade, st, base_st, tag)
    draw_metrics(ax_met, st, base_st)

    cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap="RdYlGn"),
                      ax=ax_map, location="bottom", fraction=0.05, pad=0.02,
                      aspect=46)
    cb.set_label(f"综合评分（色标固定 {norm.vmin:.0f}–{norm.vmax:.0f}，跨版本可直接对比）",
                 fontsize=8.5)
    cb.ax.tick_params(labelsize=8)

    dstd = st["vs_v1n"]["d_std"]
    fig.suptitle(
        f"评分权重版本 {tag}   ·   std {base_st['score']['std']:.2f} → "
        f"{st['score']['std']:.2f}（{dstd:+.2f}）   ·   "
        f"≥70 分 {st['discrimination']['share_ge70']:.1f}%   ·   "
        f"与 v1 秩相关 ρ={st['vs_v1n']['spearman']:.3f}",
        fontsize=14, y=0.975)
    fig.text(0.02, 0.020, "权重：" + fmt_w(w) + f"   |   合计 {wsum:.4f}"
             + ("（已归一化到 1.0）" if abs(wsum - 1) > 1e-9 else " = 1.0"),
             fontsize=8.4, color="#555555")

    out_dir = OUT / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / "heatmap.png"
    fig.savefig(png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return png


def render_compare(results: "OrderedDict[str, dict]", d: Data) -> Path:
    """One sheet to pick from: overlaid distributions + weight / metric tables."""
    tags = list(results)
    n = len(tags)
    fig = plt.figure(figsize=(15.0, 4.6 + 0.30 * n))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.55, 0.125 * n + 0.05], hspace=0.42,
                          top=0.94, bottom=0.02, left=0.05, right=0.99)

    ax0 = fig.add_subplot(gs[0])
    bins = np.arange(0, 101, 2)
    ax0.hist(d.baseline, bins=bins, histtype="step", color="#777777", lw=1.6,
             density=True, label="v1（归一化）")
    cols = plt.cm.viridis(np.linspace(0.10, 0.72, n))
    for c, tag in zip(cols, tags):
        st = results[tag]
        ax0.hist(st["_score"], bins=bins, histtype="step", color=c, lw=1.9,
                 density=True,
                 label=f"{tag}   std={st['score']['std']:.2f}   "
                       f"p10–p90={st['discrimination']['p10_p90']:.1f}")
    ax0.set_xlim(0, 100)
    ymax = ax0.get_ylim()[1]
    for b in GRADE_BINS[1:-1]:
        ax0.axvline(b, color="#aaaaaa", lw=0.9, ls=":")
    for lab, lo, hi in zip(GRADE_LABELS, GRADE_BINS[:-1], GRADE_BINS[1:]):
        ax0.text((lo + hi) / 2, ymax * 0.99, lab, ha="center", va="top",
                 fontsize=9, color="#888888")
    ax0.set_ylim(0, ymax * 1.06)
    ax0.set_xlabel("综合评分", fontsize=9)
    ax0.set_ylabel("密度", fontsize=9)
    ax0.legend(fontsize=8.5, ncol=2, loc="upper left", framealpha=0.92)
    ax0.set_title("候选权重版本的分数分布对比（曲线越宽 = 区分度越高）",
                  fontsize=12, loc="left")
    ax0.grid(color="#eeeeee", lw=0.6)
    ax0.set_axisbelow(True)
    ax0.tick_params(labelsize=8.5)

    sub = gs[1].subgridspec(1, 2, width_ratios=[1.0, 1.18], wspace=0.06)
    ax_w = fig.add_subplot(sub[0])
    ax_m = fig.add_subplot(sub[1])

    # --- weights table
    head = "  " + _pad("版本", 7) + "".join(_pad(DIM_CN[k], 6, "right") for k in DIMS) \
           + _pad("合计", 8, "right")
    wl = [head, "  " + "-" * (7 + 6 * len(DIMS) + 8)]
    for tag in tags:
        st = results[tag]
        wl.append("  " + _pad(tag, 7)
                  + "".join(_pad(f"{st['_w'][k]:.2f}", 6, "right") for k in DIMS)
                  + _pad(f"{st['_wsum']:.3f}", 8, "right"))
    ax_w.set_axis_off()
    ax_w.text(0.0, 1.0, "\n".join(wl), family=MONO, fontsize=9.4, va="top",
              ha="left", linespacing=1.62)
    ax_w.set_title("六维权重（已归一化到 1.0）", fontsize=10.5, loc="left", pad=4)

    # --- metrics table
    h2 = ("  " + _pad("版本", 7) + _pad("mean", 6, "right") + _pad("std", 6, "right")
          + _pad("IQR", 6, "right") + _pad("p10–90", 7, "right")
          + _pad("≥70%", 6, "right") + _pad("<40%", 6, "right")
          + _pad("H", 6, "right") + _pad("ρ", 6, "right")
          + _pad("前10%", 6, "right") + "   分档 差/一般/较好/好")
    ml = [h2, "  " + "-" * 92]
    for tag in tags:
        st = results[tag]
        ml.append("  " + _pad(tag, 7)
                  + _pad(f"{st['score']['mean']:.1f}", 6, "right")
                  + _pad(f"{st['score']['std']:.2f}", 6, "right")
                  + _pad(f"{st['discrimination']['iqr']:.1f}", 6, "right")
                  + _pad(f"{st['discrimination']['p10_p90']:.1f}", 7, "right")
                  + _pad(f"{st['discrimination']['share_ge70']:.1f}", 6, "right")
                  + _pad(f"{st['discrimination']['share_lt40']:.1f}", 6, "right")
                  + _pad(f"{st['discrimination']['grade_entropy']:.3f}", 6, "right")
                  + _pad(f"{st['vs_v1n']['spearman']:.3f}", 6, "right")
                  + _pad(f"{st['vs_v1n']['top10_overlap']:.2f}", 6, "right")
                  + "   " + "/".join(f"{st['grade_share'][g]:.0f}" for g in
                                     GRADE_LABELS[:-1]))
    ax_m.set_axis_off()
    ax_m.text(0.0, 1.0, "\n".join(ml), family=MONO, fontsize=9.4, va="top",
              ha="left", linespacing=1.62)
    ax_m.set_title("区分度指标（基线 = v1 归一化 mean 54.2 / std 9.88 / p10–p90 25.8）",
                   fontsize=10.5, loc="left", pad=4)

    png = OUT / f"compare_{'-'.join(tags)}.png"
    fig.savefig(png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return png


def append_ledger(row: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([row])
    if LEDGER.exists():
        old = pd.read_csv(LEDGER, encoding="utf-8-sig")
        old = old[old["tag"] != row["tag"]]
        df = pd.concat([old, df], ignore_index=True)
    df.to_csv(LEDGER, index=False, encoding="utf-8-sig")


# -------------------------------------------------------------------- main
def collect_sets(args) -> "OrderedDict[str, dict]":
    sets: "OrderedDict[str, dict]" = OrderedDict()
    pool = dict(WEIGHT_SETS)
    if args.config:
        cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
        for name, w in cfg.items():
            missing = [k for k in DIMS if k not in w]
            if missing:
                raise SystemExit(f"{name}: 缺少维度 {missing}")
            pool[name] = {k: float(w[k]) for k in DIMS}
    if args.preset:
        for name in [s.strip() for s in args.preset.split(",") if s.strip()]:
            if name not in pool:
                raise SystemExit(f"未知版本 {name!r}；可用 {list(pool)}")
            sets[name] = pool[name]
    if args.w:
        sets[args.tag or "adhoc"] = parse_weights(args.w)
    if not sets:
        raise SystemExit("给一个权重：--w / --preset / --config（--help 看例子）")
    return sets


def main() -> int:
    ap = argparse.ArgumentParser(description="评分权重迭代热力图")
    ap.add_argument("--w", help="显式权重，如 safety=0.36,green=0.22,...")
    ap.add_argument("--preset", help="内置/配置里的版本名，逗号分隔，如 v1,v2a")
    ap.add_argument("--config", help="JSON 文件：{版本名: {维度: 权重}}")
    ap.add_argument("--tag", help="--w 单版本时的输出名")
    ap.add_argument("--clim", default="30,70", help="固定色标上下限，默认 30,70")
    ap.add_argument("--dpi", type=int, default=170)
    ap.add_argument("--no-map", action="store_true", help="只算指标不画图（快）")
    args = ap.parse_args()

    sets = collect_sets(args)
    clim = tuple(float(v) for v in args.clim.split(","))
    if len(clim) != 2 or clim[0] >= clim[1]:
        raise SystemExit("--clim 形如 30,70")
    norm = Normalize(*clim)

    t0 = time.time()
    d = Data(no_map=args.no_map)
    base_st = compute_stats(d.baseline, d.baseline)
    base_st["by_fclass"] = d.by_fclass(d.baseline)

    results: "OrderedDict[str, dict]" = OrderedDict()
    for tag, w in sets.items():
        w_norm, wsum = normalise(w)
        score = d.composite(w_norm)
        st = compute_stats(score, d.baseline)
        st.update({"_score": score, "_w": w_norm, "_wsum": wsum, "tag": tag,
                   "weights": w_norm, "weight_sum_raw": wsum,
                   "by_fclass": d.by_fclass(score),
                   "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        results[tag] = st

        flag = "" if abs(wsum - 1) < 1e-9 else f"  ! 合计 {wsum:.4f}，已归一化"
        print(f"\n=== {tag}: {fmt_w(w_norm)}{flag}")
        print(f"    mean {st['score']['mean']:.2f}  std {st['score']['std']:.2f} "
              f"({st['vs_v1n']['d_std']:+.2f})  IQR {st['discrimination']['iqr']:.1f} "
              f"({st['discrimination']['iqr'] - base_st['discrimination']['iqr']:+.1f})  "
              f"p10–p90 {st['discrimination']['p10_p90']:.1f}  "
              f"≥70 {st['discrimination']['share_ge70']:.1f}%  "
              f"<40 {st['discrimination']['share_lt40']:.1f}%")
        print("    分档 " + "  ".join(f"{g} {st['grade_share'][g]:.1f}%"
                                     for g in GRADE_LABELS))
        print(f"    秩相关 ρ {st['vs_v1n']['spearman']:.3f}   前10%重合 "
              f"{st['vs_v1n']['top10_overlap']:.2f}")
        print("    按等级均分 " + "  ".join(f"{k} {v:.0f}"
                                          for k, v in st["by_fclass"].items()))

        png = None
        if not args.no_map:
            png = render_one(d, tag, w_norm, wsum, st, base_st, norm, args.dpi)
            st["_png"] = str(png.relative_to(ROOT))
            print(f"    -> {png.relative_to(ROOT)}")

        (OUT / tag).mkdir(parents=True, exist_ok=True)
        payload = {k: v for k, v in st.items() if not k.startswith("_")}
        payload["png"] = st.get("_png")
        payload["color_limits"] = list(clim)
        (OUT / tag / "stats.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        append_ledger({
            "tag": tag,
            "created": payload["created"],
            **{f"w_{k}": round(w_norm[k], 4) for k in DIMS},
            "sum_raw": round(wsum, 4),
            "mean": round(st["score"]["mean"], 3),
            "std": round(st["score"]["std"], 3),
            "cv": round(st["discrimination"]["cv"], 4),
            "iqr": round(st["discrimination"]["iqr"], 3),
            "p10_p90": round(st["discrimination"]["p10_p90"], 3),
            "share_ge70": round(st["discrimination"]["share_ge70"], 2),
            "share_lt40": round(st["discrimination"]["share_lt40"], 2),
            "grade_entropy": round(st["discrimination"]["grade_entropy"], 4),
            "rho_v1": round(st["vs_v1n"]["spearman"], 4),
            "top10_overlap": round(st["vs_v1n"]["top10_overlap"], 4),
            **{f"n_{g}": st["grades"][g] for g in GRADE_LABELS},
            "png": payload["png"],
        })

    if len(results) > 1 and not args.no_map:
        cmp_png = render_compare(results, d)
        print(f"\n[heat] 对比图 -> {cmp_png.relative_to(ROOT)}")
    if len(results) > 1:
        print("\n版本       mean    std    CV     IQR   p10–90  ≥70%   <40%   ρ     前10%")
        for tag in results:
            st = results[tag]
            print(f"{tag:10s} {st['score']['mean']:6.1f} {st['score']['std']:6.2f} "
                  f"{st['discrimination']['cv']:5.3f} {st['discrimination']['iqr']:6.1f} "
                  f"{st['discrimination']['p10_p90']:7.1f} "
                  f"{st['discrimination']['share_ge70']:5.1f} "
                  f"{st['discrimination']['share_lt40']:6.1f} "
                  f"{st['vs_v1n']['spearman']:6.3f} "
                  f"{st['vs_v1n']['top10_overlap']:5.2f}")
        print(f"\n基线 v1（归一化）mean {base_st['score']['mean']:.1f} "
              f"std {base_st['score']['std']:.2f} "
              f"IQR {base_st['discrimination']['iqr']:.1f} "
              f"p10–p90 {base_st['discrimination']['p10_p90']:.1f}")
    print(f"\n[heat] ledger -> {LEDGER.relative_to(ROOT)}   {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
