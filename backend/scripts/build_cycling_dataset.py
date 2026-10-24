# -*- coding: utf-8 -*-
"""骑行适宜性评分骨架（卡片 4）。

与跑步共用同一张路段表，只换权重与规则：
  - 坡度更敏感（6% 记 0 分，跑步是 10%）；
  - 机动车暴露权重更高；
  - 有专用自行车道（fclass == cycleway）直接加分。

TODO(卡片 4)：
  - 校准权重并说明理由（可参考《城市步行和自行车交通系统规划标准》）；
  - 加"路面材质"维度（当前 OSM 覆盖率 4.3%，只在有值时加分）；
  - 生成 1–2 条示例骑行环线，与跑步环线对比。

用法：
    .\\.venv\\Scripts\\python.exe backend\\scripts\\build_cycling_dataset.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "data" / "processed" / "running" / "v1"

# 骑行权重（TODO：认领人负责给依据）
W = {"safety": 0.35, "green": 0.15, "slope": 0.30, "cross": 0.10, "fac": 0.10}
SLOPE_ZERO = 6.0      # % 以上记 0 分
CYCLEWAY_BONUS = 12.0


def main() -> int:
    gpkg = RUN / "segments.gpkg"
    if not gpkg.exists():
        print("缺少 segments.gpkg，先跑 build_running_dataset.py", file=sys.stderr)
        return 1

    import geopandas as gpd

    print("[cycling] 读取路段 ...")
    gdf = gpd.read_file(gpkg, layer="segments")

    slope = np.clip(100 * (1 - gdf["slope_mean_pct"].to_numpy() / SLOPE_ZERO), 0, 100)
    safety = gdf["s_safety"].to_numpy()
    green = gdf["s_green"].to_numpy()
    cross = gdf["s_cross"].to_numpy()
    fac = gdf["s_fac"].to_numpy()

    bonus = np.where(gdf["fclass"].to_numpy() == "cycleway", CYCLEWAY_BONUS, 0.0)

    out = pd.DataFrame({
        "osm_id": gdf["osm_id"].to_numpy(),
        "fclass": gdf["fclass"].to_numpy(),
        "length_m": gdf["length_m"].to_numpy(),
        "slope_mean_pct": gdf["slope_mean_pct"].to_numpy(),
        "tree_share": gdf["tree_share"].to_numpy(),
        "c_safety": np.round(safety, 1),
        "c_green": np.round(green, 1),
        "c_slope": np.round(slope, 1),
        "c_cross": np.round(cross, 1),
        "c_fac": np.round(fac, 1),
        "c_cycleway": bonus,
    })

    total_w = sum(W.values())
    raw = (
        W["safety"] * out["c_safety"]
        + W["green"] * out["c_green"]
        + W["slope"] * out["c_slope"]
        + W["cross"] * out["c_cross"]
        + W["fac"] * out["c_fac"]
    ) / total_w
    out["score_cycling"] = np.round(np.clip(raw + out["c_cycleway"], 0, 100), 1)
    out["score_running"] = np.round(gdf["score"].to_numpy(), 1)
    out["delta"] = np.round(out["score_cycling"] - out["score_running"], 1)

    target = RUN / "segment_cycling.csv"
    out.to_csv(target, index=False, encoding="utf-8-sig")

    summary = {
        "weights": W,
        "slope_zero_pct": SLOPE_ZERO,
        "cycleway_bonus": CYCLEWAY_BONUS,
        "segments": int(len(out)),
        "cycling_median": round(float(out["score_cycling"].median()), 1),
        "running_median": round(float(out["score_running"].median()), 1),
        "cycleway_segments": int((out["fclass"] == "cycleway").sum()),
        "steep_penalised": int((out["slope_mean_pct"] > SLOPE_ZERO).sum()),
        "note": "骑行在陡坡段应明显低于跑步；cycleway 段应明显高于同位置普通路。",
    }
    (RUN / "cycling_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[cycling] 写出 {target.relative_to(ROOT)}")
    print("\n坡度 > 6% 的路段（骑行扣分、跑步不扣）：")
    print(out.nlargest(5, "slope_mean_pct")[
        ["fclass", "slope_mean_pct", "score_cycling", "score_running", "delta"]
    ].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
