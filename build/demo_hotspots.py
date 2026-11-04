"""Scan a grid of origins, score 5 km loops, and map where Wuhan runs best."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT.parent / "build"))

from app import running  # noqa: E402

OUT = ROOT / "data" / "output" / "running" / "v1" / "demo"
DEMO = ROOT / "build"

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

GREEN = "#1a5c46"
MID = "#4f9d7d"
PALE = "#a8d5bd"
AMBER = "#c0762a"
INK = "#1f2a26"
GRAY = "#8a9a93"

LNG0, LNG1 = 114.19, 114.46
LAT0, LAT1 = 30.47, 30.63
NX, NY = 9, 7


def main() -> None:
    g = running.load_or_build()
    rows = []
    for ix, lng in enumerate(np.linspace(LNG0, LNG1, NX)):
        for iy, lat in enumerate(np.linspace(LAT0, LAT1, NY)):
            try:
                loops = running.generate_loops(g, float(lng), float(lat), target_m=5000,
                                               prefs={"green": 1.0, "safe": 1.0, "flat": 0.6},
                                               max_candidates=6)
            except Exception as exc:  # noqa: BLE001
                print(f"[skip] {lng:.4f},{lat:.4f} {exc}")
                continue
            if not loops:
                continue
            best = max(x["score"] for x in loops)
            top3 = np.mean(sorted((x["score"] for x in loops), reverse=True)[:3])
            rows.append({"lng": float(lng), "lat": float(lat), "n": len(loops),
                         "best": float(best), "top3": float(top3),
                         "len_m": float(loops[0]["length_m"])})
            print(f"[{len(rows):02d}] {lng:.4f},{lat:.4f}  n={len(loops)}  best={best:.1f}  top3={top3:.1f}")
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "hotspots.csv", index=False, encoding="utf-8-sig")
    summary = {
        "origins": len(df),
        "best_max": float(df["best"].max()),
        "best_median": float(df["best"].median()),
        "top3_min": float(df["top3"].min()),
        "top3_max": float(df["top3"].max()),
    }
    (OUT / "hotspots_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    print(summary)
    plot(df)


def plot(df: pd.DataFrame, title: bool = True) -> None:
    import geopandas as gpd
    from shapely.geometry import box, Point

    seg = gpd.read_file(ROOT / "data" / "processed" / "running" / "v1" / "segments.gpkg",
                        layer="segments").to_crs(32650)
    clip = gpd.GeoDataFrame(geometry=[box(LNG0 - 0.02, LAT0 - 0.02, LNG1 + 0.02, LAT1 + 0.02)],
                            crs=4326).to_crs(32650).geometry.iloc[0]
    seg = seg[seg.intersects(clip)]

    pts = gpd.GeoDataFrame(
        df, geometry=[Point(xy) for xy in zip(df["lng"], df["lat"])], crs=4326
    ).to_crs(32650)
    xs = pts.geometry.x.to_numpy()
    ys = pts.geometry.y.to_numpy()

    fig, ax = plt.subplots(figsize=(10.4, 7.2), dpi=200)
    seg.plot(ax=ax, color="#e6e6e6", linewidth=0.25, zorder=1)
    seg[seg["score"] >= 55].plot(ax=ax, color="#cfe4d8", linewidth=0.3, zorder=2)

    v = df["top3"].to_numpy()
    order = v.argsort().argsort()
    norm = order / max(len(v) - 1, 1)

    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list(
        "hot", ["#AFD6C0", "#63AE8A", "#2E7A5D", "#154C3B"]
    )
    sizes = 26 + 470 * norm ** 1.45

    # 只给前 15 名上色，其余按分数画成灰点
    top15 = set(order.argsort()[-15:])
    colors = [cmap(norm[i]) if i in top15 else "#C6CFCA" for i in range(len(v))]
    edge = ["#2E7A5D" if i in top15 else "#D2DAD5" for i in range(len(v))]
    alpha = [0.98 if i in top15 else 0.9 for i in range(len(v))]
    ax.scatter(xs, ys, s=sizes, c=colors, edgecolor=edge,
               linewidth=0.55, alpha=alpha, zorder=5)

    for j, i in enumerate(sorted(top15, key=lambda k: -v[k])):
        ax.annotate(f"{j+1}", (xs[i], ys[i]), fontsize=8.2, color="white",
                    fontweight="bold", ha="center", va="center", zorder=8)

    handles = [
        ax.scatter([], [], s=26 + 470 * 0.97 ** 1.45, c=[cmap(0.97)],
                   edgecolor="#2E7A5D", linewidth=0.55, label="前 15 名"),
        ax.scatter([], [], s=26 + 470 * 0.55 ** 1.45, c=["#C6CFCA"],
                   edgecolor="#D2DAD5", linewidth=0.55, label=f"其余 {len(v) - 15} 个起点"),
    ]
    ax.legend(handles=handles, loc="lower right", bbox_to_anchor=(0.985, 0.02),
              frameon=True, facecolor="white", edgecolor="#DDE6E0", framealpha=0.92,
              fontsize=8.8, labelspacing=1.2, borderpad=0.8, handletextpad=0.7,
              title="点大小＝前三条环线均分", title_fontsize=8.8)
    labels = [("东湖绿道", 114.412, 30.556), ("汉口江滩", 114.292, 30.596),
              ("沙湖", 114.328, 30.573), ("月湖", 114.256, 30.556),
              ("青山江滩", 114.392, 30.612), ("南湖", 114.335, 30.505)]
    lab = gpd.GeoDataFrame(
        {"name": [n for n, _, _ in labels]},
        geometry=[Point(lng, lat) for _, lng, lat in labels], crs=4326
    ).to_crs(32650)
    for name, geom in zip(lab["name"], lab.geometry):
        ax.annotate(name, (geom.x, geom.y), fontsize=9, color="#33443D",
                    ha="center", va="center", xytext=(0, 20), textcoords="offset points",
                    zorder=7, bbox=dict(boxstyle="round,pad=0.18", fc="white",
                                        ec="none", alpha=0.72))
    ax.set_xlim(xs.min() - 3500, xs.max() + 2000)
    ax.set_ylim(ys.min() - 2500, ys.max() + 3000)
    ax.set_aspect("equal", adjustable="box")
    ax.set_axis_off()
    if title:
        ax.set_title(f"武汉 {len(df)} 个起点 × 5 km 环线：哪里跑起来分数最高",
                     fontsize=13, pad=16, color=INK)
        ax.text(0.5, 1.008, "彩色 = 前 15 名（编号 1–15）；灰点 = 其余起点，大小仍按分数（34–74 分）",
                transform=ax.transAxes, ha="center", va="bottom", fontsize=9.2, color=GRAY)

    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    bx, by = x0 + 0.62 * (x1 - x0), y0 + 0.045 * (y1 - y0)
    ax.plot([bx, bx + 5000], [by, by], color=INK, linewidth=3, solid_capstyle="butt")
    ax.text(bx + 2500, by + 0.016 * (y1 - y0), "5 km", ha="center", fontsize=8.6, color=INK)

    fig.subplots_adjust(left=0.01, right=0.99, top=0.995 if not title else 0.90, bottom=0.02)
    out = OUT / "fig_hotspots.png"
    fig.savefig(out, facecolor="white")
    print("图 →", out)

if __name__ == "__main__":
    main()
