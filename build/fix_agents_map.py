"""把 AGENTS.md 的仓库地图与文档索引更新到当前结构（docs 重整 + 两模式后）。"""

from __future__ import annotations

from pathlib import Path

P = Path(__file__).resolve().parents[1] / "AGENTS.md"

EDITS = [
    (
        "| `backend/app/running.py` | **跑步图 + 环线生成（当前核心）** | ✅ |",
        "| `backend/app/running.py` | **跑步图 + 两种路线生成（当前核心）** | ✅ |\n"
        "| `backend/app/api.py` | FastAPI 五端点（loops / segments / facilities / meta / health） | ✅ |",
    ),
    (
        "| `docs/` | 说明书 v4.0、数据字典、进展报告 | ✅ |",
        "| `docs/` | 三个入口文档（说明书 / 分工卡片 / 交接说明）+ 数据、汇报、过程、literature、archive 五个子目录 | ✅ |\n"
        "| `presentation/` | 答辩 PPT、原型图、热点图、讲稿、素材 | ✅ |\n"
        "| `build/` | 生成脚本（配图、PPT、文档同步），非运行时代码 | ✅ |",
    ),
    (
        "| `docs/过程/design-guidelines.md` | 做前端页面前 |",
        "| `docs/过程/design-guidelines.md` | 做前端页面前 |\n"
        "| `docs/分工卡片.md` | 组内分工、交付物与剩余工作 |\n"
        "| `docs/汇报/答辩稿.md`、`docs/汇报/讲稿.md` | 排练与答辩 |\n"
        "| `docs/literature/参考文献.md` | 已核对过的引用清单与「不能说什么」 |",
    ),
]


def main() -> None:
    s = P.read_text(encoding="utf-8")
    for old, new in EDITS:
        if old in s:
            s = s.replace(old, new)
            print("ok  ", old.splitlines()[0][:50])
        else:
            print("miss", old.splitlines()[0][:50])
    P.write_text(s, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
