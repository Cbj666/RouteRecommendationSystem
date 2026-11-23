/**
 * 图层样式注册表：manifest.layers[].style → SVG 绘制参数。
 *
 * 颜色/线宽/透明度按任务契约固定（与 reference / PPT 视觉语言一致），
 * 改这里就能整体换配色，adapter 里不再出现魔法数字。
 */
import type { LayerStyle, MapLayerDef } from '../types'

/**
 * 图层固定叠放顺序（从下到上）。
 * route / marker 不在此列表里——它们永远追加在最后，保持最上层。
 * roads 的三种变体（核心 / 干道 / 全量）共用同一个 data-layer="roads" 组。
 */
export const LAYER_ORDER = [
  'water',
  'green',
  'boundary',
  'roads',
  'metro_routes',
  'bus_routes',
  'metro_stops',
  'bus_stops',
  'facilities',
  'hotspots',
  'air_stations',
] as const

/** 面板分组顺序（与 manifest.layers 的 group 字段一致） */
export const LAYER_GROUP_LABELS = ['底图', '路网', '交通', '设施', '分析'] as const

/** 图层定义 → SVG 组 id（路网变体合并到 roads 组） */
export function layerGroupId(def: MapLayerDef): string {
  return def.style === 'score' ? 'roads' : def.id
}

/** 面图层样式（water / green / boundary） */
export const AREA_STYLES = {
  water: { fill: '#CFE3F0', opacity: 0.62 },
  green: { fill: '#DCEBDA', opacity: 0.72 },
  boundary: { fill: '#E8EFE8', opacity: 0.35, stroke: '#C9D6CE', strokeWidth: 1 },
} as const

/** 线图层样式（地铁 / 公交） */
export const LINE_STYLES = {
  metroRoute: { stroke: '#B4654A', width: 1.4, opacity: 0.72 },
  busRoute: { stroke: '#C9A227', width: 1, opacity: 0.45 },
} as const

export interface PointStyle {
  fill: string
  /** 圆点半径（SVG 像素） */
  r: number
  opacity?: number
  stroke?: string
  strokeWidth?: number
}

/** 点图层样式（设施 / 地铁站 / 公交站 / 热点 / 空气站） */
export const POINT_STYLES: Record<
  'facility' | 'metroStop' | 'busStop' | 'hotspot' | 'air',
  PointStyle
> = {
  facility: { fill: '#C0762A', r: 1.6, opacity: 0.7 },
  metroStop: { fill: '#8C4A3F', r: 2.2, stroke: '#FFFFFF', strokeWidth: 0.6 },
  busStop: { fill: '#8A9A93', r: 1.1, opacity: 0.65 },
  hotspot: { fill: '#D94F4F', r: 4, opacity: 0.8 },
  air: { fill: '#5B8FA8', r: 3 },
}

/** 面板色块（路网用色阶渐变） */
export const SWATCH: Record<LayerStyle, string> = {
  water: '#CFE3F0',
  green: '#DCEBDA',
  boundary: '#C9D6CE',
  score: 'linear-gradient(90deg, #d94f4f, #e8a33d, #8fbf6a, #2e7a5d, #15503c)',
  metroRoute: '#B4654A',
  metroStop: '#8C4A3F',
  busRoute: '#C9A227',
  busStop: '#8A9A93',
  facility: '#C0762A',
  hotspot: '#D94F4F',
  air: '#5B8FA8',
}

/** 路网描边宽度 / 透明度：与旧版 SvgAdapter 完全一致 */
export const ROAD_STROKE = { width: 1.25, opacity: 0.95 } as const
