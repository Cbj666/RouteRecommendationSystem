import type { LayerCollection, LoopFeature, MapLayerDef, ViewBox } from '../types'

export interface MapOrigin {
  lng: number
  lat: number
}

/**
 * 地图适配器边界。
 * 当前用 SVG 实现（与 reference 像素对齐），不加载任何第三方地图 JS、
 * 不在浏览器持有地图开发者 Key。若将来换底图，必须先经后端代理瓦片/接口，
 * 页面组件不需要改。
 *
 * 图层系统：
 * - mount 后建立固定的组容器（route / marker 始终存在）；
 * - setView 切换投影范围，已渲染图层 / 路线 / 起点标记会按新 view 重投影；
 * - setLayer 渲染单个图层（按 def.style 选样式）；clearLayer 移除整个组；
 * - 组顺序由 LAYER_ORDER 固定，route / marker 永远最上层。
 */
export interface MapAdapter {
  mount(host: HTMLElement): void
  setView(view: ViewBox): void
  setLayer(def: MapLayerDef, data: LayerCollection): void
  clearLayer(groupId: string): void
  setRoute(loop: LoopFeature | null): void
  setMarkers(origin: MapOrigin | null, destination: MapOrigin | null, isOneway: boolean): void
  destroy(): void
}
