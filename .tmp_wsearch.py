# -*- coding: utf-8 -*-
"""Scratch: random-search weight vectors for higher score discrimination."""
import geopandas as gpd
import numpy as np

RUN = "data/processed/running/v1/segments.gpkg"
KEYS = ["safety", "green", "slope", "cross", "fac", "air"]
COLS = [f"s_{k}" for k in KEYS]

g = gpd.read_file(RUN, layer="segments", columns=COLS)
S = g[[c for c in COLS]].to_numpy(np.float32)
base = S @ np.array([.25, .25, .15, .10, .05, .15], np.float32) / 0.95

rng = np.random.default_rng(0)
sub = rng.choice(len(S), 25000, replace=False)
Ss = S[sub]


def draw(n, minw, alpha):
    d = rng.dirichlet(np.ones(6) * alpha, size=n)
    return minw + (1 - 6 * minw) * d


def evaluate(W, X):
    """W (n,6) x X (m,6) -> metrics arrays."""
    out = []
    for i in range(0, len(W), 4000):
        w = W[i:i + 4000]
        s = X @ w.T                      # (m, n_chunk)
        p10, p25, p50, p75, p90 = np.percentile(s, [10, 25, 50, 75, 90], axis=0)
        mean = s.mean(0)
        std = s.std(0)
        hi = (s >= 70).mean(0) * 100
        # Pearson corr with baseline (proxy for rank stability)
        sb = base[sub] if X is Ss else base
        sb = sb - sb.mean()
        sc = s - mean
        rho = (sc * sb[:, None]).sum(0) / (np.sqrt((sc ** 2).sum(0)) * np.sqrt((sb ** 2).sum()))
        out.append(np.column_stack([mean, std, p75 - p25, p90 - p10, hi, rho,
                                    p10, p50, p90]))
    return np.vstack(out)


def show(w, label="", full=True):
    s = (S @ w if full else Ss @ w)
    p = np.percentile(s, [10, 25, 50, 75, 90])
    gr = np.histogram(s, [0, 40, 55, 70, 85, 100])[0] / len(s) * 100
    print(f"{label:22s} w={np.round(w, 4)} sum={w.sum():.4f} mean={s.mean():5.1f} "
          f"std={s.std():5.2f} iqr={p[3]-p[1]:5.1f} p10-90={p[4]-p[0]:5.1f} "
          f"hi70={100*(s>=70).mean():4.1f}% lo40={100*(s<40).mean():4.1f}% "
          f"grades={np.round(gr,1)}")


show(np.array([.25, .25, .15, .10, .05, .15]) / 0.95, "v1_norm")

for minw, alpha in [(0.05, 1.2), (0.06, 1.2), (0.08, 1.2), (0.05, 0.8)]:
    W = draw(60000, minw, alpha)
    M = evaluate(W, Ss)
    mean, std, iqr, span, hi, rho = M[:, 0], M[:, 1], M[:, 2], M[:, 3], M[:, 4], M[:, 5]
    ok = (mean <= 57.5) & (hi >= 5) & (hi <= 10) & (rho >= 0.93) & (W[:, 0] >= 0.18) & (W[:, 1] >= 0.18)
    J = std + 0.40 * iqr / 10 + 0.30 * span / 10
    J = np.where(ok, J, -np.inf)
    order = np.argsort(-J)[:6]
    print(f"\n--- minw={minw} alpha={alpha}: {ok.sum()} feasible of {len(W)}")
    for idx in order:
        show(W[idx], f"cand#{idx}", full=True)
        print(f"    subsample metrics: mean={mean[idx]:.1f} std={std[idx]:.2f} "
              f"iqr={iqr[idx]:.1f} span={span[idx]:.1f} hi={hi[idx]:.1f} rho={rho[idx]:.3f}")
