"""起点抖动平均：每个起点在 ±300 m 内取 5 个位置算 top3，再取均值。

目的：环线候选是离散生成的，起点吸附到不同节点会让候选整批换掉，
单点估计带 ±15 分噪声。5 点平均可把噪声压到约 45%。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "build"))

from app import running  # noqa: E402

OUT = ROOT / "data" / "output" / "running" / "v1" / "demo"
PREFS = {"green": 1.0, "safe": 1.0, "flat": 0.6}
D_LAT = 300.0 / 111_320.0
D_LNG = 300.0 / (111_320.0 * np.cos(np.radians(30.55)))


def top3_at(g, lng: float, lat: float):
    loops = running.generate_loops(g, float(lng), float(lat), target_m=5000,
                                   prefs=PREFS, max_candidates=6)
    if not loops:
        return None
    return float(np.mean(sorted((x["score"] for x in loops), reverse=True)[:3]))


def main() -> None:
    g = running.load_or_build()
    src = pd.read_csv(OUT / "hotspots_kept.csv", encoding="utf-8-sig")

    rows = []
    for i, r in src.iterrows():
        lng, lat = float(r["lng"]), float(r["lat"])
        vals = []
        for dx, dy in [(0, 0), (D_LNG, 0), (-D_LNG, 0), (0, D_LAT), (0, -D_LAT)]:
            s = top3_at(g, lng + dx, lat + dy)
            if s is not None:
                vals.append(s)
        if not vals:
            print(f"[{i+1:02d}] {lng:.4f},{lat:.4f}  全部无候选，跳过")
            continue
        v = np.array(vals)
        rows.append({
            "lng": lng, "lat": lat,
            "top3_center": float(r["top3"]),
            "top3_jitter": float(v.mean()),
            "n_used": len(vals),
            "jitter_range": float(v.max() - v.min()),
        })
        print(f"[{i+1:02d}] {lng:.4f},{lat:.4f}  center={r['top3']:.1f}  "
              f"jitter={v.mean():.1f}  (n={len(vals)}, 极差 {v.max()-v.min():.1f})")

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "hotspots_jitter.csv", index=False, encoding="utf-8-sig")

    rho = df[["top3_center", "top3_jitter"]].corr(method="spearman").iloc[0, 1]
    top15_c = set(df.nlargest(15, "top3_center").index)
    top15_j = set(df.nlargest(15, "top3_jitter").index)
    print(f"\n点数 {len(df)}；前后 Spearman = {rho:.3f}")
    print(f"前 15 名重合 {len(top15_c & top15_j)} / 15")
    print(f"抖动极差：中位 {df.jitter_range.median():.1f}，最大 {df.jitter_range.max():.1f}")
    print(f"top3 区间：{df.top3_jitter.min():.1f} – {df.top3_jitter.max():.1f}")


if __name__ == "__main__":
    main()
