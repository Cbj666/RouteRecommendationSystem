import { segmentColor } from '../lib/color'
import { MAP_H, MAP_W, VIEW, project, unproject } from '../lib/projection'
import type {
  LayerCollection,
  LoopFeature,
  MapLayerDef,
  Place,
  PoiInfo,
  ViewBox,
} from '../types'
import type { MapAdapter, MapOrigin } from './adapter'
import {
  AREA_STYLES,
  LAYER_ORDER,
  LINE_STYLES,
  POI_STYLES,
  POINT_STYLES,
  ROAD_STROKE,
  layerGroupId,
} from './layerConfig'

const NS = 'http://www.w3.org/2000/svg'

/** 视口宽度 <= 30 km 时展开单个设施符号，大于 30 km 时整城聚合 */
export const DETAIL_WIDTH_KM = 30

function svgEl<K extends keyof SVGElementTagNameMap>(
  tag: K,
  attrs: Record<string, string | number> = {},
): SVGElementTagNameMap[K] {
  const el = document.createElementNS(NS, tag)
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v))
  return el
}

function fmt(n: number): string {
  return n.toFixed(1)
}

interface RenderedLayer {
  def: MapLayerDef
  data: LayerCollection
  view: ViewBox
}

interface ProjectedPoi {
  kind: 'facility' | 'toilet'
  name: string
  type: string
  address: string
  adname: string
  accessible: boolean
  lng: number
  lat: number
  x: number
  y: number
}

interface RenderedCluster {
  lng: number
  lat: number
  x: number
  y: number
  count: number
}

/** 拖动期「合成器平移」的过扫描比例：四周各多画 30%，可平移余量 = 0.3×视口宽 */
const PAN_PAD = 0.3

/**
 * SVG 地图适配器（F1 统一单图 + F4 运动场馆/公厕分符号与整城聚合）。
 */
export class SvgAdapter implements MapAdapter {
  private host: HTMLElement | null = null
  private svg: SVGSVGElement | null = null
  private routeGroup: SVGGElement | null = null
  private markerGroup: SVGGElement | null = null
  private readonly groups = new Map<string, SVGGElement>()
  private readonly rendered = new Map<string, RenderedLayer>()

  private view: ViewBox = VIEW
  private vpX = 0
  private vpY = 0
  private zoom = 1
  private panActive = false
  private panPad = 0

  private loop: LoopFeature | null = null
  private origin: MapOrigin | null = null
  private destination: MapOrigin | null = null
  private isOneway = false
  private highlighted: [number, number][] | null = null
  private places: Place[] = []

  /** F1 视口细粒度路网（null 时显示概览路网） */
  private detailRoads: LayerCollection | null = null

  /** F4 设施点缓存与无障碍开关 */
  private facilitiesData: LayerCollection | null = null
  private toiletsData: LayerCollection | null = null
  private facilitiesEnabled = false
  private toiletsEnabled = false
  private accessibleOnly = false

  /** 预投影点表，避免每次平移缩放重新投影 */
  private projectedFacilities: ProjectedPoi[] = []
  private projectedToilets: ProjectedPoi[] = []
  private visiblePois: ProjectedPoi[] = []
  private renderedClusters: RenderedCluster[] = []

  mount(host: HTMLElement): void {
    this.host = host
    const svg = svgEl('svg', {
      width: MAP_W,
      height: MAP_H,
      viewBox: `0 0 ${MAP_W} ${MAP_H}`,
      'aria-hidden': 'true',
    })
    const route = svgEl('g', { 'data-layer': 'route' })
    const marker = svgEl('g', { 'data-layer': 'marker' })
    svg.append(route, marker)
    host.replaceChildren(svg)
    this.svg = svg
    this.routeGroup = route
    this.markerGroup = marker
  }

  setView(view: ViewBox): void {
    if (this.sameView(view, this.view)) return
    this.view = view
    this.rebuildProjectedPois()
    for (const [gid, entry] of this.rendered) {
      if (gid === 'facilities' || gid === 'toilets') continue
      if (gid === 'roads' && this.detailRoads) {
        this.renderRoadsGroup(this.detailRoads, ROAD_STROKE.detailWidth, 'viewport')
      } else {
        this.renderLayer(gid, entry.def, entry.data)
      }
    }
    this.renderPois()
    this.renderRoute()
    this.renderMarker()
    this.highlightRoad(this.highlighted)
    this.renderPlaces()
    this.reorder()
  }

