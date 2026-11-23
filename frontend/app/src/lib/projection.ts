/**
 * 动态视图投影：把经纬度线性映射到 1600×1000 的 SVG 画布。
 *
 * 片区（central）视图必须与 frontend/reference 逐像素一致：
 *   这个 bbox 乘 cos(30.5°) 后经纬比正好 1600/1000，所以简单线性投影不会变形。
 * 全城（city）视图由 manifest.view.city 的原始数据 bbox 经 fitView() 等比适配得到：
 *   - 经度先乘 cos(中心纬度) 修正，避免高纬度横向拉伸；
 *   - 取宽高两个方向的较小缩放，保证 1600×1000 内完整可见（约 24px 留白）；
 *   - 视图仍用 bbox 四边表示，所以 project/unproject 保持线性、互为逆运算。
 */
import type { ViewBox } from '../types'

export type { ViewBox }

export const MAP_W = 1600
export const MAP_H = 1000

/** 片区视图：PPT 原型 / reference 的精确视野（不要改数值） */
export const VIEW: ViewBox = {
  lon0: 114.305,
  lat0: 30.508,
  lon1: 114.405,
  lat1: 30.562,
}

/** 投影留白（像素）：fitView 时四周各留这么多 */
export const VIEW_PADDING = 24

export function projectX(lon: number, view: ViewBox = VIEW): number {
  return ((lon - view.lon0) / (view.lon1 - view.lon0)) * MAP_W
}

export function projectY(lat: number, view: ViewBox = VIEW): number {
  return ((view.lat1 - lat) / (view.lat1 - view.lat0)) * MAP_H
}

/** WGS84 → 画布像素 */
export function project(view: ViewBox, lon: number, lat: number): [number, number] {
  return [projectX(lon, view), projectY(lat, view)]
}

/** 画布像素 → WGS84；地图点击选起点用（必须用当前 view） */
export function unproject(view: ViewBox, x: number, y: number): [number, number] {
  const lon = view.lon0 + (x / MAP_W) * (view.lon1 - view.lon0)
  const lat = view.lat1 - (y / MAP_H) * (view.lat1 - view.lat0)
  return [lon, lat]
}

/**
 * 把一个经纬度 bbox 等比适配进 1600×1000（含 paddingPx 留白）。
 * 返回的 ViewBox 可直接交给 project/unproject 做线性映射。
 */
export function fitView(
  minLon: number,
  minLat: number,
  maxLon: number,
  maxLat: number,
  paddingPx: number = VIEW_PADDING,
): ViewBox {
  const lonSpan = Math.max(1e-9, maxLon - minLon)
  const latSpan = Math.max(1e-9, maxLat - minLat)
  const midLat = (minLat + maxLat) / 2
  const kx = Math.cos((midLat * Math.PI) / 180)
  const availW = Math.max(1, MAP_W - paddingPx * 2)
  const availH = Math.max(1, MAP_H - paddingPx * 2)
  // 每 1 像素对应的“修正后经度 / 纬度”取较大者 → 两个方向都装得下
  const scale = Math.min(availW / (lonSpan * kx), availH / latSpan)
  const lonSpanPx = MAP_W / (scale * kx)
  const latSpanPx = MAP_H / scale
  const midLon = (minLon + maxLon) / 2
  return {
    lon0: midLon - lonSpanPx / 2,
    lon1: midLon + lonSpanPx / 2,
    lat1: midLat + latSpanPx / 2,
    lat0: midLat - latSpanPx / 2,
  }
}

/** 便捷重载：bbox = [minLon, minLat, maxLon, maxLat] */
export function fitViewBBox(
  bbox: [number, number, number, number],
  paddingPx: number = VIEW_PADDING,
): ViewBox {
  return fitView(bbox[0], bbox[1], bbox[2], bbox[3], paddingPx)
}
