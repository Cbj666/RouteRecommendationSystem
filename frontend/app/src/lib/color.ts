/**
 * 慢跑适宜性色阶：与 matplotlib 出图 / PPT / reference 一致。
 * t = clip((score - 30) / 42, 0, 1)
 */
export const STOPS: ReadonlyArray<readonly [number, string]> = [
  [0, '#d94f4f'],
  [0.25, '#e8a33d'],
  [0.5, '#8fbf6a'],
  [0.75, '#2e7a5d'],
  [1, '#15503c'],
]

function channel(hex: string, i: number): number {
  return parseInt(hex.slice(1 + 2 * i, 3 + 2 * i), 16)
}

/** 返回 `rgb(r,g,b)`，与 reference 的字符串逐字一致（便于按颜色分桶） */
export function ramp(t: number): string {
  const x = Math.max(0, Math.min(1, t))
  for (let i = 1; i < STOPS.length; i++) {
    const [t0, c0] = STOPS[i - 1]
    const [t1, c1] = STOPS[i]
    if (x <= t1) {
      const k = (x - t0) / (t1 - t0)
      const p = (a: number) => channel(c0, a) * (1 - k) + channel(c1, a) * k
      return `rgb(${p(0) | 0},${p(1) | 0},${p(2) | 0})`
    }
  }
  return STOPS[STOPS.length - 1][1]
}

export function segmentColor(score: number): string {
  return ramp((score - 30) / 42)
}