  setViewport(x: number, y: number, zoom: number): void {
    const zoomChanged = Math.abs(this.zoom - zoom) > 1e-6
    this.vpX = x
    this.vpY = y
    this.zoom = zoom
    this.svg?.setAttribute('viewBox', `${x} ${y} ${MAP_W / zoom} ${MAP_H / zoom}`)
    if (zoomChanged) {
      // 缩放动画每一帧都会改 viewBox；聚合圆点的半径是按当前 zoom 算的，
      // 留在画面上会被放大成大片灰块，因此先清掉，等视野稳定后由
      // refreshViewportSymbols() 按新缩放重画。
      this.removeGroup('poi_clusters')
      this.renderMarker()
      if (this.places.length) this.renderPlaces()
    }
  }

  /**
   * 进入「合成器平移」：把 SVG 放大 (1+2p) 并向外偏移同样比例，viewBox 同步加边，
   * 屏幕比例不变，但四周多出一圈已绘制内容。拖动时用 CSS transform 搬这块位图，
   * 高 DPI 下不再每帧重绘整个 SVG。
   * @returns 每一侧可平移的余量（CSS px）；0 表示当前不可用（调用方回退到改 viewBox）。
   */
  beginPan(): number {
    const svg = this.svg
    const host = this.host
    if (!svg || !host || this.panActive) return 0
    const rect = host.getBoundingClientRect()
    if (!rect.width || !rect.height) return 0
    this.panActive = true
    this.panPad = PAN_PAD
    const pct = PAN_PAD * 100
    svg.style.width = `${100 + 2 * pct}%`
    svg.style.height = `${100 + 2 * pct}%`
    svg.style.marginLeft = `${-pct}%`
    svg.style.marginTop = `${-pct}%`
    svg.style.willChange = 'transform'
    this.applyPanBox()
    return PAN_PAD * rect.width
  }

  private applyPanBox(): void {
    const svg = this.svg
    if (!svg) return
    const w = MAP_W / this.zoom
    const h = MAP_H / this.zoom
    const p = this.panPad
    svg.setAttribute(
      'viewBox',
      `${this.vpX - p * w} ${this.vpY - p * h} ${w * (1 + 2 * p)} ${h * (1 + 2 * p)}`,
    )
  }

  /** 平移态中按 CSS px 位移；由合成器搬运，不触发 SVG 重绘 */
  panBy(dx: number, dy: number): void {
    const svg = this.svg
    if (!svg || !this.panActive) return
    svg.style.transform = `translate3d(${dx.toFixed(2)}px, ${dy.toFixed(2)}px, 0)`
  }

  /** 退出平移态并把 viewBox 落到给定视口（先清 transform，再设 viewBox，避免闪一帧偏移） */
  endPan(x: number, y: number, zoom: number): void {
    const svg = this.svg
    this.panActive = false
    if (svg) {
      svg.style.transform = ''
      svg.style.width = ''
      svg.style.height = ''
      svg.style.marginLeft = ''
      svg.style.marginTop = ''
      svg.style.willChange = ''
    }
    this.setViewport(x, y, zoom)
  }

  get panning(): boolean {
    return this.panActive
  }

  /** 平移/缩放结束后刷新屏幕等比点符号与整城聚合 */
  refreshViewportSymbols(): void {
    for (const [gid, entry] of this.rendered) {
      if (
        entry.def.style === 'metroStop' ||
        entry.def.style === 'busStop' ||
        entry.def.style === 'hotspot' ||
        entry.def.style === 'air'
      ) {
        this.renderLayer(gid, entry.def, entry.data)
      }
    }
    this.renderPois()
    this.renderMarker()
    this.reorder()
  }

  /** 当前视口实际地理宽度（km） */
  viewportWidthKm(): number {
    const [lon0, lat0] = unproject(this.view, this.vpX, this.vpY + MAP_H / this.zoom)
    const [lon1, lat1] = unproject(this.view, this.vpX + MAP_W / this.zoom, this.vpY)
    const midLat = ((lat0 + lat1) / 2) * (Math.PI / 180)
    return Math.abs(lon1 - lon0) * 111.32 * Math.cos(midLat)
  }

  /** 当前视口经纬度范围 [minLng, minLat, maxLng, maxLat] */
  viewportBBox(): [number, number, number, number] {
    const [minLng, minLat] = unproject(this.view, this.vpX, this.vpY + MAP_H / this.zoom)
    const [maxLng, maxLat] = unproject(this.view, this.vpX + MAP_W / this.zoom, this.vpY)
    return [minLng, minLat, maxLng, maxLat]
  }

