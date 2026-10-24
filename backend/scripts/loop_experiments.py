# -*- coding: utf-8 -*-
"""环线实验台：量化"形状好不好"（卡片 5）。

当前 generate_loops 只保证"闭合、长度接近、不原路返回"，不保证形状好看。
这个脚本给出可比较的指标，方便改进前后对比：

    length_error   |实际长度 − 目标| / 目标
    turns          相邻三段夹角 > 45° 的次数
    zigzag         夹角 > 90° 的次数（锯齿感）
    repeat_nodes   同一条环线里被经过两次以上的节点数
    retrace_edges  正反两个方向都被走过的边数（应恒为 0）

TODO(卡片 5)：
  - 实现转弯角约束（在代价里加 turn penalty，需要把"来向"纳入状态）；
  - 3 km 档放宽折点带或允许不同折点数量；
  - 惩罚重复经过的路口（当前只惩罚重复边）；
  - 改进前后各跑一次，把两张表放进 docs/开发进展-慢跑适宜性与环线.md。

用法：
    .\\.venv\\Scripts\\python.exe backend\\scripts\\loop_experiments.py --targets 3000 5000 10000
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import running  # noqa: E402

OUT = ROOT / "data" / "output" / "running" / "v1" / "experiments"

ORIGINS = [
    ("wuda", "武汉大学", 114.3547, 30.5342),
    ("donghu", "东湖绿道", 114.4100, 30.5480),
    ("jiangtan", "汉口江滩", 114.2960, 30.5980),
]


def loop_metrics(g: running.RunGraph, nodes: list[int], target_m: float) -> dict:
    xy = np.array([[g.x[n], g.y[n]] for n in nodes])
    turns = zigzag = 0
    for i in range(1, len(xy) - 1):
        v1 = xy[i] - xy[i - 1]
        v2 = xy[i + 1] - xy[i]
        n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
        if n1 < 1e-6 or n2 < 1e-6:
            continue
        cos = float(np.clip(np.dot(v1, v2) / (n1 * n2), -1, 1))
        ang = np.degrees(np.arccos(cos))
        if ang > 45:
            turns += 1
        if ang > 90:
            zigzag += 1

    pairs = list(zip(nodes[:-1], nodes[1:]))
    retrace = len({(a, b) for a, b in pairs} & {(b, a) for a, b in pairs})
    visited = pd.Series(nodes).value_counts()
    repeats = int((visited > 1).sum())

    from collections import Counter
    length = sum(float(g.csr_len[a, b]) for a, b in pairs if g.csr_len[a, b] > 0)
    return {
        "length_m": round(length, 1),
        "length_error": round(abs(length - target_m) / target_m, 3),
        "turns": turns,
        "zigzag": zigzag,
        "repeat_nodes": repeats,
        "retrace_edges": retrace,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", nargs="+", type=int, default=[3000, 5000, 10000])
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    g = running.load_or_build()
    print(f"[exp] 图 {g.n:,} 节点 / {g.csr_len.nnz:,} 边")

    rows = []
    for slug, name, lng, lat in ORIGINS:
        for target in args.targets:
            loops = running.generate_loops(g, lng, lat, target)
            print(f"\n{name} · {target/1000:.0f} km → {len(loops)} 条候选")
            for rank, lp in enumerate(loops[:3], 1):
                m = loop_metrics(g, lp["nodes"], target)
                row = {
                    "origin": slug, "name": name, "target_m": target, "rank": rank,
                    "score": lp["score"], **m,
                }
                rows.append(row)
                print(f"  #{rank} {m['length_m']/1000:.2f} km  误差 {m['length_error']:.1%}  "
                      f"转弯 {m['turns']}（锯齿 {m['zigzag']}）  "
                      f"重复节点 {m['repeat_nodes']}  原路返回 {m['retrace_edges']}")

    df = pd.DataFrame(rows)
    csv = OUT / "loop_metrics.csv"
    df.to_csv(csv, index=False, encoding="utf-8-sig")
    (OUT / "summary.json").write_text(
        json.dumps({
            "notes": [
                "retrace_edges 应为 0：算法对去程边双向惩罚",
                "turns/zigzag 越低越接近手工设计的环线",
                "3 km 档候选数量是已知短板",
            ],
            "means": {
                "turns": round(float(df["turns"].mean()), 1),
                "zigzag": round(float(df["zigzag"].mean()), 1),
                "length_error": round(float(df["length_error"].mean()), 3),
            },
            "by_target": {
                str(t): int((df["target_m"] == t).sum()) for t in args.targets
            },
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[exp] 写出 {csv.relative_to(ROOT)}")
    print("均值：", f"转弯 {df['turns'].mean():.1f}，锯齿 {df['zigzag'].mean():.1f}，"
          f"长度误差 {df['length_error'].mean():.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
