# -*- coding: utf-8 -*-
"""生成展示 PPT 用的图表（matplotlib）。输出到 build/ppt/assets/。

运行： .venv 里的 python 执行本脚本
"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "assets"
OUT.mkdir(parents=True, exist_ok=True)

INK = "#1B2A24"
GRAY = "#6D7C76"
LINE = "#D8E0DB"
GREEN = "#2E8B6B"
GREEN_DEEP = "#14503C"
AMBER = "#C98B2E"
RED = "#B5503B"
PALE = "#EDF3EF"

plt.rcParams.update({
    "font.sans-serif": ["Microsoft YaHei"],
    "font.family": "sans-serif",
    "axes.unicode_minus": False,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": GRAY,
    "ytick.color": INK,
})


def clean(ax, grid_axis="x"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(LINE)
    ax.grid(axis=grid_axis, color=LINE, linewidth=0.8, alpha=0.9)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------- 1. 六维有效度
def chart_dims() -> None:
    rows = [  # 名称, 权重, 中位子分
        ("安全", 0.25, 56.0),
        ("绿化", 0.25, 41.5),
        ("坡度", 0.20, 88.1),
        ("过街", 0.10, 58.0),
        ("空气", 0.10, 54.0),
        ("设施", 0.05, 3.0),
    ]
    fig, ax = plt.subplots(figsize=(5.9, 3.9), dpi=220)
    ys = list(range(len(rows)))[::-1]
    for y, (name, w, v) in zip(ys, rows):
        col = RED if v < 5 else GREEN
        ax.barh(y, v, height=0.46, color=col, zorder=3)
        ax.text(v + 1.8, y, f"{v:.1f}", va="center", ha="left",
                fontsize=11, color=col, fontweight="bold")
        ax.text(-1.8, y, name, va="center", ha="right", fontsize=11, color=INK)
    ax.axvline(50, color=AMBER, linewidth=1.1, linestyle=(0, (4, 3)), zorder=2)
    ax.text(51.2, len(rows) - 0.55, "50 分", fontsize=8.2, color=AMBER, va="center")
    ax.set_xlim(0, 105)
    ax.set_ylim(-0.85, len(rows) - 0.25)
    ax.set_yticks([])
    ax.set_xlabel("该维度子分中位数（0–100）", fontsize=9, color=GRAY, labelpad=6)
    clean(ax)
    ax.set_title("六个维度算出来是什么样：设施维度几乎恒为 0",
                 fontsize=11.5, color=INK, loc="left", pad=10)
    fig.tight_layout(pad=0.4)
    fig.savefig(OUT / "c_dims.png")
    plt.close(fig)


# ---------------------------------------------------------------- 2. 敏感性
def chart_sens() -> None:
    path = ROOT / "data/output/running/v1/sensitivity/weight_sensitivity.csv"
    rows = []
    with path.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            rows.append((r["scenario"], float(r["spearman"]),
                         float(r["top10_overlap"]), float(r["mean_shift"])))
    names = {
        "safety_+80%": "安全 权重 −20%", "safety_+120%": "安全 权重 +20%",
        "green_+80%": "绿化 权重 −20%", "green_+120%": "绿化 权重 +20%",
        "slope_+80%": "坡度 权重 −20%", "slope_+120%": "坡度 权重 +20%",
        "cross_+80%": "过街 权重 −20%", "cross_+120%": "过街 权重 +20%",
        "fac_+80%": "设施 权重 −20%", "fac_+120%": "设施 权重 +20%",
        "air_+80%": "空气 权重 −20%", "air_+120%": "空气 权重 +20%",
        "alt_equal": "全部等权 1/6", "alt_ahp_like": "AHP 型权重",
        "alt_terrain_first": "地形优先", "alt_comfort_first": "舒适优先",
    }
    rows.sort(key=lambda r: r[1])
    fig, ax = plt.subplots(figsize=(6.7, 4.0), dpi=220)
    base = 0.85
    for i, (key, sp, ov, shift) in enumerate(rows):
        alt = key.startswith("alt_")
        col = AMBER if alt else GREEN
        ax.barh(i, sp - base, left=base, height=0.56, color=col, zorder=3, alpha=0.95)
        ax.text(sp + 0.0035, i, f"{sp:.4f}", va="center", fontsize=7.8,
                color=col, fontweight="bold")
    ax.axvline(0.90, color=RED, linewidth=1.0, linestyle=(0, (4, 3)), zorder=2)
    ax.set_xlim(base, 1.008)
    ax.set_ylim(-0.72, len(rows) - 0.24)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([names.get(r[0], r[0]) for r in rows],
                       fontsize=8.6, color=INK)
    ax.tick_params(axis="y", length=0, pad=4)
    ax.tick_params(axis="x", labelsize=8.6)
    ax.set_xlabel("与基准权重的 Spearman 秩相关（横轴自 0.85 起，1.00 = 排序完全一致）",
                  fontsize=8.4, color=GRAY, labelpad=6)
    clean(ax)
    ax.set_title(f"{len(rows)} 种权重方案下，路段排序几乎不变",
                 fontsize=11.5, color=INK, loc="left", pad=10)
    handles = [Rectangle((0, 0), 1, 1, color=GREEN),
               Rectangle((0, 0), 1, 1, color=AMBER),
               Line2D([0], [0], color=RED, linestyle=(0, (4, 3)), linewidth=1.1)]
    ax.legend(handles, ["单维 ±20% 扰动", "整组换权（等权 / AHP / 极端偏好）", "0.90 警戒线"],
              loc="upper center", bbox_to_anchor=(0.5, -0.155), ncol=3,
              frameon=False, fontsize=7.6, handlelength=1.1, columnspacing=1.4,
              borderaxespad=0.0)
    fig.tight_layout(pad=0.4)
    fig.savefig(OUT / "c_sens.png")
    plt.close(fig)


# ---------------------------------------------------------------- 3. 分级构成
def chart_grade() -> None:
    segs = [("差\n<40", 9521, AMBER), ("一般\n40–55", 40483, "#E4CE9A"),
            ("较好\n55–70", 39070, "#8FC3A8"), ("好\n70–85", 2129, "#3E9E77"),
            ("很好\n≥85", 0, GREEN_DEEP)]
    total = sum(s[1] for s in segs) or 91203
    fig, ax = plt.subplots(figsize=(5.5, 2.5), dpi=220)
    xs = range(len(segs))
    for x, (label, n, col) in zip(xs, segs):
        pct = n / total * 100
        ax.bar(x, pct, width=0.58, color=col, zorder=3)
        txt = "0 段" if n == 0 else (f"{pct:.1f}%" if pct >= 1 else "<0.1%")
        ax.text(x, pct + 1.4, txt, ha="center", va="bottom", fontsize=9,
                color=INK, fontweight="bold")
    ax.set_xticks(list(xs))
    ax.set_xticklabels([s[0] for s in segs], fontsize=8.4, linespacing=1.3)
    ax.set_ylim(0, 60)
    ax.set_ylabel("占全部路段比例（%）", fontsize=8.4, color=GRAY)
    ax.tick_params(axis="y", labelsize=8)
    clean(ax, grid_axis="y")
    ax.set_title("9.1 万段路的评分落在哪：一半在「一般」",
                 fontsize=11, color=INK, loc="left", pad=8)
    fig.tight_layout(pad=0.4)
    fig.savefig(OUT / "c_grade.png")
    plt.close(fig)


if __name__ == "__main__":
    chart_dims()
    chart_sens()
    chart_grade()
    for p in sorted(OUT.glob("*.png")):
        print(p.name, f"{p.stat().st_size/1024:.0f} KB")
