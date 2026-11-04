"""CHAP 1 km 空气污染物 → 每段路一个浓度值（真正的逐段空气维度）。

为什么用它：AQICN 只有 10 个站，91,203 段路里只有 12.7% 落在站点 3 km 内，
用 19 km 外的站点插值得到的是噪声。CHAP（ChinaHighAirPollutants）是 1 km、
逐日/逐月/逐年、100% 覆盖的再分析产品，直接把路段中点的网格值取出来即可。

数据来源（公开免费，无需注册）：
    产品页  https://weijing-rs.github.io/product.html
    PM2.5   Zenodo 10.5281/zenodo.21770406（2022–2025）/ 10.5281/zenodo.6398971（2000–2021）
    NO2     Zenodo 10.5281/zenodo.21774207（2019–2025）
    网格    0.01°（约 1 km）、WGS84、uint16、scale_factor=0.1、单位 µg/m³

用法：
    python backend/scripts/build_air_quality_chap.py --year 2024 --plot
    python backend/scripts/build_air_quality_chap.py --year 2024 --product pm25
    python backend/scripts/build_air_quality_chap.py --year 2024 --product no2 --local x.nc

输出：
    data/raw/chap/CHAP_{PRODUCT}_Y1K_{year}_V{v}.nc      原始网格（5–6 MB，不入库）
    data/processed/running/v1/segment_air_{product}.csv  单产品逐段值
    data/processed/running/v1/segment_air.csv            合并表（osm_id, pm25_ugm3, no2_ugm3）
    data/output/running/v1/air_chap_map.png              分段着色图（--plot）

口径提醒：
    * 这是**年均浓度**（µg/m³），用于"长期暴露"型评分；
      不要和 AQICN 的实时 AQI（分指数、US EPA 口径）混着算。
    * 采样点是路段几何中点；1 km 网格对城市道路足够，跨网格的长路段会损失一点信息。
    * NO2 的空间差异远大于 PM2.5，是"机动车暴露"最好的可替代指标——
      现有 s_safety 用道路等级代理车流，NO2 可以直接替换这个代理。
"""

from __future__ import annotations

import argparse
import urllib.request
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "running" / "v1"
OUTPUT = ROOT / "data" / "output" / "running" / "v1"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
NODATA = 65535

# 产品 → Zenodo 记录与年份区间 / 文件名模板 / netCDF 变量名前缀 / CSV 列名
PRODUCTS: dict[str, dict] = {
    "pm25": {
        "records": [(21770406, 2022, 2025), (6398971, 2000, 2021)],
        "tmpl": "CHAP_PM2.5_Y1K_{year}_V4.nc",
        "tag": "PM2.5",
        "col": "pm25_ugm3",
        "label": "PM2.5",
    },
    "no2": {
        "records": [(21774207, 2019, 2025)],
        "tmpl": "CHAP_NO2_Y1K_{year}_V2.nc",
        "tag": "NO2",
        "col": "no2_ugm3",
        "label": "NO2",
    },
}


def raw_dir() -> Path:
    d = RAW / "chap"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pick_record(product: str, year: int) -> str:
    for rec, lo, hi in PRODUCTS[product]["records"]:
        if lo <= year <= hi:
            return str(rec)
    raise SystemExit(
        f"{product} 在 {year} 年没有公开的年度产品，可选年份："
        + ", ".join(f"{lo}-{hi}" for _, lo, hi in PRODUCTS[product]["records"])
    )


