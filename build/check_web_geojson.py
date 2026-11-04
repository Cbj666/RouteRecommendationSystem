"""校验 web/ 下 GeoJSON：要素数、空几何、字节数。"""
import json
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "data/output/running/v1/web"

for name in ["segments_city.geojson", "segments_arterial.geojson", "water_green.geojson"]:
    p = WEB / name
    d = json.loads(p.read_text(encoding="utf-8"))
    feats = d["features"]
    nulls = sum(1 for f in feats if f["geometry"] is None)
    empties = sum(
        1 for f in feats
        if f["geometry"] is not None and len(f["geometry"]["coordinates"] or []) == 0
    )
    print(f"{name:28s} {len(feats):>6,} 要素  空几何 {nulls:>3}  "
          f"空坐标 {empties:>3}  {p.stat().st_size / 1024 / 1024:5.2f} MB")
