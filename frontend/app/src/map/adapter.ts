import type { LoopFeature, SegmentGeoCollection, WaterGreenCollection } from '../types'

export interface MapOrigin {
  lng: number
  lat: number
}

/**
 * 地图适配器边界。
 * M1 用 SVG 实现（与 reference 像素对齐）；拿到百度 AK 后加一个 BaiduAdapter，
 * 页面组件不需要改。坐标转换（WGS84 → BD-09）只允许发生在适配器内部。
 */
export interface MapAdapter {
  mount(host: HTMLElement): void
  setBase(segments: SegmentGeoCollection, waterGreen?: WaterGreenCollection): void
  setRoute(loop: LoopFeature | null): void
  setOrigin(origin: MapOrigin | null): void
  destroy(): void
}