  setLayer(def: MapLayerDef, data: LayerCollection): void {
    const gid = layerGroupId(def)
    if (def.style === 'facility') {
      const changed = this.facilitiesData !== data || !this.facilitiesEnabled
      this.facilitiesData = data
      this.facilitiesEnabled = true
      if (changed) {
        this.projectedFacilities = this.projectPoiCollection(data, 'facility')
        this.renderPois()
        this.reorder()
      }
      return
    }
    if (def.style === 'toilet') {
      const changed = this.toiletsData !== data || !this.toiletsEnabled
      this.toiletsData = data
      this.toiletsEnabled = true
      if (changed) {
        this.projectedToilets = this.projectPoiCollection(data, 'toilet')
        this.renderPois()
        this.reorder()
      }
      return
    }

    const cached = this.rendered.get(gid)
    if (cached && cached.def.id === def.id && cached.data === data && cached.view === this.view) {
      return
    }
    if (gid === 'roads' && this.detailRoads) {
      this.rendered.set(gid, { def, data, view: this.view })
      this.renderRoadsGroup(this.detailRoads, ROAD_STROKE.detailWidth, 'viewport')
      this.reorder()
      return
    }
    this.renderLayer(gid, def, data)
    this.reorder()
  }

  clearLayer(groupId: string): void {
    if (groupId === 'facilities') {
      this.facilitiesEnabled = false
      this.removeGroup('facilities')
      this.renderPois()
      return
    }
    if (groupId === 'toilets') {
      this.toiletsEnabled = false
      this.removeGroup('toilets')
      this.renderPois()
      return
    }
    this.removeGroup(groupId)
    this.rendered.delete(groupId)
  }

  /** 设置或清除视口细粒度路网；null 时自动回落到概览路网 */
  setDetailRoads(data: LayerCollection | null): void {
    if (this.detailRoads === data) return
    this.detailRoads = data
    const base = this.rendered.get('roads')
    if (!base) return
    if (data && data.features.length > 0) {
      this.renderRoadsGroup(data, ROAD_STROKE.detailWidth, 'viewport')
    } else {
      this.renderRoadsGroup(base.data, ROAD_STROKE.overviewWidth, base.def.file)
    }
    this.reorder()
  }

  setAccessibleOnly(only: boolean): void {
    if (this.accessibleOnly === only) return
    this.accessibleOnly = only
    this.renderPois()
    this.reorder()
  }

  setRoute(loop: LoopFeature | null): void {
    this.loop = loop
    this.renderRoute()
    this.renderMarker()
  }

  setMarkers(origin: MapOrigin | null, destination: MapOrigin | null, isOneway: boolean): void {
    this.origin = origin
    this.destination = destination
    this.isOneway = isOneway
    this.renderMarker()
  }

  highlightRoad(coordinates: [number, number][] | null): void {
    this.highlighted = coordinates
    const group = this.ensureGroup('selection')
    group.replaceChildren()
    if (coordinates) {
      group.append(
        svgEl('path', {
          d: this.lineD(coordinates),
          fill: 'none',
          stroke: '#1569a6',
          'stroke-width': 4,
          'stroke-linecap': 'round',
          'stroke-linejoin': 'round',
          'vector-effect': 'non-scaling-stroke',
        }),
      )
    }
    this.reorder()
  }

  /** 屏幕坐标命中测试：放大状态下检测设施点（运动场馆 / 公厕） */
  hitTestPoi(canvasX: number, canvasY: number, radiusPx = 8): PoiInfo | null {
    if (this.visiblePois.length === 0) return null
    const svgX = this.vpX + canvasX / this.zoom
    const svgY = this.vpY + canvasY / this.zoom
    const maxDistSq = (radiusPx / this.zoom) ** 2
    let best: ProjectedPoi | null = null
    let bestDistSq = maxDistSq
    for (const poi of this.visiblePois) {
      const dx = poi.x - svgX
      const dy = poi.y - svgY
      const dSq = dx * dx + dy * dy
      if (dSq <= bestDistSq) {
        bestDistSq = dSq
        best = poi
      }
    }
    if (!best) return null
    return {
      kind: best.kind,
      name: best.name,
      type: best.type,
      address: best.address,
      adname: best.adname,
      accessible: best.accessible,
      lng: best.lng,
      lat: best.lat,
      screenX: (best.x - this.vpX) * this.zoom,
      screenY: (best.y - this.vpY) * this.zoom,
    }
  }

