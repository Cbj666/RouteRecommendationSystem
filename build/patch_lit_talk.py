"""让讲稿/答辩稿的「创新三」与 PPT 卡片 03 对齐为「两种模式的统一框架」。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITS = [
    (
        ROOT / "docs" / "汇报" / "讲稿.md",
        "创新三是**空间结论的规模化**：用同一套流程扫 50 个起点，把「哪里跑起来分数高」从个案做成可复核的地图。",
        "创新三是**两种模式的统一框架**：同一张图、同一套偏好代价，只换折点与终点规则就得到环线和单行线；"
        "1–42 km 任意整千米都能出路线，长度控制在目标 ±15% 以内。",
    ),
    (
        ROOT / "docs" / "汇报" / "答辩稿.md",
        "、空间结论的规模化（50 个起点的热点地图）",
        "、两种模式的统一框架（同一张图、同一套代价，1–42 km 任意整千米）",
    ),
]

for path, old, new in EDITS:
    s = path.read_text(encoding="utf-8")
    if old not in s:
        print("MISS", path.name, old[:30])
        continue
    path.write_text(s.replace(old, new), encoding="utf-8")
    print("ok", path.name)

# 讲稿里“三个算法创新”改为明确的三项名，避免与 PPT 标题不一致
p = ROOT / "docs" / "汇报" / "讲稿.md"
s = p.read_text(encoding="utf-8")
s = s.replace(
    "三个算法创新、两项可交付结论。",
    "三个算法创新（六维评价 / 环线生成 / 两种模式的统一框架）、两项可交付结论。",
)
p.write_text(s, encoding="utf-8")
print("讲稿标题行已补全")
