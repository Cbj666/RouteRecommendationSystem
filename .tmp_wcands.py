# -*- coding: utf-8 -*-
"""Scratch: evaluate hand-designed weight candidates (sum = 1.0)."""
import geopandas as gpd
import numpy as np
from scipy.stats import spearmanr

KEYS = ["safety", "green", "slope", "cross", "fac", "air"]
g = gpd.read_file(
    "data/processed/running/v1/segments.gpkg",
    layer="segments",
    columns=[f"s_{k}" for k in KEYS] + ["fclass", "in_boundary"],
)
S = g[[f"s_{k}" for k in KEYS]].to_numpy(float)
base = S @ np.array([.25, .25, .15, .10, .05, .15]) / 0.95
top_base = set(np.argsort(-base)[: len(base) // 10])


def rep(name, w):
    w = np.asarray(w, float)
    w = w / w.sum()
    s = np.round(S @ w, 1)
    p = np.percentile(s, [10, 25, 50, 75, 90])
    gr = np.histogram(s, [0, 40, 55, 70, 85, 100])[0] / len(s) * 100
    rho = spearmanr(base, s).statistic
    top = set(np.argsort(-s)[: len(s) // 10])
    ov = len(top & top_base) / len(top_base)
    ent = -np.sum([(x / 100) * np.log(x / 100) for x in gr if x > 0]) / np.log(5)
    print(f"{name:10s} " + " ".join(f"{k[:2]}={v:.2f}" for k, v in zip(KEYS, w))
          + f" | mean {s.mean():5.1f} std {s.std():5.2f} cv {s.std()/s.mean():.3f}"
          f" iqr {p[3]-p[1]:5.1f} p10-90 {p[4]-p[0]:5.1f} hi70 {100*(s>=70).mean():4.1f}%"
          f" lo40 {100*(s<40).mean():4.1f}% H {ent:.2f} rho {rho:.3f} top {ov:.2f}")
    print(f"           grades 差{gr[0]:5.1f} 一般{gr[1]:5.1f} 较好{gr[2]:5.1f} "
          f"好{gr[3]:5.1f} 很好{gr[4]:5.1f}")
    # face validity: mean score by road class (expect footway/path > residential > primary)
    df = g.assign(s=s)
    m = df[df.in_boundary == True].groupby("fclass")["s"].mean()
    keep = ["footway", "path", "cycleway", "residential", "tertiary", "secondary", "primary", "trunk"]
    print("           byclass " + " ".join(f"{k[:5]}={m.get(k, np.nan):.0f}" for k in keep))
    return s


rep("v1_asis", [.25, .25, .15, .10, .05, .15])
rep("v1_norm", [.25, .25, .15, .10, .05, .15])
print()
rep("A_light", [.27, .25, .15, .12, .06, .15])
rep("B_mid", [.30, .24, .13, .15, .08, .10])
rep("B2_mid", [.30, .25, .14, .13, .07, .11])
rep("C_strong", [.36, .22, .10, .16, .08, .08])
rep("D_extreme", [.42, .21, .08, .14, .07, .08])
