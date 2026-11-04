"""生成一张完整的 UML 分层架构图（单张 PNG，供 PPT 直接嵌入）。"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

OUT = Path(__file__).resolve().parent / "assets"
OUT.mkdir(parents=True, exist_ok=True)

PRIMARY = "#15503C"
INK = "#1F2A26"
SUB = "#5F6F68"
BAND = "#F2F6F3"

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False


def layer(ax, y, h, title, subtitle):
    ax.add_patch(Rectangle((3, y), 94, h, facecolor=BAND, edgecolor=PRIMARY, linewidth=1.4, zorder=1))
    ax.text(5, y + h - 1.8, title, ha="left", va="top", fontsize=13.6,
            fontweight="bold", color=PRIMARY, zorder=2)
    ax.text(5, y + h - 6.2, subtitle, ha="left", va="top", fontsize=9.0, color=SUB, zorder=2)
    ax.add_patch(Rectangle((4.6, y + 0.9), 90.8, h - 10.4, facecolor="none",
                           edgecolor="#8FA39A", linewidth=1.0, linestyle=(0, (4, 3)), zorder=2))


def components(ax, y, h, items, label):
    n = len(items)
    gap = 1.5
    w = (90.8 - gap * (n + 1)) / n
    x = 4.6 + gap
    for title, line1, line2 in items:
        ax.add_patch(Rectangle((x, y + 1.4), w, 10.4, facecolor="white",
                               edgecolor=INK, linewidth=1.0, zorder=3))
        ax.text(x + w / 2, y + 10.7, title, ha="center", va="top",
                fontsize=11.0, fontweight="bold", color=INK, zorder=4)
        ax.text(x + w / 2, y + 8.2, line1, ha="center", va="top",
                fontsize=8.6, color=SUB, zorder=4)
        if line2:
            ax.text(x + w / 2, y + 5.9, line2, ha="center", va="top",
                    fontsize=8.6, color=SUB, zorder=4)
        x += w + gap


def arrow(ax, y0, y1, label):
    ax.add_patch(FancyArrowPatch((50, y0), (50, y1), arrowstyle="-|>", mutation_scale=15,
                                 linewidth=1.3, color=INK, zorder=5, shrinkA=0, shrinkB=0))
    ax.text(51.4, (y0 + y1) / 2, label, ha="left", va="center", fontsize=9.0, color=INK)


def main() -> None:
    fig, ax = plt.subplots(figsize=(11.6, 5.9), dpi=240)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_axis_off()
    fig.subplots_adjust(left=0.008, right=0.992, top=0.995, bottom=0.005)

    layers = [
        (77.0, "表现层（客户端 · 独立前端工程）",
         "Vue 3.5 + TypeScript + Vite ｜ 只通过 REST / JSON 访问服务，不直连数据", "«component»",
         [("地图视图 MapView", "路段适宜性配色", "环线叠加与图例"),
          ("控制面板 ControlPanel", "起点 / 目标距离", "四个偏好开关"),
          ("结果面板 ResultPanel", "总分 / 六项指标", "三维子分条")]),
        (51.0, "接口层（API 服务 · FastAPI）",
         "参数校验、CORS、Swagger 自动文档 ｜ 无状态，可水平扩展", "«controller»",
         [("LoopsController", "POST /api/loops", "环线 + 指标"),
          ("SegmentsController", "GET /api/segments", "bbox → GeoJSON"),
          ("FacilitiesController", "GET /api/facilities", "运动 / 补给点"),
          ("MetaController", "GET /api/meta · /health", "权重 / 图状态")]),
        (25.0, "算法层（算法内核 · 纯函数）",
         "CSR 稀疏图 + 双向 Dijkstra ｜ 一次环线请求 1.3 s（979,351 节点）", "«service»",
         [("RouteService", "generate_loops()", "折点 → 去程 → 回程 → 筛选"),
          ("GraphService", "load_or_build()", "邻接表 / 最近节点吸附"),
          ("ScoringService", "pref_score · cost_matrix", "权重合成与代价")]),
        (0.4, "数据层（数据文件 · 离线管线产出）",
         "只读挂载，服务重启即生效 ｜ 原始数据 12 GB 不入库", "«repository»",
         [("segments.gpkg", "91,203 段 × 27 字段", "评分 / 空气 / 指标"),
          ("segment_air.csv", "PM2.5 / NO2 年均", "按 osm_id 关联"),
          ("run_graph.npz", "图缓存 37 MB", "可随时重建")]),
    ]

    for y, title, sub, label, items in layers:
        layer(ax, y, 23, title, sub)
        components(ax, y, 23, items, label)

    arrow(ax, 77.0, 74.0, "REST / HTTP + JSON（跨进程，唯一契约）")
    arrow(ax, 51.0, 48.0, "函数调用（同进程，无序列化）")
    arrow(ax, 25.0, 22.0, "读文件（只读挂载，不写回）")

    fig.savefig(OUT / "uml_arch.png", facecolor="white", bbox_inches="tight", pad_inches=0.1)
    print("uml →", OUT / "uml_arch.png")


if __name__ == "__main__":
    main()