  /** 屏幕坐标命中测试：整城聚合状态下检测聚合圆 */
  hitTestCluster(
    canvasX: number,
    canvasY: number,
    radiusPx = 12,
  ): { lng: number; lat: number; count: number } | null {
    if (this.renderedClusters.length === 0) return null
    const svgX = this.vpX + canvasX / this.zoom
    const svgY = this.vpY + canvasY / this.zoom
    const maxDistSq = (radiusPx / this.zoom) ** 2
    let best: RenderedCluster | null = null
    let bestDistSq = maxDistSq
    for (const c of this.renderedClusters) {
      const dx = c.x - svgX
      const dy = c.y - svgY
      const dSq = dx * dx + dy * dy
      if (dSq <= bestDistSq) {
        bestDistSq = dSq
        best = c
      }
    }
    return best ? { lng: best.lng, lat: best.lat, count: best.count } : null
  }

  /** 搜索结果标记：白边深绿圆 + 序号，与下拉列表的序号一一对应。 */
  setPlaces(places: Place[]): void {
    this.places = places
    this.renderPlaces()
    this.reorder()
  }

  destroy(): void {
    this.host?.replaceChildren()
    this.host = null
    this.svg = null
    this.routeGroup = null
    this.markerGroup = null
    this.groups.clear()
    this.rendered.clear()
    this.loop = null
    this.origin = null
    this.destination = null
    this.places = []
    this.detailRoads = null
    this.visiblePois = []
    this.renderedClusters = []
  }

  /* ------------------------------------------------------------------ */

  private sameView(a: ViewBox, b: ViewBox): boolean {
    return a.lon0 === b.lon0 && a.lat0 === b.lat0 && a.lon1 === b.lon1 && a.lat1 === b.lat1
  }

  private removeGroup(gid: string): void {
    const group = this.groups.get(gid)
    if (group) {
      group.remove()
      this.groups.delete(gid)
    }
  }

  private reorder(): void {
    const svg = this.svg
    if (!svg) return
    for (const gid of LAYER_ORDER) {
      const group = this.groups.get(gid)
      if (group) svg.appendChild(group)
    }
    const clusterGroup = this.groups.get('poi_clusters')
    if (clusterGroup) svg.appendChild(clusterGroup)
    const selectionGroup = this.groups.get('selection')
    if (selectionGroup) svg.appendChild(selectionGroup)
    const placesGroup = this.groups.get('places')
    if (placesGroup) svg.appendChild(placesGroup)
    if (this.routeGroup) svg.appendChild(this.routeGroup)
    if (this.markerGroup) svg.appendChild(this.markerGroup)
  }

  private ensureGroup(gid: string): SVGGElement {
    let group = this.groups.get(gid)
    if (!group) {
      group = svgEl('g', { 'data-layer': gid })
      this.groups.set(gid, group)
      this.svg?.appendChild(group)
    }
    return group
  }

  private renderRoadsGroup(data: LayerCollection, strokeWidth: number, sourceTag: string): void {
    const group = this.ensureGroup('roads')
    group.setAttribute('data-file', sourceTag)
    const frag = document.createDocumentFragment()
    this.appendRoads(frag, data, strokeWidth)
    group.replaceChildren(frag)
  }

  private renderLayer(gid: string, def: MapLayerDef, data: LayerCollection): void {
    const group = this.ensureGroup(gid)
    if (def.style === 'score') group.setAttribute('data-file', def.file)
    else group.removeAttribute('data-file')

    const frag = document.createDocumentFragment()
    this.appendLayer(frag, def, data)
    if (frag.childNodes.length === 0) {
      this.removeGroup(gid)
      this.rendered.set(gid, { def, data, view: this.view })
      return
    }
    group.replaceChildren(frag)
    this.rendered.set(gid, { def, data, view: this.view })
  }

  private appendLayer(
    frag: DocumentFragment,
    def: MapLayerDef,
    data: LayerCollection,
  ): void {
    switch (def.style) {
      case 'water':
      case 'green':
      case 'boundary':
        this.appendArea(frag, data, def.style)
        break
      case 'score':
        this.appendRoads(frag, data, ROAD_STROKE.overviewWidth)
        break
      case 'metroRoute':
        this.appendLines(frag, data, LINE_STYLES.metroRoute)
        break
      case 'busRoute':
        this.appendLines(frag, data, LINE_STYLES.busRoute)
        break
      case 'metroStop':
      case 'busStop':
      case 'hotspot':
      case 'air':
        this.appendPoints(frag, data, POINT_STYLES[def.style])
        break
    }
  }

  /* ------------------------------ F4 设施符号与整城聚合 ------------------------------ */

  private rebuildProjectedPois(): void {
    this.projectedFacilities = this.facilitiesData
      ? this.projectPoiCollection(this.facilitiesData, 'facility')
      : []
    this.projectedToilets = this.toiletsData
      ? this.projectPoiCollection(this.toiletsData, 'toilet')
      : []
  }

