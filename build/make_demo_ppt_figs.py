"""产出 PPT 用的演示图：路线三模式、空气的空间/时间/尺度规律。

输入：data/processed/running/v1/{segments.gpkg, segment_air.csv, edge_air_cache.npz}
输出：data/output/running/v1/demo/fig_*.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.collections import LineCollection

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "build"))

from app import running  # noqa: E402
import demo_routes as D  # noqa: E402

PROC = ROOT / "data" / "processed" / "running" / "v1"
OUT = ROOT / "data" / "output" / "running" / "v1" / "demo"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

INK = "#1f2a26"
GREEN = "#1a5c46"
MID = "#4f9d7d"
PALE = "#a8d5bd"
AMBER = "#c0762a"
RED = "#b03a2e"
GRAY = "#8a9a93"


def style_ax(ax, grid_axis="y"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#d8d8d8")
    ax.tick_params(colors="#555", labelsize=9.5, length=3)
    ax.grid(axis=grid_axis, color="#ececec", linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def title(ax, text, sub=None):
    ax.set_title(text, fontsize=13.5, color=INK, fontweight="bold", loc="left",
                 pad=27 if sub else 12)
    if sub:
        ax.text(0, 1.012, sub, transform=ax.transAxes, fontsize=9.5, color=GRAY, va="bottom")


# --------------------------------------------------------------- 数据
def load_all():
    g = running.load_or_build()
    z = np.load(PROC / "edge_air_cache.npz")
    air = {"pm25": z["pm25"].astype(np.float64), "no2": z["no2"].astype(np.float64)}
    return g, air


def fig_modes(g, air):
    prefs = {"green": 1.0, "safe": 1.0, "flat": 0.6}
    pref = running._pref_score(g, prefs)
    cost = running._cost_matrix(g, pref)
    ORIGIN = (114.3547, 30.5342)

    loop5 = D.loops_with_air(g, air, *ORIGIN, 5000, prefs, max_candidates=8)
    ow10 = D.one_way(g, cost, air, *ORIGIN, 10000, prefs)
    mar = D.loops_with_air(g, air, *ORIGIN, 42195, prefs, max_candidates=8)

    seg = gpd.read_file(PROC / "segments.gpkg", layer="segments", columns=["score"]).to_crs(32650)
    seg["geometry"] = seg.geometry.scale(0.001, 0.001, origin=(0, 0))
    panels = [
        ("① 环线 5 km · 闭合回到起点", loop5[0], "loop", 2),
        ("② 单行线 10 km · A → B 不回头", ow10[0], "oneway", 2),
        ("③ 马拉松 42 km · 长距离闭环", mar[0], "loop", 10),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(15.2, 5.6), dpi=190)
    scale_bars = []
    for ax, (ttl, r, kind, bar_km) in zip(axes, panels):
        nodes = r["nodes"]
        x = g.x[nodes] / 1000.0
        y = g.y[nodes] / 1000.0
        cx, cy = (x.min() + x.max()) / 2, (y.min() + y.max()) / 2
        span = max(x.max() - x.min(), y.max() - y.min())
        half_win = span * 0.64 + 0.55
        sub = seg.cx[(cx - half_win):(cx + half_win), (cy - half_win):(cy + half_win)]
        sub.plot(ax=ax, color="#dedede", linewidth=0.30, zorder=1)
        sub[sub["score"] >= 55].plot(ax=ax, color=PALE, linewidth=0.34, zorder=2)
        ax.plot(x, y, color="white", linewidth=4.8, solid_capstyle="round", zorder=3)
        ax.plot(x, y, color=GREEN, linewidth=2.4, solid_capstyle="round", zorder=4)
        ax.plot(x[0], y[0], marker="o", markersize=7, markerfacecolor="white",
                markeredgecolor=GREEN, markeredgewidth=1.8, zorder=6)
        if kind == "oneway":
            ax.plot(x[-1], y[-1], marker="s", markersize=7.5, markerfacecolor=GREEN,
                    markeredgecolor="white", markeredgewidth=1.2, zorder=6)

        ax.set_xlim(cx - half_win * 1.03, cx + half_win * 1.03)
        ax.set_ylim(cy - half_win * 0.80, cy + half_win * 0.80)
        ax.set_aspect("equal", adjustable="datalim")
        ax.set_axis_off()

        ax.text(0, 1.10, ttl, transform=ax.transAxes, fontsize=11.5, color=INK,
                fontweight="bold", va="bottom")
        ax.text(0, 1.035, f"{r['length_m'] / 1000:.2f} km · {r['minutes']:.0f} min · "
                          f"{r['score']:.1f} 分 · 树冠 {r['tree_share'] * 100:.0f}% · "
                          f"NO2 {r['no2']:.1f} µg/m³",
                transform=ax.transAxes, fontsize=9.2, color=GRAY, va="bottom")

        # 比例尺（draw 之后统一加，见下）
        scale_bars.append((ax, bar_km))

    fig.suptitle("同一副路网、同一起点，三种路线模式", fontsize=15.5, color=INK,
                 fontweight="bold", x=0.5, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.canvas.draw()
    for ax, bar_km in scale_bars:
        x1, x2 = ax.get_xlim()
        y1, y2 = ax.get_ylim()
        sx = x1 + (x2 - x1) * 0.06
        sy = y1 + (y2 - y1) * 0.085
        ax.plot([sx, sx + bar_km], [sy, sy], color=INK, lw=2.8,
                solid_capstyle="butt", zorder=8)
        ax.text(sx + bar_km / 2, sy + (y2 - y1) * 0.022, f"{bar_km} km",
                ha="center", va="bottom", fontsize=8.6, color=INK, zorder=8)

    fig.suptitle("同一副路网、同一起点，三种路线模式", fontsize=15.5, color=INK,
                 fontweight="bold", x=0.5, y=0.985)
    p = OUT / "fig_route_modes.png"
    fig.savefig(p, facecolor="white")
    plt.close(fig)
    print("  ", p.name)
    return panels


def fig_gradient():
    byc = pd.read_csv(OUT / "_ring_class.csv", encoding="utf-8-sig")
    allring = pd.read_csv(OUT / "_ring_all.csv", encoding="utf-8-sig").set_index("ring")
    rings = ["<2", "2–4", "4–6", "6–8", "8–12", "12–20", "20–40", ">40"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.8, 5.7), dpi=190,
                                   gridspec_kw={"width_ratios": [1.05, 1]})

    xs = range(len(rings))
    no2 = [allring.loc[r, "no2"] for r in rings]
    pm = [allring.loc[r, "pm25"] for r in rings]
    ax1.plot(xs, no2, marker="o", markersize=7, color=GREEN, linewidth=2.6,
             markerfacecolor="white", markeredgewidth=2, zorder=4, label="NO2（机动车）")
    ax1.plot(xs, pm, marker="s", markersize=6.5, color=AMBER, linewidth=2.6,
             markerfacecolor="white", markeredgewidth=2, zorder=4, label="PM2.5")
    for i, (a, b) in enumerate(zip(no2, pm)):
        ax1.annotate(f"{a:.1f}", (i, a), textcoords="offset points", xytext=(0, -16),
                     ha="center", fontsize=8.6, color=GREEN, fontweight="bold")
        ax1.annotate(f"{b:.1f}", (i, b), textcoords="offset points", xytext=(0, 10),
                     ha="center", fontsize=8.6, color=AMBER, fontweight="bold")
    ax1.set_xticks(list(xs))
    ax1.set_xticklabels(rings, fontsize=9.5)
    ax1.set_xlabel("到江汉路（城市中心）的直线距离，km", fontsize=10, color="#444")
    ax1.set_ylabel("年均浓度，µg/m³", fontsize=10, color="#444")
    ax1.set_ylim(14, 43)
    ax1.legend(frameon=False, fontsize=9.5, loc="center right")
    style_ax(ax1)
    ax1.text(0.03, 0.96, "NO2 跟着距离走：28.8 → 18.9（1.5×，ρ = −0.90）\n"
                         "PM2.5 基本不动：35.0 → 38.3（1.09×，没有梯度）",
             transform=ax1.transAxes, fontsize=9.5, color="#2f3b36", va="top", linespacing=1.7,
             bbox=dict(boxstyle="round,pad=0.45", fc="#f4f8f5", ec="#d8e6dd", lw=0.6))
    title(ax1, "两种污染物，两种空间行为")

    # 右：同一圈层内，换道路等级还剩多少差别（与左图同一 x 轴，便于直接比较）
    rows = []
    for r in rings:
        s = byc[(byc["ring"] == r) & byc["g"].isin(["trunk", "primary", "residential", "footway"])]
        s = s[s["n"] >= 50]
        if len(s) >= 2:
            rows.append((r, float(s["no2"].min()), float(s["no2"].max())))
    ys = np.arange(len(rows))
    for y, (r, lo, hi) in zip(ys, rows):
        ax2.plot([lo, hi], [y, y], color=MID, linewidth=9, solid_capstyle="round", zorder=3)
        ax2.plot([lo, hi], [y, y], color=[GREEN, AMBER][int(hi - lo > 1.0)],
                 linewidth=2.2, solid_capstyle="round", zorder=4)
    ax2.set_yticks(ys)
    ax2.set_yticklabels([r[0] for r in rows], fontsize=9.5)
    ax2.set_ylim(-0.8, len(rows) - 0.15)
    ax2.set_xlim(16.8, 31.4)
    ax2.invert_yaxis()
    ax2.set_xlabel("年均 NO2，µg/m³", fontsize=10, color="#444")
    ax2.set_ylabel("到江汉路的距离，km", fontsize=10, color="#444")
    style_ax(ax2, grid_axis="x")
    ax2.tick_params(axis="y", length=0)
    widest = max(rows, key=lambda t: t[2] - t[1])
    wi = rows.index(widest)
    ax2.annotate(f"这一圈最大差 {widest[2] - widest[1]:.1f}",
                 xy=(widest[2], wi), xytext=(widest[2] + 1.1, wi - 0.62),
                 fontsize=9.0, color="#8a5a1f",
                 arrowprops=dict(arrowstyle="->", color="#b98a4a", lw=0.9))
    ax2.text(0.03, 0.96, "左图那条 NO2 曲线一共下降 9.9 µg/m³，\n而每个圈层内部只差 0.2–1.8 µg/m³",
             transform=ax2.transAxes, fontsize=9.4, color="#2f3b36", va="top", linespacing=1.7,
             bbox=dict(boxstyle="round,pad=0.45", fc="#f4f8f5", ec="#d8e6dd", lw=0.6))
    title(ax2, "换成什么路走，几乎没差别")

    fig.tight_layout()
    p = OUT / "fig_air_gradient.png"
    fig.savefig(p, facecolor="white")
    plt.close(fig)
    print("  ", p.name)


def fig_season():
    labels = ["1 月（冬）", "7 月（夏）", "11 月（秋）"]
    val = [66.6, 12.7, 38.5]
    lo = [58.5, 12.0, 34.5]
    hi = [72.8, 13.6, 42.3]
    cols = [RED, MID, AMBER]

    fig, ax = plt.subplots(figsize=(9.6, 5.0), dpi=190)
    ys = np.arange(3)
    bars = ax.barh(ys, val, height=0.46, color=cols, zorder=3)
    ax.errorbar(val, ys, xerr=[np.array(val) - np.array(lo), np.array(hi) - np.array(val)],
                fmt="none", ecolor="#4a4a4a", elinewidth=1.2, capsize=5, zorder=4)
    for y, v, h in zip(ys, val, hi):
        ax.text(h + 2.2, y, f"{v:.1f}", va="center", fontsize=12, color=INK, fontweight="bold")
    ax.axvline(15, color="#4f9d7d", linewidth=1.2, linestyle=(0, (4, 3)), zorder=2)
    ax.text(15.6, 2.42, "WHO 年均指导值 15", fontsize=8.6, color="#3d7a5e")
    ax.axvline(35, color="#b03a2e", linewidth=1.2, linestyle=(0, (4, 3)), zorder=2)
    ax.text(35.6, 2.42, "国标二级 35", fontsize=8.6, color=RED)
    ax.set_yticks(ys)
    ax.set_yticklabels(labels, fontsize=10.5)
    ax.set_ylim(2.6, -0.6)
    ax.set_xlim(0, 88)
    ax.set_xlabel("全市 PM2.5 月均，µg/m³（误差棒 = 全市 p10–p90）", fontsize=10, color="#444")
    style_ax(ax, grid_axis="x")
    ax.tick_params(axis="y", length=0)
    ax.annotate("", xy=(70.5, 0), xytext=(70.5, 1),
                arrowprops=dict(arrowstyle="<->", color=INK, lw=1.4))
    ax.text(72.0, 0.5, "5.2×", fontsize=15, color=INK, fontweight="bold", va="center")
    ax.text(72.0, 0.50, "\n\n同一座城，月份不同", fontsize=9.2, color="#4a4a4a", va="center")
    title(ax, "空气的第二层规律：时间上的差别远大于空间",
          sub="武汉 2024 年 · CHAP 1 km 网格")
    fig.tight_layout()
    p = OUT / "fig_air_season.png"
    fig.savefig(p, facecolor="white")
    plt.close(fig)
    print("  ", p.name)


def fig_scales():
    """四个杠杆上的空气差异，统一用「倍数」表达。"""
    demo = json.loads((OUT / "routes_demo.json").read_text(encoding="utf-8"))
    o = pd.read_csv(OUT / "origins_air.csv", encoding="utf-8-sig")
    allring = pd.read_csv(OUT / "_ring_all.csv", encoding="utf-8-sig").set_index("ring")

    cand = [r["no2"] for r in demo["loop5"]]
    rows = [
        ("换一种走法\n同一区域 5 km 环线的 6 个候选", min(cand), max(cand),
         f"NO2 {min(cand):.1f}–{max(cand):.1f}", "#b9c7c1"),
        ("换一个城区跑\n5 个起点 × 5 km 环线", o["no2"].min(), o["no2"].max(),
         f"NO2 {o['no2'].min():.1f}–{o['no2'].max():.1f}", MID),
        ("住在中心还是外围\n8 个圈层的年均值", allring["no2"].max(), allring["no2"].min(),
         f"NO2 {allring['no2'].min():.1f}–{allring['no2'].max():.1f}", GREEN),
        ("换一个月份跑\n全市 PM2.5 月均", 12.7, 66.6, "PM2.5 12.7–66.6", "#1a5c46"),
    ]
    fig, ax = plt.subplots(figsize=(10.8, 4.5), dpi=190)
    for i, (label, v0, v1, note, col) in enumerate(rows):
        hi, lo = max(v0, v1), min(v0, v1)
        ratio = hi / lo
        ax.barh(i, ratio - 1.0, left=1.0, height=0.42, color=col, zorder=3)
        ax.text(ratio + 0.12, i, f"{ratio:.2f}×", va="center", fontsize=13.5,
                color=col, fontweight="bold")
        ax.text(ratio + 1.05, i, note, va="center", fontsize=8.8, color=GRAY)
    ax.axvline(1.0, color="#c9d3ce", linewidth=1.0, zorder=2)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows], fontsize=10.5, color=INK, linespacing=1.7)
    ax.set_xlim(1.0, 7.4)
    ax.set_ylim(-0.62, 3.62)
    ax.set_xlabel("最大值 ÷ 最小值（1.0× = 没有差别）", fontsize=9.8, color="#444")
    style_ax(ax, grid_axis="x")
    ax.tick_params(axis="y", length=0, pad=10)
    ax.invert_yaxis()
    title(ax, "空气能帮人选什么：月份  >  住哪儿  >  换城区  >  换走法",
          sub="越靠下，杠杆越大——所以「逐段评分」能榨出的信息很有限")
    fig.tight_layout()
    p = OUT / "fig_air_scales.png"
    fig.savefig(p, facecolor="white")
    plt.close(fig)
    print("  ", p.name)


if __name__ == "__main__":
    print("载入图与空气网格…")
    g, air = load_all()
    print("出图：")
    fig_modes(g, air)
    fig_gradient()
    fig_season()
    fig_scales()
