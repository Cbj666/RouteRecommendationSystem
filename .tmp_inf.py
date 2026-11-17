# -*- coding: utf-8 -*-
import json
from pathlib import Path

import geopandas as gpd
import numpy as np

RUN = Path("data/processed/running/v1")
gdf = gpd.read_file(RUN / "segments.gpkg", layer="segments")
for col in gdf.select_dtypes(include=[np.number]).columns:
    s = gdf[col]
    n_inf = int(np.isinf(s).sum())
    if n_inf:
        print("INF", col, n_inf, "min", s.min(), "max", s.max())
print("d_green max", gdf.d_green_m.max(), "d_water max", gdf.d_water_m.max())
sub = gdf[gdf.osm_id == gdf.osm_id.iloc[0]]
print(sub.to_json(drop_id=True)[:500])
empty = gdf.cx[0:0.01, 0:0.01]
print("empty", len(empty), empty.to_json(drop_id=True))
