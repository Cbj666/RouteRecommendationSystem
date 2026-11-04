"""把 `docs/接口契约.md` 补进交接说明的文档地图（一级目录现已 4 个文件）。"""

from __future__ import annotations

from pathlib import Path

P = Path("docs/项目交接说明.md")
s = P.read_text(encoding="utf-8")

old_intro = "一级目录只放三个入口文档，其余按用途收进子目录。"
new_intro = "一级目录只放三个入口文档 + 一份接口契约，其余按用途收进子目录。"
assert old_intro in s, "intro not found"
s = s.replace(old_intro, new_intro)

anchor = "| `docs/项目交接说明.md` | 本文件：进度、资产、限制、下一步 | 接手项目 |"
row = (
    anchor
    + "\n| `docs/接口契约.md` | 5 个 REST 端点的字段、样例、错误结构与已知缺口 | "
    "**前后端开工前必读**，改接口先改这里 |"
)
assert anchor in s, "anchor row not found"
s = s.replace(anchor, row)

P.write_text(s, encoding="utf-8")
print("patched", "接口契约.md" in s, s.count("接口契约"))
