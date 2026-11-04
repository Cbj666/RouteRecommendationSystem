"""按标题核验指定的关键文献（OpenAlex），输出元数据 + OA 状态。"""

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

ANCHORS = [
    ("Pikora 2003 步行/骑行环境四要素",
     "Developing a framework for assessment of the environmental determinants of walking and cycling"),
    ("Frank 2010 walkability index",
     "The development of a walkability index: application to the Neighborhood Quality of Life Study"),
    ("Minetti 2002 坡度能量代价",
     "Energy cost of walking and running at extreme uphill and downhill slopes"),
    ("Luo & Wang 2003 2SFCA",
     "Measures of spatial accessibility to health care in a GIS environment"),
    ("Tainio 2016 污染 vs 运动收益",
     "Can air pollution negate the health benefits of cycling and walking"),
    ("Thompson Coon 2011 户外绿色运动",
     "Does participating in physical activity in outdoor natural environments have a greater effect on physical and mental wellbeing"),
    ("Abraham 2013 替代路径",
     "Alternative routes in road networks"),
    ("Frank 2006 步行指数",
     "Many pathways from land use to health: associations between neighborhood walkability and active transportation"),
    ("Sallis 2009 环境与活动综述",
     "Neighborhood built environment and income: examining multiple health outcomes"),
    ("Mekuria 2012 低压力骑行网络",
     "Low-Stress Bicycling and Network Connectivity"),
]


def search(title: str) -> dict | None:
    params = {
        "filter": f"title.search:{title}",
        "per-page": "3",
        "mailto": MAIL,
    }
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                results = json.load(r).get("results", [])
            return results[0] if results else None
        except Exception:  # noqa: BLE001
            time.sleep(2 + 2 * attempt)
    return None


def main() -> None:
    rows = []
    for label, title in ANCHORS:
        w = search(title)
        time.sleep(0.4)
        if not w:
            rows.append({"label": label, "found": "N", "title": title, "year": "", "journal": "",
                         "doi": "", "cites": "", "oa": "", "oa_url": "", "authors": ""})
            print("MISS", label)
            continue
        src = (w.get("primary_location") or {}).get("source") or {}
        oa = w.get("open_access") or {}
        auths = [a["author"]["display_name"] for a in w.get("authorships", [])[:3]]
        rows.append({
            "label": label,
            "found": "Y",
            "title": w.get("title") or "",
            "year": w.get("publication_year") or "",
            "journal": src.get("display_name") or "",
            "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
            "cites": w.get("cited_by_count") or 0,
            "oa": "Y" if oa.get("is_oa") else "N",
            "oa_url": oa.get("oa_url") or "",
            "authors": "; ".join(auths),
        })
        print("OK  ", label, "|", (w.get("title") or "")[:60], "|", w.get("publication_year"), "| OA", oa.get("is_oa"))

    csv_path = OUT / "anchors.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("→", csv_path)


if __name__ == "__main__":
    main()