  private projectPoiCollection(
    data: LayerCollection,
    kind: 'facility' | 'toilet',
  ): ProjectedPoi[] {
    const out: ProjectedPoi[] = []
    for (const f of data.features) {
      if (!f.geometry || f.geometry.type !== 'Point') continue
      const [lng, lat] = f.geometry.coordinates
      const [x, y] = project(this.view, lng, lat)
      const props = f.properties ?? {}
      out.push({
        kind,
        name: String(props.name || (kind === 'facility' ? '运动场馆' : '公共厕所')),
        type: String(props.type || ''),
        address: String(props.address || ''),
        adname: String(props.adname || ''),
        accessible: Boolean(props.accessible),
        lng,
        lat,
        x,
        y,
      })
    }
    return out
  }

  private renderPois(): void {
    this.visiblePois = []
    this.renderedClusters = []

    const activeFacilities = this.facilitiesEnabled ? this.projectedFacilities : []
    const activeToilets = this.toiletsEnabled
      ? this.accessibleOnly
        ? this.projectedToilets.filter((p) => p.accessible)
        : this.projectedToilets
      : []

    if (activeFacilities.length === 0 && activeToilets.length === 0) {
      this.removeGroup('facilities')
      this.removeGroup('toilets')
      this.removeGroup('poi_clusters')
      return
    }

    const widthKm = this.viewportWidthKm()
    const xMin = this.vpX - 24 / this.zoom
    const xMax = this.vpX + (MAP_W + 24) / this.zoom
    const yMin = this.vpY - 24 / this.zoom
    const yMax = this.vpY + (MAP_H + 24) / this.zoom

    if (widthKm > DETAIL_WIDTH_KM) {
      // 整城低缩放：按 0.01°（或其整数倍避免圆圈重叠糊成一片）聚合成深灰圆 + 数字
      this.removeGroup('facilities')
      this.removeGroup('toilets')
      const [minLng, , maxLng] = this.viewportBBox()
      const pxPerDeg = MAP_W / Math.max(1e-6, maxLng - minLng)
      // 保证相邻聚合圆中心距留足呼吸空间，且为 0.01° 的整数倍
      const cellDeg = Math.max(0.01, Math.ceil((32 / pxPerDeg) * 100) / 100)

      const buckets = new Map<
        string,
        { sumLng: number; sumLat: number; count: number }
      >()
      const addList = (list: ProjectedPoi[]) => {
        for (const p of list) {
          if (p.x < xMin || p.x > xMax || p.y < yMin || p.y > yMax) continue
          const gx = Math.floor(p.lng / cellDeg)
          const gy = Math.floor(p.lat / cellDeg)
          const key = `${gx},${gy}`
          let b = buckets.get(key)
          if (!b) {
            b = { sumLng: 0, sumLat: 0, count: 0 }
            buckets.set(key, b)
          }
          b.sumLng += p.lng
          b.sumLat += p.lat
          b.count += 1
        }
      }
      addList(activeFacilities)
      addList(activeToilets)

      // 全城视野下把 1.1 万个设施收敛成「少量聚集点」：
      // 只画最大的 80 个团（≥4 个设施），圆的大小表示数量，不标数字——
      // 之前每格一个数字会让整屏都是重复的 1/2/3，反而看不清底图与路线。
      const MIN_CLUSTER_COUNT = 4
      const MAX_CLUSTERS = 80
      const picked = [...buckets.values()]
        .filter((b) => b.count >= MIN_CLUSTER_COUNT)
        .sort((a, b) => b.count - a.count)
        .slice(0, MAX_CLUSTERS)

      if (picked.length === 0) {
        this.removeGroup('poi_clusters')
        return
      }

      const group = this.ensureGroup('poi_clusters')
      const circleParts: string[] = []
      const clusters: RenderedCluster[] = []

      for (const b of picked) {
        const lng = b.sumLng / b.count
        const lat = b.sumLat / b.count
        const [x, y] = project(this.view, lng, lat)
        const r = (POI_STYLES.cluster.r / this.zoom) * (0.45 + Math.min(0.45, Math.log2(b.count) / 22))
        clusters.push({ lng, lat, x, y, count: b.count })
        circleParts.push(this.circleArcXY(x, y, r))
      }

      this.renderedClusters = clusters
      group.dataset.clusters = String(clusters.length)
      group.replaceChildren(
        svgEl('path', {
          d: circleParts.join(''),
          fill: POI_STYLES.cluster.fill,
          'fill-opacity': 0.45,
          'stroke': 'none',
          'vector-effect': 'non-scaling-stroke',
        }),
      )
      return
    }

    // 放大视野（<= 30 km）：运动场馆画橙色圆角方块，公厕画蓝色白边圆点（无障碍加小内点）
    this.removeGroup('poi_clusters')

    // 1. 运动场馆：合并为单个 <path>（圆角方块，橙 #C2410C，5px）
    if (activeFacilities.length > 0) {
      const s = POI_STYLES.facility.size / this.zoom
      const h = s / 2
      const rx = POI_STYLES.facility.rx / this.zoom
      const parts: string[] = []
      for (const p of activeFacilities) {
        if (p.x < xMin || p.x > xMax || p.y < yMin || p.y > yMax) continue
        this.visiblePois.push(p)
        parts.push(this.roundedRectXY(p.x, p.y, h, rx))
      }
      if (parts.length > 0) {
        const group = this.ensureGroup('facilities')
        group.replaceChildren(
          svgEl('path', {
            d: parts.join(''),
            fill: POI_STYLES.facility.fill,
            stroke: POI_STYLES.facility.stroke,
            'stroke-width': POI_STYLES.facility.strokeWidth,
            'vector-effect': 'non-scaling-stroke',
          }),
        )
      } else {
        this.removeGroup('facilities')
      }
    } else {
      this.removeGroup('facilities')
    }

    // 2. 公共厕所：合并为 1 个圆形 <path>（蓝 #1D4ED8 + 白边）+ 1 个无障碍内点 <path>
    if (activeToilets.length > 0) {
      const r = POI_STYLES.toilet.r / this.zoom
      const innerR = POI_STYLES.toilet.accessibleDotR / this.zoom
      const circleParts: string[] = []
      const accessibleParts: string[] = []
      for (const p of activeToilets) {
        if (p.x < xMin || p.x > xMax || p.y < yMin || p.y > yMax) continue
        this.visiblePois.push(p)
        circleParts.push(this.circleArcXY(p.x, p.y, r))
        if (p.accessible) {
          accessibleParts.push(this.circleArcXY(p.x, p.y, innerR))
        }
      }
      if (circleParts.length > 0) {
        const group = this.ensureGroup('toilets')
        const frag = document.createDocumentFragment()
        frag.appendChild(
          svgEl('path', {
            d: circleParts.join(''),
            fill: POI_STYLES.toilet.fill,
            stroke: POI_STYLES.toilet.stroke,
            'stroke-width': POI_STYLES.toilet.strokeWidth,
            'vector-effect': 'non-scaling-stroke',
          }),
        )
        if (accessibleParts.length > 0) {
          frag.appendChild(
            svgEl('path', {
              d: accessibleParts.join(''),
              fill: POI_STYLES.toilet.accessibleDotFill,
            }),
          )
        }
        group.replaceChildren(frag)
      } else {
        this.removeGroup('toilets')
      }
    } else {
      this.removeGroup('toilets')
    }
  }