def fetch_year(product: str, year: int, force: bool = False) -> Path:
    """下载（或复用）某年某污染物的 CHAP 年度网格。"""
    name = PRODUCTS[product]["tmpl"].format(year=year)
    dst = raw_dir() / name
    if dst.exists() and not force:
        print(f"[chap] 复用缓存 {dst.name}（{dst.stat().st_size / 1e6:.1f} MB）")
        return dst

    rec = pick_record(product, year)
    url = f"https://zenodo.org/api/records/{rec}/files/{dst.name}/content"
    print(f"[chap] 下载 {dst.name} ← zenodo:{rec}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    tmp = dst.with_suffix(".part")
    with urllib.request.urlopen(req, timeout=180) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(dst)
    print(f"[chap] 完成 {dst.stat().st_size / 1e6:.1f} MB")
    return dst


def sample_segments(nc_path: Path, product: str) -> pd.DataFrame:
    """把 1 km 网格值取到每条路段的中点上。"""
    seg = gpd.read_file(OUT / "segments.gpkg", layer="segments")[
        ["osm_id", "length_m", "in_boundary", "geometry"]
    ]
    seg = seg.to_crs(4326)
    mid = seg.geometry.interpolate(0.5, normalized=True)
    lon = np.asarray(mid.x, dtype="float64")
    lat = np.asarray(mid.y, dtype="float64")

    tag = PRODUCTS[product]["tag"]
    with rasterio.open(nc_path) as src:
        scale = float(src.tags().get(f"{tag}#scale_factor", 1.0))
        win = src.window(lon.min() - 0.05, lat.min() - 0.05, lon.max() + 0.05, lat.max() + 0.05)
        data = src.read(1, window=win, boundless=True, fill_value=NODATA)
        wtr = src.window_transform(win)

    cols = np.floor((lon - wtr.c) / wtr.a).astype(np.int64)
    rows = np.floor((lat - wtr.f) / wtr.e).astype(np.int64)
    ok = (rows >= 0) & (rows < data.shape[0]) & (cols >= 0) & (cols < data.shape[1])
    vals = np.full(len(seg), np.nan, dtype="float32")
    raw = np.zeros(len(seg), dtype="uint16")
    raw[ok] = data[rows[ok], cols[ok]]
    good = ok & (raw != NODATA)
    vals[good] = raw[good].astype("float32") * scale

    col = PRODUCTS[product]["col"]
    df = pd.DataFrame(
        {
            "osm_id": seg["osm_id"].values,
            "length_m": seg["length_m"].values,
            "in_boundary": seg["in_boundary"].values,
            col: np.round(vals, 2),
        }
    )
    n_bad = int(df[col].isna().sum())
    if n_bad:
        print(f"[chap] 注意：{n_bad} 段落在网格外或无值（NaN）")
    return df


def summarize(df: pd.DataFrame, product: str) -> None:
    col, label = PRODUCTS[product]["col"], PRODUCTS[product]["label"]
    v = df[col].dropna()
    q = np.percentile(v, [0, 10, 25, 50, 75, 90, 100])
    print(f"\n=== {label} 逐段年均浓度（µg/m³）===")
    print(f"路段数 {len(v):,} / 缺失 {int(df[col].isna().sum()):,}")
    print("min %.1f | p10 %.1f | p25 %.1f | 中位 %.1f | p75 %.1f | p90 %.1f | max %.1f" % tuple(q))
    print(f"极差 {q[-1] - q[0]:.1f}，四分位距 {q[4] - q[2]:.1f}，变异系数 {v.std() / v.mean():.3f}")
    for flag, name in ((True, "市域内"), (False, "市域外")):
        sub = df.loc[df["in_boundary"] == flag, col].dropna()
        if len(sub):
            print(f"  {name}: n={len(sub):,}  中位 {sub.median():.1f}  均值 {sub.mean():.1f}")
    w = df.dropna(subset=[col])
    if w["length_m"].sum():
        print(f"按里程加权均值 {np.average(w[col], weights=w['length_m']):.1f}")


def plot(df: pd.DataFrame, year: int, out_png: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.cm import ScalarMappable

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
    plt.rcParams["axes.unicode_minus"] = False

    seg = gpd.read_file(OUT / "segments.gpkg", layer="segments")[["osm_id", "geometry"]]
    seg = seg.merge(df[["osm_id", "pm25_ugm3", "no2_ugm3"]], on="osm_id", how="left").to_crs(32650)
    palette = ListedColormap(["#1a9850", "#91cf60", "#d9ef8b", "#fee08b", "#fc8d59", "#d73027"])

    panels = [("pm25_ugm3", f"PM2.5 年均 {year}"), ("no2_ugm3", f"NO2 年均 {year}")]
    fig, axes = plt.subplots(1, 2, figsize=(13.6, 6.6), dpi=190)
    for ax, (col, title) in zip(axes, panels):
        v = seg[col].dropna()
        bounds = np.unique(np.percentile(v, np.linspace(0, 100, palette.N + 1)).round(1))
        bounds[0] -= 0.1
        bounds[-1] += 0.1
        norm = BoundaryNorm(bounds, palette.N)
        for i, (lo, hi) in enumerate(zip(bounds[:-1], bounds[1:])):
            sub = seg[(seg[col] >= lo) & (seg[col] <= hi)]
            if len(sub):
                sub.plot(ax=ax, color=palette(i), linewidth=0.28, zorder=2)
        cb = fig.colorbar(ScalarMappable(norm=norm, cmap=palette), ax=ax, shrink=0.62, pad=0.01)
        cb.set_label(f"{title}（µg/m³，CHAP 1 km）", fontsize=8.5)
        cb.ax.tick_params(labelsize=7.5)
        ax.set_title(f"{title}：按分位数分 6 档", fontsize=10.5, pad=8)
        ax.set_axis_off()

    fig.suptitle(
        "逐段空气落到 9.1 万段路上（1 km 网格，CHAP）\n"
        "AQICN 全武汉只有 10 站，3 km 缓冲仅覆盖 12.7% 路段",
        fontsize=11.5,
        y=0.99,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, bbox_inches="tight", facecolor="white")
    print(f"[chap] 图 → {out_png}")


def main() -> int:
    ap = argparse.ArgumentParser(description="CHAP 1 km 污染物 → 逐段浓度")
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--product", choices=["pm25", "no2", "all"], default="all")
    ap.add_argument("--local", type=Path, help="本地 .nc 路径（仅单产品时可用）")
    ap.add_argument("--force", action="store_true", help="强制重新下载")
    ap.add_argument("--plot", action="store_true", help="出分段着色图（需两个产品都算过）")
    args = ap.parse_args()

    warnings.filterwarnings("ignore", category=UserWarning)
    products = ["pm25", "no2"] if args.product == "all" else [args.product]

    merged: pd.DataFrame | None = None
    for p in products:
        nc = args.local or fetch_year(p, args.year, force=args.force)
        df = sample_segments(Path(nc), p)
        df.to_csv(OUT / f"segment_air_{p}.csv", index=False, encoding="utf-8-sig")
        summarize(df, p)
        merged = df if merged is None else merged.merge(
            df[["osm_id", PRODUCTS[p]["col"]]], on="osm_id", how="outer"
        )

    if merged is None:
        return 1
    merged.to_csv(OUT / "segment_air.csv", index=False, encoding="utf-8-sig")
    print(f"\n[chap] 合并表 → {OUT / 'segment_air.csv'}  行={len(merged):,}")

    if args.plot and len(products) == 2:
        plot(merged, args.year, OUTPUT / "air_chap_map.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
