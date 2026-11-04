import sys
sys.path.insert(0, "backend")
from app import running

g = running.load_or_build()
prefs = {"green": 1.0, "safe": 1.0, "flat": 0.6}
rows = []
for km in range(1, 43):
    lp = running.generate_loops(g, 114.3547, 30.5342, km * 1000, prefs, max_candidates=8)
    if not lp:
        rows.append((km, 0, None, None)); continue
    b = lp[0]
    rows.append((km, len(lp), b["length_m"], b["score"]))

zero = [r[0] for r in rows if r[1] == 0]
errs = [(r[0], (r[2] / (r[0] * 1000) - 1) * 100) for r in rows if r[2]]
bad = [(k, e) for k, e in errs if abs(e) > 12]
print(f"扫描 1–42 km：无候选 {len(zero)} 个 {zero}")
print(f"长度误差范围 {min(e for _, e in errs):+.1f}% ~ {max(e for _, e in errs):+.1f}%")
print(f"|误差| > 12% 的目标：{[(k, round(e,1)) for k, e in bad]}")
cnt = [r[1] for r in rows if r[1]]
print(f"候选数：最少 {min(cnt)}、中位 {sorted(cnt)[len(cnt)//2]}、最多 {max(cnt)}")
print("逐千米（km: n / 长度误差 / 分）：")
line = []
for km, n, L, sc in rows:
    if n == 0: line.append(f"{km}:0")
    else: line.append(f"{km}:{n}/{L/(km*1000)*100-100:+.0f}%/{sc:.0f}")
print("  " + "  ".join(line[:14]))
print("  " + "  ".join(line[14:28]))
print("  " + "  ".join(line[28:]))