  /* ------------------------------ 面 ------------------------------ */

  private appendArea(
    frag: DocumentFragment,
    data: LayerCollection,
    kind: 'water' | 'green' | 'boundary',
  ): void {
    const style = AREA_STYLES[kind]
    const parts: string[] = []
    for (const f of data.features) {
      const g = f.geometry
      if (!g) continue
      if (g.type === 'Polygon') parts.push(this.polygonD(g.coordinates))
      else if (g.type === 'MultiPolygon') {
        for (const rings of g.coordinates) parts.push(this.polygonD(rings))
      }
    }
    if (parts.length === 0) return
    const attrs: Record<string, string | number> = {
      d: parts.join(''),
      fill: style.fill,
      'fill-opacity': style.opacity,
      'fill-rule': 'evenodd',
      stroke: 'none',
    }
    if ('stroke' in style) {
      attrs.stroke = style.stroke
      attrs['stroke-width'] = style.strokeWidth
      attrs['vector-effect'] = 'non-scaling-stroke'
    }
    frag.appendChild(svgEl('path', attrs))
  }

  /* ------------------------------ 线 ------------------------------ */

  private appendRoads(
    frag: DocumentFragment,
    data: LayerCollection,
    strokeWidth: number,
  ): void {
    const order = data.features
      .map((_, i) => i)
      .sort(
        (ia, ib) =>
          (data.features[ia].properties.score ?? 0) -
          (data.features[ib].properties.score ?? 0),
      )
    const buckets = new Map<string, { t: number; parts: string[] }>()
    for (const i of order) {
      const f = data.features[i]
      const g = f.geometry
      if (!g) continue
      const score = f.properties.score ?? 0
      const color = segmentColor(score, f.properties.grade)
      let bucket = buckets.get(color)
      if (!bucket) {
        bucket = { t: (score - 30) / 42, parts: [] }
        buckets.set(color, bucket)
      }
      if (g.type === 'LineString') bucket.parts.push(this.lineD(g.coordinates))
      else if (g.type === 'MultiLineString') {
        for (const c of g.coordinates) bucket.parts.push(this.lineD(c))
      }
    }
    for (const [color, bucket] of [...buckets.entries()].sort((a, b) => a[1].t - b[1].t)) {
      frag.appendChild(
        svgEl('path', {
          d: bucket.parts.join(''),
          fill: 'none',
          stroke: color,
          'stroke-width': strokeWidth,
          'stroke-linecap': 'round',
          'stroke-opacity': ROAD_STROKE.opacity,
          'vector-effect': 'non-scaling-stroke',
        }),
      )
    }
  }

