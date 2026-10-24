# -*- coding: utf-8 -*-
"""Probe: node-level OSM features relevant to running/cycling, in the Wuhan bbox.

Usage: python tools/osm_node_probe.py <path-to.pbf>
(pyosmium cannot open paths with non-ASCII characters on Windows — copy the
PBF to an ASCII path such as D:\\dsh-tmp\\osm\\hubei.osm.pbf first.)
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import osmium

BBOX = (113.69, 29.97, 115.08, 31.37)
KEYS = ["highway", "amenity", "leisure", "natural", "sport", "tourism", "barrier", "man_made"]


class NodeProbe(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.total = 0
        self.vals: dict[str, Counter] = {k: Counter() for k in KEYS}

    def node(self, n):
        if not n.tags:
            return
        lat, lon = n.location.lat, n.location.lon
        if not (BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]):
            return
        self.total += 1
        for k in KEYS:
            v = n.tags.get(k)
            if v:
                self.vals[k][v] += 1


def main() -> int:
    pbf = Path(sys.argv[1])
    p = NodeProbe()
    p.apply_file(str(pbf), locations=True)
    print(f"tagged nodes in bbox: {p.total:,}\n")
    for k in KEYS:
        if not p.vals[k]:
            continue
        print(f"[{k}] {sum(p.vals[k].values()):,}")
        for v, c in p.vals[k].most_common(12):
            print(f"   {v:<22}{c:>8,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
