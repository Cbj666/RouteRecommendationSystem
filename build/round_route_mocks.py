"""把 mocks/loops_*.json 的浮点数收敛到合理精度（体积更小、也比 0.5759999 好看）。"""

from __future__ import annotations

import json
from pathlib import Path

MOCKS = Path(__file__).resolve().parents[1] / "frontend" / "app" / "src" / "mocks"

ROUND = {
    "length_m": 1,
    "minutes": 1,
    "score": 1,
    "tree_share": 4,
    "slope_mean_pct": 2,
    "facility_m": 0,
    "origin_snap_m": 1,
}


def main() -> None:
    for p in sorted(MOCKS.glob("loops_*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        for feat in d["features"]:
            props = feat["properties"]
            for k, nd in ROUND.items():
                if k in props and isinstance(props[k], (int, float)):
                    props[k] = round(float(props[k]), nd)
                    if nd == 0:
                        props[k] = int(props[k])
            feat["geometry"]["coordinates"] = [
                [round(x, 6), round(y, 6)] for x, y in feat["geometry"]["coordinates"]
            ]
        p.write_text(
            json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        print(f"  {p.name:26s} {p.stat().st_size / 1024:6.1f} KB  {len(d['features'])} 条")


if __name__ == "__main__":
    main()
