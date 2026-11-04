"""逐月抓 CHAP PM2.5（1 km，M1K），算武汉全年 12 个月的月均曲线。

用法：
    .\\.venv\\Scripts\\python.exe backend\\scripts\\build_air_monthly.py
    .\\.venv\\Scripts\\python.exe backend\\scripts\\build_air_monthly.py --year 2024 --force

产物：
    data/raw/chap/CHAP_PM2.5_M1K_{YYYYMM}_V4.nc          原始月网格（约 6–8 MB / 月）
    data/processed/running/v1/air_monthly_wuhan.csv      全市按月统计
    data/processed/running/v1/segment_air_monthly.csv    91,203 段 × 12 个月
    data/output/running/v1/demo/fig_air_season12.png     12 个月曲线
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "chap"
OUT = ROOT / "data" / "processed" / "running" / "v1"
FIG = ROOT / "data" / "output" / "running" / "v1" / "demo"

RECORD = 21770406           # ChinaHighPM2.5 V4, 2022–2025
TMPL = "CHAP_PM2.5_M1K_{ym}_V4.nc"
NODATA = 65535
SCALE = 0.1
BBOX = (113.70, 30.00, 115.10, 31.40)   # 武汉全市外接矩形
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _readable(path: Path) -> bool:
    """下载中断会留下「大小像样但读不了」的文件，必须验证内容。"""
    try:
        with rasterio.open(path) as src:
            _ = src.read(1, window=((0, 8), (0, 8)))
        return True
    except Exception:                                  # noqa: BLE001
        return False


def fetch_month(ym: str, force: bool = False) -> Path:
    name = TMPL.format(ym=ym)
    dst = RAW / name
    if dst.exists() and not force and dst.stat().st_size > 1e6 and _readable(dst):
        print(f"[air] 复用 {name}（{dst.stat().st_size / 1e6:.1f} MB）")
        return dst
    if dst.exists():
        print(f"[air] {name} 不可用，重新下载")
        dst.unlink(missing_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    url = f"https://zenodo.org/api/records/{RECORD}/files/{name}/content"
    for attempt in range(1, 4):
        try:
            print(f"[air] 下载 {name}（第 {attempt} 次）← zenodo:{RECORD}")
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            tmp = dst.with_suffix(".part")
            n_bytes = 0
            with urllib.request.urlopen(req, timeout=300) as r:
                want = r.headers.get("Content-Length")
                with open(tmp, "wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
                        n_bytes += len(chunk)
            if want is not None and int(want) != n_bytes:
                raise IOError(f"传输不完整：{n_bytes} / {want} 字节")
            if not _readable(tmp):
                raise IOError("下载完成但 HDF5 读不了（文件不完整）")
            tmp.replace(dst)
            print(f"[air] 完成 {dst.stat().st_size / 1e6:.1f} MB")
            return dst
        except Exception as exc:                      # noqa: BLE001
            print(f"[air] 失败：{exc!r}")
            Path(tmp).unlink(missing_ok=True)
            if attempt == 3:
                raise
    raise RuntimeError("unreachable")


def read_bbox(nc_path: Path) -> np.ndarray:
    """读武汉 bbox 内的像元值（µg/m³），去掉 nodata。"""
    with rasterio.open(nc_path) as src:
        win = src.window(BBOX[0], BBOX[1], BBOX[2], BBOX[3])
        raw = src.read(1, window=win, boundless=True, fill_value=NODATA)
    vals = raw[raw != NODATA].astype("float32") * SCALE
    return vals


def sample_segments(nc_path: Path, seg: gpd.GeoDataFrame) -> np.ndarray:
    """路段中点取格值。"""
    with rasterio.open(nc_path) as src:
        win = src.window(BBOX[0] - 0.05, BBOX[1] - 0.05, BBOX[2] + 0.05, BBOX[3] + 0.05)
        data = src.read(1, window=win, boundless=True, fill_value=NODATA)
        tr = src.window_transform(win)
    lon = seg["mid_x"].to_numpy()
    lat = seg["mid_y"].to_numpy()
    cols = np.floor((lon - tr.c) / tr.a).astype(np.int64)
    rows = np.floor((lat - tr.f) / tr.e).astype(np.int64)
    ok = (rows >= 0) & (rows < data.shape[0]) & (cols >= 0) & (cols < data.shape[1])
    raw = np.zeros(len(seg), dtype="uint16")
    raw[ok] = data[rows[ok], cols[ok]]
    out = np.full(len(seg), np.nan, dtype="float32")
    good = ok & (raw != NODATA)
    out[good] = raw[good].astype("float32") * SCALE
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    months = [f"{args.year}{m:02d}" for m in range(1, 13)]
    seg = gpd.read_file(OUT / "segments.gpkg", layer="segments")[["osm_id", "geometry"]]
    seg = seg.to_crs(4326)
    mid = seg.geometry.interpolate(0.5, normalized=True)
    seg = seg.assign(mid_x=np.asarray(mid.x), mid_y=np.asarray(mid.y))

    rows, cols = [], {}
    for ym in months:
        nc = fetch_month(ym, force=args.force)
        vals = read_bbox(nc)
        seg_vals = sample_segments(nc, seg)
        cols[ym] = seg_vals
        rows.append(
            {
                "month": ym,
                "pm25_median": round(float(np.median(vals)), 2),
                "pm25_p10": round(float(np.percentile(vals, 10)), 2),
                "pm25_p90": round(float(np.percentile(vals, 90)), 2),
                "pm25_mean": round(float(vals.mean()), 2),
                "pm25_p95": round(float(np.percentile(vals, 95)), 2),
                "seg_nan": int(np.isnan(seg_vals).sum()),
                "seg_median": round(float(np.nanmedian(seg_vals)), 2),
            }
        )
        print(f"[air] {ym}: 全市中位 {rows[-1]['pm25_median']:.1f}  "
              f"p10 {rows[-1]['pm25_p10']:.1f}  p90 {rows[-1]['pm25_p90']:.1f}")

    stat = pd.DataFrame(rows)
    stat.to_csv(OUT / "air_monthly_wuhan.csv", index=False, encoding="utf-8-sig")

    seg_df = pd.DataFrame({"osm_id": seg["osm_id"].to_numpy()})
    for ym, v in cols.items():
        seg_df[f"pm25_{ym}"] = np.round(v, 2)
    seg_df.to_csv(OUT / "segment_air_monthly.csv", index=False, encoding="utf-8-sig")

    ratio = float(stat["pm25_median"].max() / stat["pm25_median"].min())
    peak = stat.loc[stat["pm25_median"].idxmax(), "month"]
    low = stat.loc[stat["pm25_median"].idxmin(), "month"]
    summary = {
        "year": args.year,
        "months": len(stat),
        "ratio_max_min": round(ratio, 2),
        "peak_month": peak,
        "low_month": low,
        "annual_median": round(float(stat["pm25_median"].median()), 2),
    }
    (OUT / "air_monthly_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    plot(stat, args.year)
    return 0


def plot(stat: pd.DataFrame, year: int) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
    plt.rcParams["axes.unicode_minus"] = False

    GREEN, MID, AMBER, RED = "#1a5c46", "#4f9d7d", "#c0762a", "#b03a2e"
    INK, GRAY = "#1f2a26", "#8a9a93"

    fig, ax = plt.subplots(figsize=(10.6, 4.9), dpi=190)
    x = np.arange(len(stat))
    ax.fill_between(x, stat["pm25_p10"], stat["pm25_p90"], color="#dbe9e1", zorder=2)
    ax.plot(x, stat["pm25_median"], color=GREEN, linewidth=2.2, marker="o",
            markersize=5, zorder=3)
    for xi, v in zip(x, stat["pm25_median"]):
        ax.text(xi, v + 3.2, f"{v:.0f}", ha="center", fontsize=8.6, color=INK)
    ax.axhline(15, color=MID, linewidth=1.1, linestyle=(0, (4, 3)))
    ax.text(len(stat) - 0.35, 11.6, "WHO 年均指导值 15", fontsize=8.4, color="#3d7a5e", ha="right")
    ax.axhline(35, color=RED, linewidth=1.1, linestyle=(0, (4, 3)))
    ax.text(len(stat) - 0.35, 31.6, "国标二级年均 35", fontsize=8.4, color=RED, ha="right")

    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(m[4:])}月" for m in stat["month"]], fontsize=9.5)
    ax.set_ylim(0, 78)
    ax.set_ylabel("PM2.5，µg/m³", fontsize=10, color="#444")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#d8d8d8")
    ax.grid(axis="y", color="#ececec", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors="#555", labelsize=9.5)
    ax.set_title(f"{year} 年武汉全市 PM2.5 月均（CHAP 1 km 网格，阴影 = 全市 p10–p90）",
                 fontsize=12.5, color=INK, fontweight="bold", loc="left", pad=12)

    i_hi = int(stat["pm25_median"].idxmax())
    i_lo = int(stat["pm25_median"].idxmin())
    r = stat["pm25_median"].iloc[i_hi] / stat["pm25_median"].iloc[i_lo]
    ax.text(0.52, 0.70, f"{r:.1f}×", transform=ax.transAxes, fontsize=22, color=INK,
            fontweight="bold", ha="left", va="center")
    ax.text(0.52, 0.62, f"最高 {stat['pm25_median'].iloc[i_hi]:.0f}（{int(stat['month'].iloc[i_hi][4:])} 月）"
                        f" / 最低 {stat['pm25_median'].iloc[i_lo]:.0f}（{int(stat['month'].iloc[i_lo][4:])} 月）",
            transform=ax.transAxes, fontsize=9.6, color="#4a4a4a", ha="left", va="center")
    ax.plot([i_hi, i_hi], [stat["pm25_median"].iloc[i_hi], 0], color=INK, linewidth=0.8,
            linestyle=(0, (2, 3)), alpha=0.45, zorder=1)
    ax.plot([i_lo, i_lo], [stat["pm25_median"].iloc[i_lo], 0], color=INK, linewidth=0.8,
            linestyle=(0, (2, 3)), alpha=0.45, zorder=1)

    fig.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    p = FIG / "fig_air_season12.png"
    fig.savefig(p, facecolor="white")
    plt.close(fig)
    print(f"[air] 图 → {p}")


if __name__ == "__main__":
    raise SystemExit(main())