  private appendLines(
    frag: DocumentFragment,
    data: LayerCollection,
    style: { stroke: string; width: number; opacity: number },
  ): void {
    const parts: string[] = []
    for (const f of data.features) {
      const g = f.geometry
      if (!g) continue
      if (g.type === 'LineString') parts.push(this.lineD(g.coordinates))
      else if (g.type === 'MultiLineString') {
        for (const c of g.coordinates) parts.push(this.lineD(c))
      }
    }
    if (parts.length === 0) return
    frag.appendChild(
      svgEl('path', {
        d: parts.join(''),
        fill: 'none',
        stroke: style.stroke,
        'stroke-width': style.width,
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        'stroke-opacity': style.opacity,
        'vector-effect': 'non-scaling-stroke',
      }),
    )
  }

  /* ------------------------------ 通用点 ------------------------------ */

  private appendPoints(
    frag: DocumentFragment,
    data: LayerCollection,
    style: { fill: string; r: number; opacity?: number; stroke?: string; strokeWidth?: number },
  ): void {
    const r = style.r / this.zoom
    const xMin = this.vpX - 20 / this.zoom
    const xMax = this.vpX + (MAP_W + 20) / this.zoom
    const yMin = this.vpY - 20 / this.zoom
    const yMax = this.vpY + (MAP_H + 20) / this.zoom
    const parts: string[] = []
    for (const f of data.features) {
      const g = f.geometry
      if (!g) continue
      if (g.type === 'Point') {
        const [x, y] = project(this.view, g.coordinates[0], g.coordinates[1])
        if (x >= xMin && x <= xMax && y >= yMin && y <= yMax) {
          parts.push(this.circleArcXY(x, y, r))
        }
      } else if (g.type === 'MultiPoint') {
        for (const coord of g.coordinates) {
          const [x, y] = project(this.view, coord[0], coord[1])
          if (x >= xMin && x <= xMax && y >= yMin && y <= yMax) {
            parts.push(this.circleArcXY(x, y, r))
          }
        }
      }
    }
    if (parts.length === 0) return
    const attrs: Record<string, string | number> = { d: parts.join(''), fill: style.fill }
    if (style.opacity !== undefined) attrs['fill-opacity'] = style.opacity
    if (style.stroke) {
      attrs.stroke = style.stroke
      attrs['stroke-width'] = style.strokeWidth ?? 0
      attrs['vector-effect'] = 'non-scaling-stroke'
    }
    frag.appendChild(svgEl('path', attrs))
  }

  private circleArcXY(x: number, y: number, r: number): string {
    const rr = r.toFixed(2)
    return `M${(x - r).toFixed(2)},${y.toFixed(2)}a${rr},${rr} 0 1,0 ${(r * 2).toFixed(2)},0a${rr},${rr} 0 1,0 ${(-r * 2).toFixed(2)},0`
  }

  private roundedRectXY(cx: number, cy: number, h: number, r: number): string {
    const x0 = cx - h
    const y0 = cy - h
    const x1 = cx + h
    const y1 = cy + h
    const rr = r.toFixed(2)
    return (
      `M${(x0 + r).toFixed(2)},${y0.toFixed(2)}` +
      `H${(x1 - r).toFixed(2)}` +
      `A${rr},${rr} 0 0 1 ${x1.toFixed(2)},${(y0 + r).toFixed(2)}` +
      `V${(y1 - r).toFixed(2)}` +
      `A${rr},${rr} 0 0 1 ${(x1 - r).toFixed(2)},${y1.toFixed(2)}` +
      `H${(x0 + r).toFixed(2)}` +
      `A${rr},${rr} 0 0 1 ${x0.toFixed(2)},${(y1 - r).toFixed(2)}` +
      `V${(y0 + r).toFixed(2)}` +
      `A${rr},${rr} 0 0 1 ${(x0 + r).toFixed(2)},${y0.toFixed(2)}Z`
    )
  }

