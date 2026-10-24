# -*- coding: utf-8 -*-
"""Probe: which running/cycling-relevant OSM tags exist in the local Hubei PBF."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import osmium

ROOT = Path(__file__).resolve().parents[1]
PBF = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "raw" / "hubei" / "hubei-261013.osm.pbf"
BBOX = (113.69, 29.97, 115.08, 31.37)  # Wuhan

WAY_TAGS = ["highway", "surface", "lit", "sidewalk", "bicycle", "foot",
            "cycleway", "cycleway:left", "cycleway:right", "maxspeed",
            "lanes", "smoothness", "tracktype", "crossing", "bridge", "tunnel"]
NODE_TAGS = ["highway", "amenity", "leisure", "natural", "sport", "tourism",
             "man_made", "barrier"]


class Probe(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.ways = Counter()
        self.way_tag_vals = {k: Counter() for k in WAY_TAGS}
        self.nodes = Counter()
        self.node_tag_vals = {k: Counter() for k in NODE_TAGS}

    def _in(self, lat, lon):
        return BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]

    def way(self, w):
        if not w.tags:
            return
        if not any(self._in(n.lat, n.lon) for n in w.nodes):
            return
        hw = w.tags.get("highway")
        if not hw:
            return
        self.ways["highway_ways"] += 1
        for k in WAY_TAGS:
            v = w.tags.get(k)
            if v:
                self.way_tag_vals[k][v] += 1
                self.ways[f"{k}_present"] += 1

    def node(self, n):
        if not n.tags or not self._in(n.location.lat, n.location.lon):
            return
        for k in NODE_TAGS:
            v = n.tags.get(k)
            if v:
                self.node_tag_vals[k][v] += 1
                self.nodes[f"{k}_present"] += 1


def main() -> int:
    if not PBF.exists():
        print("missing", PBF, file=sys.stderr)
        return 1
    p = Probe()
    p.apply_file(str(PBF), locations=True)
    print(f"PBF {PBF.name}\n")
    total = p.ways["highway_ways"] or 1
    print(f"highway ways in bbox: {total:,}")
    for k in WAY_TAGS:
        n = p.ways[f"{k}_present"]
        print(f"  {k:<16} {n:>7,}  ({100 * n / total:5.1f}%)")
        for v, c in p.way_tag_vals[k].most_common(6):
            print(f"      {v:<18}{c:>7,}")
    print("\nnode features in bbox:")
    for k in NODE_TAGS:
        n = p.nodes[f"{k}_present"]
        if n:
            print(f"  {k:<10}{n:>8,}  " + ", ".join(f"{v}={c}" for v, c in p.node_tag_vals[k].most_common(6)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
