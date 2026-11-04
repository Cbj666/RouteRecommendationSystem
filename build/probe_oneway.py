import sys
import numpy as np
sys.path.insert(0, "backend")
sys.path.insert(0, "build")
from app import running
import demo_routes as dr

g = running.load_or_build()
prefs = {"green": 1.0, "safe": 1.0, "flat": 0.6}
cost = running._cost_matrix(g, running._pref_score(g, prefs))
ne = g.csr_len.nnz
air = {"pm25": np.full(ne, np.nan), "no2": np.full(ne, np.nan)}

print(f"{'target':>8} {'n':>3} {'best_len':>9} {'err%':>6} {'score':>6}  终点≠起点")
for km in [1, 2, 5, 10, 20, 30, 42]:
    lp = dr.one_way(g, cost, air, 114.3547, 30.5342, km * 1000, prefs)
    if not lp:
        print(f"{km:>6} km {0:>3} {'--':>9} {'--':>6} {'--':>6}")
        continue
    b = lp[0]
    err = (b["length_m"] / (km * 1000) - 1) * 100
    print(f"{km:>6} km {len(lp):>3} {b['length_m']:>9.0f} {err:>+6.1f} {b['score']:>6.1f}  {b['nodes'][0] != b['nodes'][-1]}")
