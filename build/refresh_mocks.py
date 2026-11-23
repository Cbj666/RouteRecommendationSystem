"""刷新前端 mock 快照（`frontend/app/src/mocks/*.json`）。

前端 `src/api/client.ts` 在 `VITE_USE_MOCK=1` 时直接读这些文件，
它们必须是**后端真实响应**的拷贝，否则离线演示会显示旧权重/旧分数。

用法（先起后端）：

    .\\.venv\\Scripts\\python.exe -m uvicorn app.api:app --app-dir backend --port 8010

    .\\.venv\\Scripts\\python.exe build\\refresh_mocks.py --base-url http://127.0.0.1:8010
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOCKS = ROOT / "frontend" / "app" / "src" / "mocks"


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def dump(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    feats = payload.get("features")
    extra = f"，{len(feats)} 个要素" if isinstance(feats, list) else ""
    print(f"  {path.relative_to(ROOT)}  {path.stat().st_size / 1024:.0f} KB{extra}")


def main() -> None:
    ap = argparse.ArgumentParser(description="刷新前端 mock 快照")
    ap.add_argument("--base-url", default="http://127.0.0.1:8010")
    ap.add_argument("--limit", type=int, default=1200,
                    help="/api/segments 的返回上限（沿用历史快照的 1200 条，别把 mocks 撑大）")
    ap.add_argument(
        "--fields",
        default="osm_id,fclass,name,length_m,score,grade,s_safety,s_green,s_slope,"
                "s_cross,s_fac",
        help="要保留的字段，逗号分隔（沿用历史快照的字段集）")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    print("[mocks] 拉取 /api/meta …")
    meta = get_json(f"{base}/api/meta")
    dump(MOCKS / "meta.json", meta)
    print(f"       weights = {json.dumps(meta.get('weights'), ensure_ascii=False)}")
    print(f"       grade_bins = {meta.get('grade_bins')}")

    bbox = (meta.get("data") or {}).get("default_segment_bbox")
    if not bbox:
        raise SystemExit("meta 里没有 default_segment_bbox，无法确定 segments 快照范围")
    min_lng, min_lat, max_lng, max_lat = bbox
    print(f"[mocks] 拉取 /api/segments（bbox={bbox}, limit={args.limit}）…")
    query = (f"min_lng={min_lng}&min_lat={min_lat}&max_lng={max_lng}&max_lat={max_lat}"
             f"&limit={args.limit}&fields={args.fields}")
    seg = get_json(f"{base}/api/segments?{query}")
    dump(MOCKS / "segments.json", seg)
    scores = [f["properties"]["score"] for f in seg.get("features", [])
              if f["properties"].get("score") is not None]
    if scores:
        print(f"       score {min(scores):.1f} – {max(scores):.1f}")
    print("[mocks] done")


if __name__ == "__main__":
    main()
