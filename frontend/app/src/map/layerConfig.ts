/**
 * 图层样式注册表：manifest.layers[].style → SVG 绘制参数。
 */
import type { LayerStyle, MapLayerDef } from '../types'

/**
 * 图层固定叠放顺序（从下到上）。
 * selection / route / marker 永远追加在最后，保持最上层；
 * 设施（facilities / toilets）在路网之上、路线之下。
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
  'toilets',
  'hotspots',
  'air_stations',
] as const

/** 面板分组顺序（与 manifest.layers 的 group 字段一致） */
export const LAYER_GROUP_LABELS = ['底图', '路网', '交通', '设施', '分析'] as const

/** 图层定义 → SVG 组 id */
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
  metroRoute: { stroke: '#B4654A', width: 1.5, opacity: 0.72 },
  busRoute: { stroke: '#C9A227', width: 1, opacity: 0.45 },
} as const

export interface PointStyle {
  fill: string
  /** 屏幕像素半径 */
  r: number
  opacity?: number
  stroke?: string
  strokeWidth?: number
}

/** 通用点图层样式（地铁站 / 公交站 / 热点 / 空气站） */
export const POINT_STYLES: Record<
  'metroStop' | 'busStop' | 'hotspot' | 'air',
  PointStyle
> = {
  metroStop: { fill: '#8C4A3F', r: 2.6, stroke: '#FFFFFF', strokeWidth: 0.8 },
  busStop: { fill: '#8A9A93', r: 1.8, opacity: 0.7 },
  hotspot: { fill: '#D94F4F', r: 4.5, opacity: 0.85, stroke: '#FFFFFF', strokeWidth: 0.8 },
  air: { fill: '#5B8FA8', r: 3.5, stroke: '#FFFFFF', strokeWidth: 0.8 },
}

/** F4 设施符号样式：形状优先区分，颜色辅助 */
export const POI_STYLES = {
  facility: {
    fill: '#C2410C',
    size: 5, // 4–5 px 圆角方块
    rx: 1.2,
    stroke: '#FFFFFF',
    strokeWidth: 0.75,
  },
  toilet: {
    fill: '#1D4ED8',
    r: 2.5, // 5 px 直径圆形 + 白边
    stroke: '#FFFFFF',
    strokeWidth: 1,
    accessibleDotR: 0.9,
    accessibleDotFill: '#FFFFFF',
  },
  cluster: {
    fill: '#374151',
    r: 9, // 18 px 直径深灰圆
    stroke: '#FFFFFF',
    strokeWidth: 1.4,
    textFill: '#FFFFFF',
  },
} as const

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
  facility: '#C2410C',
  toilet: '#1D4ED8',
  hotspot: '#D94F4F',
  air: '#5B8FA8',
}

/** 路网描边宽度（使用 non-scaling-stroke 保持缩放后视觉稳定） */
export const ROAD_STROKE = { overviewWidth: 1.3, detailWidth: 1.7, opacity: 0.94 } as const
