from pathlib import Path

# 1) AGENTS.md：build/ 与 presentation/ 两行补「哪些入库」
p = Path('AGENTS.md')
s = p.read_text(encoding='utf-8')
old = "| `presentation/` | 答辩 PPT、原型图、热点图、讲稿、素材 | ✅ |\n| `build/` | 生成脚本（配图、PPT、文档同步），非运行时代码 | ✅ |"
new = ("| `presentation/` | 答辩 PPT、原型图、热点图、讲稿、素材（`素材/*.png` 不入库，可重出） | ✅ |\n"
       "| `build/` | 生成脚本（配图、PPT、文档同步），**只入库 `*.py` 与 `proto/*.html`**，渲染产物不入库 | ✅ |")
assert old in s, 'AGENTS 行没匹配到'
p.write_text(s.replace(old, new, 1), encoding='utf-8')
print('AGENTS.md 已更新')

# 2) 交接说明 §九：补 .gitignore 现行规则
p = Path('docs/项目交接说明.md')
s = p.read_text(encoding='utf-8')
old = """`.gitignore` 排除：`.venv/`、`.env`、`data/raw/`、`data/cache/`、
`data/interim/amap_pilot/`、`data/processed/{graph,running/graph}/`、`vendor/`。"""
new = """`.gitignore` 排除：`.venv/`、`.env`、`data/raw/`、`data/cache/`、
`data/interim/amap_pilot/`、`data/processed/{graph,running/graph}/`、`vendor/`、
`projects/`（ppt-master 工作区，130 MB）、`docs/literature/*.pdf`（文献全文）、
`presentation/素材/*.png`（36 张，可用 `build/make_geometry_assets*.py` 重出）、
`data/processed/running/v1/{segment_air_pm25,segment_air_no2,edge_air_cache.npz}`。

`build/` 只入库脚本：所有 `build/*.py` 与 `build/proto/*.html` 进库，
渲染图（`build/**/*.png`）、OpenAlex 候选、探针输出等不入库。"""
assert old in s, '交接说明段落没匹配到'
p.write_text(s.replace(old, new, 1), encoding='utf-8')
print('交接说明 §九 已更新')
