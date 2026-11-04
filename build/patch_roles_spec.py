"""一次性补丁：分工卡片角色拆成 9 行；说明书补马拉松边界、1–42 km 支持范围、±15% 精度口径。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---------- 分工卡片 ----------
p = ROOT / "docs" / "分工卡片.md"
s = p.read_text(encoding="utf-8")
start = s.index("| # | 角色 | 负责内容 | 已交付 | 证据路径 | 负责人 |")
end = s.index("> 一人可兼多角色；实际按提交记录填写。组长另负责排期与对外沟通。")

table = """| # | 角色 | 负责内容 | 已交付 | 证据路径 | 负责人 |
|---|---|---|---|---|---|
| 1 | 数据工程 A | 路网清洗、投影、坡度、地表覆盖 | 91,203 段 × 24 字段底表；坡度、树冠两列 | `data/processed/running/v1/segment_{slope,canopy}.csv` | （待填） |
| 2 | 数据工程 B | 外部数据抓取与校验（高德、CHAP、AQICN） | 场馆 5,137 个；空气 1 km 年均 + 12 个月；站点 10 个 | `amap_sport_poi.csv`、`segment_air.csv`、`air_monthly_wuhan.csv` | （待填） |
| 3 | 评分算法 | 六维子分与公式、分档 | `segments.gpkg` 27 字段里的六个 `s_*` 列与 `score`/`grade` | `backend/scripts/build_running_dataset.py` | （待填） |
| 4 | 权重与检验 | 权重依据、16 组敏感性、分档阈值 | 六维权重重排（0.25/0.25/0.15/0.10/0.05/0.15）、16 组检验 | `sensitivity_analysis.py`、`data/output/running/v1/sensitivity/` | （待填） |
| 5 | 路线算法 | 图构建、CSR 双向 Dijkstra、偏好代价函数 | 979,351 节点图、代价公式、1.3–1.6 s/次 | `backend/app/running.py` | （待填） |
| 6 | 路线模式 | 环线与单行线的选点规则、候选去重、长度窗 | 两种模式；1–42 km 全扫 42/42 有解、误差 −14.9%~+13.2% | `run_loop_demo.py`、`build/demo_routes.py`、`build/probe_sweep.py` | （待填） |
| 7 | 空间扫描 | 50 起点网格扫描、抖动去噪、热点判定 | 50 起点 × 5 次 300 m 抖动均值、热点图、±2 分标准误 | `build/hotspot_jitter.py`、`presentation/热点图.png` | （待填） |
| 8 | 后端与原型 | FastAPI 五端点、GeoJSON 契约、高保真原型 | `/api/loops` 等 5 个接口；1600×1000 原型 | `backend/app/api.py`、`build/proto/` | （待填） |
| 9 | 文档与答辩 | 说明书、数据字典、PPT、讲稿、文献 | 13 页 PPT、讲稿、问答 8 条、5 篇 PDF + 15 条参考文献 | `docs/`、`presentation/` | （待填） |

"""
s = s[:start] + table + s[end:]
s = s.replace(
    "评分中位 **52.8**、最高 **79.8**；路线 **1.3–1.6 秒/次**；",
    "评分中位 **52.8**、最高 **79.8**；路线 **1–42 km 任意整千米**、**1.2 秒/次**；",
)
s = s.replace(
    "| 2 | Vue 完整交互页（点选起点、切模式、展示路线） | 前端原型 |",
    "| 2 | Vue 完整交互页（点选起点、切模式、展示路线） | 后端与原型 |",
)
p.write_text(s, encoding="utf-8")
print("分工卡片 ok，角色行数 =", sum(1 for ln in s.splitlines() if ln.startswith("| ") and ln[2:3].isdigit()))

# ---------- 说明书 ----------
q = ROOT / "docs" / "项目说明书.md"
t = q.read_text(encoding="utf-8")

a1 = "- 逐段车流量与逐段空气浓度（前者无公开数据，后者受 1 km 网格分辨率限制）。"
assert a1 in t
t = t.replace(
    a1,
    a1
    + "\n- 马拉松赛事口径的指标（补给点、封路、计时、赛道认证等）。**赛事我们不做承诺**；\n"
    "  只承诺一件事：给定起点，能生成足够长（1–42 km 任意整千米）的闭合环线。",
)

a2 = "- 图缓存 37 MB，加载 0.4 秒。"
assert a2 in t
t = t.replace(
    a2,
    a2
    + "\n- **目标距离支持范围**：环线对 1–42 km 的每个整千米都实跑过，**42/42 全部有解**，\n"
    "  候选 2–7 条（中位 4），长度误差 **−14.9% ~ +13.2%**，单次 1.1–1.3 秒；\n"
    "  单行线抽查 1/5/10/20/42 km 均能生成，误差 +0.6% ~ +14.2%。",
)

a3 = "- 目标距离 3 km 时候选折点少，偶尔只有 1–2 条可选；"
assert a3 in t
t = t.replace(
    a3,
    "- **长度是「±15% 内取最优」，不是 ±5%**：折点只能落在路网节点上，离散；\n"
    "  要更准可把候选数从 8 提到 24、或把环带收窄到 ±6%，代价是慢几倍；\n" + a3,
)

q.write_text(t, encoding="utf-8")
print("说明书 ok")
