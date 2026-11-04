"""用 OpenAlex 检索候选文献，输出候选清单（CSV + Markdown）。

只做元数据与摘要检索，不下载 PDF。
"""

from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "lit"
OUT.mkdir(parents=True, exist_ok=True)

MAIL = "research.assistant@outlook.com"
BASE = "https://api.openalex.org/works"

GROUPS = {
    "A_维度": [
        "walkability built environment physical activity",
        "bikeability cycling environment audit tool",
        "energy cost slope running gradient",
        "tree canopy street greenery shade physical activity",
        "personal exposure air pollution running cycling",
    ],
    "B_权重": [
        "analytic hierarchy process weighting walkability",
        "entropy weight TOPSIS composite index evaluation",
        "stated preference route choice cycling attributes",
        "global sensitivity analysis composite indicator weights",
    ],
    "C_路线": [
        "alternative routes penalty shortest path diversity",
        "route recommendation running cycling preference",
        "loop route round trip path planning",
        "scenic route greenway route choice",
        "exposure minimizing route cycling air pollution",
    ],
}


def fetch(query: str, per_page: int = 10) -> list[dict]:
    params = {
        "filter": (
            f"title_and_abstract.search:{query},"
            "from_publication_date:2000-01-01,type:article"
        ),
        "per-page": str(per_page),
        "mailto": MAIL,
    }
    url = BASE + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r).get("results", [])
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 + 2 * attempt)
    raise RuntimeError(f"openalex failed: {last}")


def abstract(inv: dict | None, limit: int = 240) -> str:
    if not inv:
        return ""
    pos: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        for i in idxs:
            pos.append((i, word))
    pos.sort()
    text = " ".join(w for _, w in pos)
    return text[:limit] + ("…" if len(text) > limit else "")


def main() -> None:
    rows: list[dict] = []
    seen: set[str] = set()
    for group, queries in GROUPS.items():
        for q in queries:
            try:
                results = fetch(q)
            except Exception as exc:  # noqa: BLE001
                print("FAIL", q, exc)
                continue
            for w in results:
                key = (w.get("doi") or w.get("id") or "").lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                src = (w.get("primary_location") or {}).get("source") or {}
                oa = w.get("open_access") or {}
                rows.append({
                    "group": group,
                    "query": q,
                    "title": w.get("title") or "",
                    "year": w.get("publication_year") or "",
                    "journal": src.get("display_name") or "",
                    "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
                    "cites": w.get("cited_by_count") or 0,
                    "is_oa": "Y" if oa.get("is_oa") else "N",
                    "oa_url": oa.get("oa_url") or "",
                    "abstract": abstract(w.get("abstract_inverted_index")),
                })
            time.sleep(0.3)

    rows.sort(key=lambda r: (r["group"], -int(r["cites"])))
    csv_path = OUT / "candidates.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    md = ["# 候选文献清单（OpenAlex 检索）", "",
          f"共 {len(rows)} 条，按分组与被引排序。`OA=Y` 表示有开放获取副本。", ""]
    for group in GROUPS:
        sub = [r for r in rows if r["group"] == group]
        md.append(f"## {group}（{len(sub)} 条）")
        md.append("")
        md.append("| 年 | 文献 | 期刊 | 被引 | OA | DOI |")
        md.append("|---:|---|---|---:|:--:|---|")
        for r in sub:
            md.append(f"| {r['year']} | {r['title']} | {r['journal'][:38]} | {r['cites']} | {r['is_oa']} | {r['doi']} |")
        md.append("")
    md_path = OUT / "candidates.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    print("rows", len(rows))
    print("→", csv_path)
    print("→", md_path)


if __name__ == "__main__":
    main()
