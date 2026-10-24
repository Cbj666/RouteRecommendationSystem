# -*- coding: utf-8 -*-
"""Derive per-segment slope for the walk network from the SRTM 1" DEM.

Inputs
    data/raw/dem/skadi/N{lat}E{lon}.hgt   9 tiles, downloaded by fetch_dem.py
    data/processed/v1/osm_walk_roads.gpkg layer walk_roads (91,203 segments)

Output
    data/processed/running/v1/segment_slope.csv
        osm_id, length_m, slope_mean_pct, slope_max_pct, elev_gain_m,
        elev_min_m, elev_max_m

Method
    SRTM at 30 m in a city carries roughly ±4 m of noise from buildings and
    canopy, so differencing neighbouring samples reports 5–7 % slopes on flat
    ground. Instead we
      1. mosaic the tiles into one array covering the Wuhan bbox,
      2. smooth it with a Gaussian (sigma ≈ 150 m) to remove that noise,
      3. take the gradient of the smoothed surface in metres/metre,
      4. average |gradient| along each OSM segment (length-weighted).
    This gives every segment a value, including short ones, and the result is
    a terrain trend rather than a per-block reading.
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely
from scipy.ndimage import gaussian_filter

ROOT = Path(__file__).resolve().parents[2]
DEM = ROOT / "data" / "raw" / "dem" / "skadi"
V1 = ROOT / "data" / "processed" / "v1"
OUT = ROOT / "data" / "processed" / "running" / "v1"
N = 3601                 # samples per side of a 1" SRTM tile
SMOOTH_SIGMA_M = 150.0   # metres; removes SRTM urban noise
SLOPE_CAP = 30.0         # %, clip DEM artefacts


class Mosaic:
    """Smoothed DEM mosaic covering a lon/lat bbox, with gradient access."""

    def __init__(self, folder: Path, bbox: tuple[float, float, float, float],
                 sigma_m: float = SMOOTH_SIGMA_M):
        lon0, lat0, lon1, lat1 = bbox
        self.lon0 = np.floor(lon0)
        self.lat1 = np.ceil(lat1)
        self.lon_min = lon0
        self.lon_max = lon1
        self.lat_min = lat0
        self.lat_max = lat1

        self.rows = int(round((self.lat1 - np.floor(lat0)) * (N - 1)))
        self.cols = int(round((np.ceil(lon1) - self.lon0) * (N - 1)))
        z = np.full((self.rows, self.cols), np.nan, dtype=np.float32)

        for p in sorted(folder.glob("N*E*.hgt")):
            tlat, tlon = int(p.stem[1:3]), int(p.stem[4:7])
            r0 = int(round((self.lat1 - (tlat + 1)) * (N - 1)))
            c0 = int(round((tlon - self.lon0) * (N - 1)))
            arr = np.fromfile(p, dtype=">i2").reshape(N, N).astype(np.float32)
            arr[arr < -1000] = np.nan
            r1, c1 = r0 + N, c0 + N
            tr = slice(max(r0, 0), min(r1, self.rows))
            tc = slice(max(c0, 0), min(c1, self.cols))
            sr = slice(tr.start - r0, tr.stop - r0)
            sc = slice(tc.start - c0, tc.stop - c0)
            z[tr, tc] = arr[sr, sc]

        # fill voids by nearest valid value, then smooth
        if np.isnan(z).any():
            from scipy.ndimage import distance_transform_edt

            idx = distance_transform_edt(np.isnan(z), return_distances=False,
                                         return_indices=True)
            z = z[tuple(idx)]
        cell_m = 30.87  # 1 arc-second at ~30.5°N
        sigma_cells = max(sigma_m / cell_m, 1.0)
        zs = gaussian_filter(z, sigma=sigma_cells, mode="nearest")
        self.z = zs
        gy, gx = np.gradient(zs)
        self.gx = gx / (cell_m * np.cos(np.radians(30.5)))   # east-west spacing
        self.gy = gy / cell_m                                  # north-south spacing

    def _index(self, lon: np.ndarray, lat: np.ndarray):
        r = np.rint((self.lat1 - lat) * (N - 1)).astype(int)
        c = np.rint((lon - self.lon0) * (N - 1)).astype(int)
        np.clip(r, 0, self.rows - 1, out=r)
        np.clip(c, 0, self.cols - 1, out=c)
        return r, c

    def slope_pct(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        r, c = self._index(lon, lat)
        grad = np.hypot(self.gx[r, c], self.gy[r, c])
        return grad * 100.0

    def elevation(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        r, c = self._index(lon, lat)
        return self.z[r, c]


def main() -> int:
    if not list(DEM.glob("*.hgt")):
        print("no DEM tiles; run backend/scripts/fetch_dem.py first", file=sys.stderr)
        return 1

    print("[slope] reading walk network ...")
    gdf = pyogrio.read_dataframe(V1 / "osm_walk_roads.gpkg", layer="walk_roads")
    metric = gdf.to_crs(32650)
    bbox = tuple(float(v) for v in gdf.to_crs(4326).total_bounds)

    print(f"[slope] mosaicking DEM for {tuple(round(b, 3) for b in bbox)} ...")
    mos = Mosaic(DEM, bbox)

    rows = []
    geoms = metric.geometry.to_numpy()
    for osm_id, geom in zip(gdf["osm_id"].to_numpy(), geoms):
        xy = np.asarray(shapely.get_coordinates(geom), dtype=np.float64)
        if len(xy) < 2:
            continue
        lonlat = gpd.GeoSeries([shapely.MultiPoint(xy)], crs=32650).to_crs(4326)
        ll = np.asarray(shapely.get_coordinates(lonlat.iloc[0]), dtype=np.float64)
        seg = np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1]))
        total = float(seg.sum())
        if total <= 0:
            continue

        slope = np.clip(mos.slope_pct(ll[:, 0], ll[:, 1]), 0, SLOPE_CAP)
        elev = mos.elevation(ll[:, 0], ll[:, 1])
        # vertex weight = half of the two adjacent segments (endpoints get half a segment)
        vw = np.empty(len(slope), dtype=float)
        vw[0] = seg[0] / 2.0
        vw[-1] = seg[-1] / 2.0
        if len(slope) > 2:
            vw[1:-1] = (seg[:-1] + seg[1:]) / 2.0
        mean_pct = float(np.average(slope, weights=np.clip(vw, 1e-3, None)))
        rows.append(
            (
                int(osm_id),
                round(total, 1),
                round(mean_pct, 2),
                round(float(slope.max()), 2),
                round(float(np.clip(np.diff(elev), 0, None).sum()), 1),
                round(float(np.min(elev)), 1),
                round(float(np.max(elev)), 1),
            )
        )

    out = pd.DataFrame(
        rows,
        columns=[
            "osm_id", "length_m", "slope_mean_pct", "slope_max_pct",
            "elev_gain_m", "elev_min_m", "elev_max_m",
        ],
    )
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "segment_slope.csv"
    out.to_csv(target, index=False)
    print(f"[slope] {len(out):,} segments -> {target.relative_to(ROOT)}")
    q = out["slope_mean_pct"].describe(percentiles=[0.5, 0.9, 0.99])
    print("[slope] mean slope %: " + ", ".join(f"{k}={v:.2f}" for k, v in q.items()))
    print(f"[slope] >3%: {(out['slope_mean_pct'] > 3).sum():,}  "
          f">5%: {(out['slope_mean_pct'] > 5).sum():,}")
    top = out.nlargest(5, "slope_mean_pct")[["osm_id", "length_m", "slope_mean_pct", "elev_gain_m"]]
    print("[slope] steepest:\n" + top.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
