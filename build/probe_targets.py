import sys, time
sys.path.insert(0, "backend")
from app import running

g = running.load_or_build()
prefs = {"green": 1.0, "safe": 1.0, "flat": 0.6}
print(f"{'target':>8} {'n':>3} {'best_len':>9} {'err%':>6} {'score':>6} {'sec':>5}  闭合?")
for km in [1, 2, 3, 5, 8, 10, 15, 21, 30, 42]:
    t0 = time.time()
    lp = running.generate_loops(g, 114.3547, 30.5342, km * 1000, prefs, max_candidates=8)
    dt = time.time() - t0
    if not lp:
        print(f"{km:>6} km {0:>3} {'--':>9} {'--':>6} {'--':>6} {dt:>5.2f}  --")
        continue
    b = lp[0]
    closed = b["nodes"][0] == b["nodes"][-1]
    err = (b["length_m"] / (km * 1000) - 1) * 100
    print(f"{km:>6} km {len(lp):>3} {b['length_m']:>9.0f} {err:>+6.1f} {b['score']:>6.1f} {dt:>5.2f}  {closed}")