  /* --------------------------- 几何 → path --------------------------- */

  private lineD(coords: [number, number][]): string {
    const out: string[] = []
    for (let i = 0; i < coords.length; i++) {
      const [x, y] = project(this.view, coords[i][0], coords[i][1])
      out.push(`${i ? 'L' : 'M'}${fmt(x)},${fmt(y)}`)
    }
    return out.join('')
  }

  private polygonD(rings: [number, number][][]): string {
    const out: string[] = []
    for (const ring of rings) {
      for (let i = 0; i < ring.length; i++) {
        const [x, y] = project(this.view, ring[i][0], ring[i][1])
        out.push(`${i ? 'L' : 'M'}${fmt(x)},${fmt(y)}`)
      }
      out.push('Z')
    }
    return out.join('')
  }

  /* --------------------------- 路线 / 起终点标记 --------------------------- */

  private renderRoute(): void {
    if (!this.routeGroup) return
    this.routeGroup.replaceChildren()
    if (!this.loop) return
    const d = this.lineD(this.loop.geometry.coordinates)
    this.routeGroup.append(
      svgEl('path', {
        d,
        fill: 'none',
        stroke: '#FFFFFF',
        'stroke-width': 8,
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        'stroke-opacity': 0.95,
        'vector-effect': 'non-scaling-stroke',
      }),
      svgEl('path', {
        d,
        fill: 'none',
        stroke: '#141414',
        'stroke-width': 4.4,
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        'vector-effect': 'non-scaling-stroke',
      }),
    )
  }

  /**
   * 搜索结果编号标记。半径/字号按 1/zoom 缩放，屏幕上的大小不随地图缩放变化；
   * `pointer-events="none"` 让点击继续落到地图上，避免挡住“点图选起点”。
   */
  private renderPlaces(): void {
    if (!this.svg) return
    let group = this.groups.get('places')
    if (!group) {
      if (this.places.length === 0) return
      group = this.ensureGroup('places')
    }
    group.setAttribute('pointer-events', 'none')
    group.replaceChildren()
    if (this.places.length === 0) {
      group.remove()
      this.groups.delete('places')
      return
    }

    const zoom = this.zoom || 1
    this.places.forEach((place, index) => {
      const [x, y] = project(this.view, place.lng, place.lat)
      const mark = svgEl('g', {
        'data-place-index': index + 1,
        'data-place-id': place.id,
      })
      mark.append(
        svgEl('circle', {
          cx: fmt(x),
          cy: fmt(y),
          r: fmt(10 / zoom),
          fill: '#15503C',
          stroke: '#fff',
          'stroke-width': fmt(2 / zoom),
        }),
      )
      const label = svgEl('text', {
        x: fmt(x),
        y: fmt(y),
        'text-anchor': 'middle',
        'dominant-baseline': 'central',
        'font-size': fmt(11 / zoom),
        'font-weight': 700,
        fill: '#fff',
      })
      label.textContent = String(index + 1)
      mark.append(label)
      const title = svgEl('title', {})
      title.textContent = [place.name, place.address || place.district].filter(Boolean).join(' · ')
      mark.append(title)
      group!.append(mark)
    })
  }

  private appendBadgeMarker(
    group: SVGGElement,
    point: MapOrigin,
    text: string,
    fill: string,
  ): void {
    const [x, y] = project(this.view, point.lng, point.lat)
    const r = 11 / this.zoom
    const strokeW = 2.4 / this.zoom
    const fontSize = 11 / this.zoom
    group.append(
      svgEl('circle', {
        cx: x.toFixed(2),
        cy: y.toFixed(2),
        r: r.toFixed(2),
        fill,
        stroke: '#FFFFFF',
        'stroke-width': strokeW.toFixed(2),
      }),
    )
    const label = svgEl('text', {
      x: x.toFixed(2),
      y: y.toFixed(2),
      'text-anchor': 'middle',
      'dominant-baseline': 'central',
      'font-size': fontSize.toFixed(2),
      'font-weight': 700,
      fill: '#FFFFFF',
    })
    label.textContent = text
    group.append(label)
  }

  private renderMarker(): void {
    if (!this.markerGroup) return
    this.markerGroup.replaceChildren()
    if (this.isOneway) {
      if (this.origin) {
        this.appendBadgeMarker(this.markerGroup, this.origin, 'A', '#15503C')
      }
      if (this.destination) {
        this.appendBadgeMarker(this.markerGroup, this.destination, 'B', '#C2410C')
      }
      return
    }
    if (this.origin) {
      this.appendBadgeMarker(this.markerGroup, this.origin, '起', '#15503C')
    }
  }
}
