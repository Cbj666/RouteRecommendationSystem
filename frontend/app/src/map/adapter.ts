import type { LayerCollection, LoopFeature, MapLayerDef, ViewBox } from '../types'

export interface MapOrigin {
  lng: number
  lat: number
}

/**
 * 地图适配器边界。
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
