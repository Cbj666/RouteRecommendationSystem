import type { LoopSubScores } from '../types'

export function fmtKm(m: number): string {
  return `${(m / 1000).toFixed(2)} km`
}

export function fmtMinutes(m: number): string {
  return `${Math.round(m)} min`
}

export function fmtPercent(v: number, digits = 0): string {
  return `${(v * 100).toFixed(digits)}%`
}

export function fmtSlope(pct: number): string {
  return `${pct.toFixed(1)}%`
}

export function fmtMeters(m: number): string {
  return `${Math.round(m)} m`
}

export function fmtScore(score: number): string {
  return score.toFixed(1)
}

/**
 * 环线综合分的人话标签。
 * 注意：这不是 segments 的 grade（差/一般/较好/好/很好），
 * 两者口径不同（loops 的 score 是偏好匹配分），见 G3。
 */
export function loopBadge(score: number): string {
  if (score >= 75) return '很适宜'
  if (score >= 65) return '较适宜'
  if (score >= 55) return '一般'
  return '需谨慎'
}

const EMPTY_SUB: LoopSubScores = { s_safety: 0, s_green: 0, s_slope: 0 }

export function parseSub(sub: string | undefined): LoopSubScores {
  if (!sub) return EMPTY_SUB
  try {
    const v = JSON.parse(sub) as Partial<LoopSubScores>
    return {
      s_safety: Number(v.s_safety ?? 0),
      s_green: Number(v.s_green ?? 0),
      s_slope: Number(v.s_slope ?? 0),
    }
  } catch {
    return EMPTY_SUB
  }
}

/** 环线首尾是否同一个点（闭合） */
export function isClosed(coords: [number, number][] | undefined): boolean {
  if (!coords || coords.length < 2) return false
  const a = coords[0]
  const b = coords[coords.length - 1]
  return a[0] === b[0] && a[1] === b[1]
}

/** 两点间球面直线距离（米，Haversine） */
export function haversineMeters(
  lng1: number,
  lat1: number,
  lng2: number,
  lat2: number,
): number {
  const R = 6371000
  const toRad = (deg: number) => (deg * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLng = toRad(lng2 - lng1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}
