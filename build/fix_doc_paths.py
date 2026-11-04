"""把仓库里对 docs/ 旧路径的引用统一改到新结构。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (旧文件名词干, 新相对 docs 的路径)
MOVES = [
    ("项目说明书-v4.0.md", "项目说明书.md"),
    ("分工与任务卡.md", "分工卡片.md"),
    ("README.md", "项目交接说明.md"),  # docs/README.md 已并入交接说明
    ("开发进展-慢跑适宜性与环线.md", "过程/开发进展-慢跑适宜性与环线.md"),
    ("验证与敏感性分析.md", "过程/验证与敏感性分析.md"),
    ("环境与复现.md", "过程/环境与复现.md"),
    ("design-guidelines.md", "过程/design-guidelines.md"),
    ("数据字典-跑步数据集.md", "数据/数据字典-跑步数据集.md"),
    ("数据字典-v1.md", "数据/数据字典-v1.md"),
    ("数据补充清单.md", "数据/数据补充清单.md"),
    ("数据现状与增补建议.md", "数据/数据现状与增补建议.md"),
    ("数据冻结与开发就绪报告.md", "数据/数据冻结与开发就绪报告.md"),
    ("答辩稿.md", "汇报/答辩稿.md"),
    ("讲稿.md", "汇报/讲稿.md"),
    ("参考文献与算法依据.md", "literature/参考文献与算法依据.md"),
    ("论文检索关键词.md", "literature/论文检索关键词.md"),
    ("参考文献.md", "literature/参考文献.md"),
    ("高德公交数据抓取与OSM叠加报告.md", "archive/公交与地铁试点/高德公交数据抓取与OSM叠加报告.md"),
    ("高德公交线路10条试点结果.md", "archive/公交与地铁试点/高德公交线路10条试点结果.md"),
    ("武汉地铁数据准备报告.md", "archive/公交与地铁试点/武汉地铁数据准备报告.md"),
    ("试点结果-百度站点定位与OSM叠合.md", "archive/公交与地铁试点/试点结果-百度站点定位与OSM叠合.md"),
]
# 交接说明本体（在根目录时带 docs/ 前缀，也不带）
ROOT_MOVES = [("项目进度与交接说明.md", "docs/项目交接说明.md")]

SKIP_DIRS = {".git", ".venv", "node_modules", "vendor", "data", "projects", "build"}


def main() -> None:
    files = [
        p
        for p in ROOT.rglob("*.md")
        if not any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts)
    ]
    changed = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        orig = text

        # 1) 先处理根目录那份交接说明（旧名）
        for old, new in ROOT_MOVES:
            text = text.replace(f"`{old}`", f"`{new}`")
            text = text.replace(old, new)

        # 2) docs/ 内文件：用占位符避免二次替换
        for i, (bare, new_rel) in enumerate(MOVES):
            text = text.replace(f"docs/{bare}", f"@@D{i}@@")
            text = text.replace(bare, f"@@D{i}@@")
        for i, (bare, new_rel) in enumerate(MOVES):
            text = text.replace(f"@@D{i}@@", f"docs/{new_rel}")

        if text != orig:
            path.write_text(text, encoding="utf-8", newline="\n")
            changed += 1
            print("updated:", path.relative_to(ROOT))
    print("files changed:", changed)


if __name__ == "__main__":
    main()
