# -*- coding: utf-8 -*-
"""Download the SRTM 1-arcsecond DEM tiles covering Wuhan (no API key needed).

Source: AWS Open Data "elevation-tiles-prod", skadi bucket — public, no
registration, ~30 m resolution (SRTM 1"), void-filled by NASA.

Tiles are 1° x 1° *.hgt* files (3601 x 3601 int16, big-endian, metres).
They land in ``data/raw/dem/skadi/`` which is gitignored (like all raw data).

Run:  .\.venv\\Scripts\\python.exe backend\\scripts\\fetch_dem.py
"""
from __future__ import annotations

import gzip
import math
import shutil
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "dem" / "skadi"
BOUNDARY = ROOT / "data" / "raw" / "boundary" / "武汉市_市.geojson"
BASE = "https://s3.amazonaws.com/elevation-tiles-prod/skadi"
HGT_SIZE = 3601 * 3601 * 2  # int16 per sample


def tiles_for_bbox(bbox: tuple[float, float, float, float]) -> list[str]:
    lon0, lat0, lon1, lat1 = bbox
    out = []
    for lat in range(math.floor(lat0), math.floor(lat1) + 1):
        for lon in range(math.floor(lon0), math.floor(lon1) + 1):
            out.append(f"N{lat:02d}E{lon:03d}")
    return out


def boundary_bbox() -> tuple[float, float, float, float]:
    import geopandas as gpd

    g = gpd.read_file(BOUNDARY).to_crs(4326)
    return tuple(float(v) for v in g.total_bounds)


def fetch(name: str, force: bool = False) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    hgt = RAW / f"{name}.hgt"
    if hgt.exists() and hgt.stat().st_size == HGT_SIZE and not force:
        print(f"  {name}: cached")
        return hgt

    url = f"{BASE}/{name[:3]}/{name}.hgt.gz"
    gz = RAW / f"{name}.hgt.gz"
    t0 = time.time()
    with urllib.request.urlopen(url, timeout=120) as resp, gz.open("wb") as fh:
        shutil.copyfileobj(resp, fh)
    with gzip.open(gz, "rb") as src, hgt.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    gz.unlink(missing_ok=True)
    size = hgt.stat().st_size
    if size != HGT_SIZE:
        raise RuntimeError(f"{name}: unexpected size {size} (want {HGT_SIZE})")
    print(f"  {name}: {size / 1e6:.1f} MB in {time.time() - t0:.1f}s")
    return hgt


def main() -> int:
    bbox = boundary_bbox()
    names = tiles_for_bbox(bbox)
    print(f"bbox {bbox}\n{len(names)} tiles: {' '.join(names)}")
    for n in names:
        try:
            fetch(n)
        except Exception as exc:  # noqa: BLE001
            print(f"  {n}: FAILED {exc}", file=sys.stderr)
            return 1
    total = sum((RAW / f"{n}.hgt").stat().st_size for n in names)
    print(f"\nok: {len(names)} tiles, {total / 1e6:.1f} MB -> {RAW.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
