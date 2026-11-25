/**
 * 热点地图的 mock 兜底网格（真实数据走 /api/hotspot）。
 *
 * 真实数据由 `backend/scripts/build_hotspot_grid.py` 生成全城 2 km 网格，
 * 写入 `data/output/running/v1/hotspot/grid.json`，再由 `/api/hotspot`
 * 提供；mock 模式（VITE_USE_MOCK 未设或不为 0）没有后端，这里用 25×20 的
 * 都市区合成格把页面结构、交互与视觉跑通，字段名与真实响应保持一致。
 */
import type { HotspotCell, HotspotPayload } from '../types'

export type { HotspotCell, HotspotPayload } from '../types'

export const HOTSPOT_SOURCE_NOTE = '2 km 网格 · 都市区示例 · mock 模式'

const CELL_W = 0.0208
const CELL_H = 0.018
const GRADE_BINS = [35, 50, 65, 80]
const GRADE_LABELS = ['差', '一般', '较好', '好', '很好']

interface Anchor {
  name: string
  lng: number
  lat: number
  score: number
  hotspot: boolean
}

const ANCHORS: Anchor[] = [
  { name: '东湖磨山', lng: 114.415, lat: 30.555, score: 78, hotspot: true },
  { name: '东湖绿道', lng: 114.435, lat: 30.575, score: 76, hotspot: true },
  { name: '武汉大学', lng: 114.355, lat: 30.535, score: 72, hotspot: true },
  { name: '沙湖', lng: 114.335, lat: 30.575, score: 68, hotspot: false },
  { name: '光谷广场', lng: 114.400, lat: 30.505, score: 66, hotspot: false },
  { name: '南湖', lng: 114.340, lat: 30.490, score: 64, hotspot: false },
  { name: '汉口江滩', lng: 114.295, lat: 30.590, score: 61, hotspot: false },
  { name: '青山江滩', lng: 114.385, lat: 30.620, score: 58, hotspot: false },
  { name: '汤逊湖', lng: 114.380, lat: 30.450, score: 60, hotspot: false },
  { name: '后官湖', lng: 114.250, lat: 30.500, score: 57, hotspot: false },
]

function clamp(value: number, low = 0, high = 100): number {
  return Math.max(low, Math.min(high, value))
}

function gradeOf(score: number): string {
  const index = GRADE_BINS.findIndex((boundary) => score <= boundary)
  return GRADE_LABELS[index < 0 ? GRADE_LABELS.length - 1 : index]
}

function direction(row: number, col: number): string {
  const ns = row < 0 ? '北' : row > 0 ? '南' : ''
  const ew = col < 0 ? '西' : col > 0 ? '东' : ''
  return `${ns}${ew}`
}

function offset(anchorIndex: number, row: number, col: number, dim: number): number {
  return (((anchorIndex + 3) * 17 + (row + 2) * 7 + (col + 2) * 11 + dim * 13) % 13) - 6
}

/** 都市区 bbox 与 1 km 网格：覆盖东湖、武大、光谷、汉口江滩与青山江滩。 */
const LON0 = 114.24
const LAT0 = 30.45
const COLS = 25
const ROWS = 20

function nearestAnchor(lng: number, lat: number): { anchor: Anchor; index: number; distance: number } {
  let best = { anchor: ANCHORS[0], index: 0, distance: Number.POSITIVE_INFINITY }
  for (const [index, anchor] of ANCHORS.entries()) {
    const dx = (lng - anchor.lng) * 95.5
    const dy = (lat - anchor.lat) * 111
    const distance = Math.hypot(dx, dy)
    if (distance < best.distance) best = { anchor, index, distance }
  }
  return best
}

const cells: HotspotCell[] = []

for (let row = 0; row < ROWS; row++) {
  for (let col = 0; col < COLS; col++) {
    const lng = Number((LON0 + (col + 0.5) * CELL_W).toFixed(6))
    const lat = Number((LAT0 + (row + 0.5) * CELL_H).toFixed(6))
    const { anchor, index: anchorIndex, distance } = nearestAnchor(lng, lat)
    const wave = Math.sin((col + 1) * 0.9 + (row + 1) * 0.7) * 1.8
    const noise = offset(anchorIndex, row, col, 0) * 0.36
    const score = clamp(
      42 + (anchor.score - 42) * Math.exp(-distance / 2.2) + wave + noise,
      30,
      92,
    )
    const hotspot = score >= 66
    const id = `H-${row + 1}-${col + 1}`
    const suffix = direction(row - ROWS / 2, col - COLS / 2)

    cells.push({
      id,
      name: distance < 1.2 ? anchor.name : `${anchor.name}${suffix}`,
      cluster: anchor.name,
      lng,
      lat,
      widthLng: CELL_W,
      heightLat: CELL_H,
      score: Number(score.toFixed(1)),
      grade: gradeOf(score),
      rank: 0,
      nSeg: 2 + ((row * 7 + col * 11) % 10),
      lenM: 520 + ((row * 431 + col * 287 + 163) % 3200),
      isHotspot: hotspot,
      subs: {
        s_safety: Number(clamp(score + offset(anchorIndex, row, col, 1)).toFixed(1)),
        s_green: Number(clamp(score + 4 + offset(anchorIndex, row, col, 2)).toFixed(1)),
        s_slope: Number(clamp(score + 12 + offset(anchorIndex, row, col, 3)).toFixed(1)),
        s_cross: Number(clamp(score - 2 + offset(anchorIndex, row, col, 4)).toFixed(1)),
        s_fac: Number(clamp(score - 5 + offset(anchorIndex, row, col, 5)).toFixed(1)),
        s_air: Number(clamp(score - 1 + offset(anchorIndex, row, col, 6)).toFixed(1)),
      },
    })
  }
}

cells.sort((a, b) => b.score - a.score)
for (const [index, cell] of cells.entries()) cell.rank = index + 1

export const HOTSPOT_CELLS: HotspotCell[] = cells

/** mock 模式下的 /api/hotspot 等价响应（都市区 500 格合成数据） */
export const HOTSPOT_MOCK: HotspotPayload = {
  generated_at: new Date(0).toISOString(),
  source: 'src/mocks/hotspot.ts',
  note: HOTSPOT_SOURCE_NOTE,
  cell: { widthLng: CELL_W, heightLat: CELL_H },
  view: [LON0, LAT0, LON0 + COLS * CELL_W, LAT0 + ROWS * CELL_H],
  summary: {
    cells: cells.length,
    hotspots: cells.filter((cell) => cell.isHotspot).length,
    totalLengthKm: Number(
      (cells.reduce((sum, cell) => sum + cell.lenM, 0) / 1000).toFixed(1),
    ),
    meanScore: Number(
      (cells.reduce((sum, cell) => sum + cell.score, 0) / cells.length).toFixed(1),
    ),
    maxScore: cells[0]?.score ?? 0,
    hotspotRule: '综合分 ≥ 66（mock 示例规则）',
  },
  cells,
}
