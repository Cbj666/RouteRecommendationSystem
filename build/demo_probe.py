import sys, time, json
sys.path.insert(0, "backend")
import numpy as np
from scipy.sparse.csgraph import dijkstra
from app import running

t0 = time.time()
g = running.load_or_build()
print("graph", g.n, "edges", g.csr_len.nnz, "load %.1fs" % (time.time()-t0))
print("edge_attr keys", list(g.edge_attr), "subs", list(g.subs))

t = time.time()
dl = dijkstra(g.csr_len, directed=True, indices=0)
print("dijkstra %.2fs" % (time.time()-t))

o = g.nearest(114.3547, 30.5342)
print("nearest", o)

for tgt in (5000, 10000):
    t = time.time()
    lp = running.generate_loops(g, 114.3547, 30.5342, target_m=tgt)
    print(tgt, "loops", len(lp), "%.1fs" % (time.time()-t),
          [(x["length_m"], x["score"]) for x in lp[:3]])

t = time.time()
lp42 = running.generate_loops(g, 114.3547, 30.5342, target_m=42195, max_candidates=8)
print("42195 ->", len(lp42), "%.1fs" % (time.time()-t))
for x in lp42[:5]:
    print("  ", x["length_m"], x["minutes"], x["score"], x["sub"])
