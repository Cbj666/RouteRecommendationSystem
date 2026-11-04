# -*- coding: utf-8 -*-
"""敏感性分析骨架（卡片 3）。

做三件事，结果写到 data/output/running/v1/sensitivity/：
1. 单维度权重 ±20% 扰动，看路段排序变了多少（Spearman + 前 10% 重合度）；
2. 与三种替代权重方案对比（等权 / AHP 式 / 地形优先）；
3. 输出一张 CSV 供画图。

TODO(卡片 3)：
  - 把结果写成 `docs/验证与敏感性分析.md`，回答"权重变多少会改结论"；
  - 加"与已知绿道对照"（东湖绿道/江滩 vs 全市均值）；
  - 加城区 / 远城区分组统计。

用法：
    .\\.venv\\Scripts\\python.exe backend\\scripts\\sensitivity_analysis.py
"""
from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "data" / "processed" / "running" / "v1"
OUT = ROOT / "data" / "output" / "running" / "v1" / "sensitivity"

BASE_W = {"safety": 0.25, "green": 0.25, "slope": 0.15, "cross": 0.10, "fac": 0.05, "air": 0.15}


def score_with(df: pd.DataFrame, w: dict[str, float]) -> np.ndarray:
    total = sum(w.values())
    return sum((w[k] / total) * df[f"s_{k}"].to_numpy() for k in w)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    gpkg = RUN / "segments.gpkg"
    if not gpkg.exists():
        print("缺少 segments.gpkg，请先跑 build_running_dataset.py", file=sys.stderr)
        return 1

    import geopandas as gpd

    print("[sens] 读取评分表 ...")
    gdf = gpd.read_file(gpkg, layer="segments", columns=[
        "score", "s_safety", "s_green", "s_slope", "s_cross", "s_fac", "s_air", "length_m",
    ])
    base = score_with(gdf, BASE_W)
    gdf["base"] = base
    top = np.argsort(-base)[: int(len(base) * 0.10)]

    rows = []

    # 1) 单维度 ±20%
    for k in BASE_W:
        for factor in (0.8, 1.2):
            w = dict(BASE_W)
            w[k] = BASE_W[k] * factor
            s = score_with(gdf, w)
            rho = spearmanr(base, s).statistic
            overlap = len(set(np.argsort(-s)[: len(top)]) & set(top)) / len(top)
            rows.append({
                "scenario": f"{k}_{factor:+.0%}",
                "spearman": round(float(rho), 4),
                "top10_overlap": round(float(overlap), 4),
                "mean_shift": round(float(np.mean(s - base)), 2),
            })

    # 2) 替代方案
    alternatives = {
        "equal": {k: 0.95 / 6 for k in BASE_W},
        "ahp_like": {"safety": 0.32, "green": 0.27, "slope": 0.17, "cross": 0.09, "fac": 0.05, "air": 0.10},
        "terrain_first": {"safety": 0.20, "green": 0.20, "slope": 0.40, "cross": 0.10, "fac": 0.05, "air": 0.05},
        "comfort_first": {"safety": 0.20, "green": 0.35, "slope": 0.30, "cross": 0.05, "fac": 0.05, "air": 0.05},
    }
    for name, w in alternatives.items():
        s = score_with(gdf, w)
        rho = spearmanr(base, s).statistic
        overlap = len(set(np.argsort(-s)[: len(top)]) & set(top)) / len(top)
        rows.append({
            "scenario": f"alt_{name}",
            "spearman": round(float(rho), 4),
            "top10_overlap": round(float(overlap), 4),
            "mean_shift": round(float(np.mean(s - base)), 2),
        })

    df = pd.DataFrame(rows)
    csv = OUT / "weight_sensitivity.csv"
    df.to_csv(csv, index=False, encoding="utf-8-sig")
    summary = {
        "baseline_weights": BASE_W,
        "segments": int(len(gdf)),
        "min_spearman": float(df["spearman"].min()),
        "min_top10_overlap": float(df["top10_overlap"].min()),
        "rows": df.to_dict(orient="records"),
        "note": "spearman/top10_overlap 越高说明该扰动不改变结论；"
                "低于 0.9 / 0.8 时需要在报告里单独说明。",
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(df.to_string(index=False))
    print(f"\n[sens] 写出 {csv.relative_to(ROOT)}")
    print(f"[sens] 最低 Spearman {summary['min_spearman']}，"
          f"最低前10%重合 {summary['min_top10_overlap']}")

    # TODO(卡片 3): 在这里加"已知绿道 vs 全市"的对照，输出箱线图
    return 0


if __name__ == "__main__":
    sys.exit(main())
