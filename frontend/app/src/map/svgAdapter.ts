import { segmentColor } from '../lib/color'
import { MAP_H, MAP_W, VIEW, project } from '../lib/projection'
import type {
  Extent,
  LayerCollection,
  LoopFeature,
  MapLayerDef,
  PointGeometry,
  ViewBox,
} from '../types'
import type { MapAdapter, MapOrigin } from './adapter'
import {
  AREA_STYLES,
  LAYER_ORDER,
  LINE_STYLES,
  POINT_STYLES,
  ROAD_STROKE,
  layerGroupId,
} from './layerConfig'

const NS = 'http://www.w3.org/2000/svg'

function svgEl<K extends keyof SVGElementTagNameMap>(
  tag: K,
  attrs: Record<string, string | number> = {},
): SVGElementTagNameMap[K] {
  const el = document.createElementNS(NS, tag)
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v))
  return el
}

/** SVG 坐标统一 1 位小数（契约要求） */
function fmt(n: number): string {
  return n.toFixed(1)
}

interface RenderedLayer {
  def: MapLayerDef
  data: LayerCollection
  view: ViewBox
}

/**
 * SVG 版地图适配器：复刻 frontend/reference/index.html 的视觉参数，
 * 并把 manifest 里的全部图层画到固定的 <g data-layer="..."> 组里。
 *
 * 性能策略：
 * - 所有线与点各合并成单个 path（点用小圆弧 subpath），路网按颜色分桶；
 * - 同一份数据 + 同一 view 不重复绘制（extent 来回切换只重投影，不重新 fetch）；
 * - DOM 组顺序固定，route / marker 始终最上层。
 */
export const comparisonColors = { A: '#15503c', B: '#9b491c' } as const

export interface ComparisonMark {
  side: keyof typeof comparisonColors
  origin: MapOrigin
  route: LoopFeature | null
}

export class SvgAdapter implements MapAdapter {
  private host: HTMLElement | null = null
  private svg: SVGSVGElement | null = null
  private routeGroup: SVGGElement | null = null
  private markerGroup: SVGGElement | null = null
  private readonly groups = new Map<string, SVGGElement>()
  private readonly rendered = new Map<string, RenderedLayer>()
  private view: ViewBox = VIEW
  private viewName: Extent = 'central'
  private loop: LoopFeature | null = null
  private origin: MapOrigin | null = null
  private end: MapOrigin | null = null
  private comparison: ComparisonMark[] | null = null
  private zoom = 1
  private highlighted: [number, number][] | null = null
  private toilets: LayerCollection | null = null

  mount(host: HTMLElement): void {
    this.host = host
    const svg = svgEl('svg', {
      width: MAP_W,
      height: MAP_H,
      viewBox: `0 0 ${MAP_W} ${MAP_H}`,
      'data-view': 'central',
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

  setView(view: ViewBox, extent: Extent): void {
    const same = this.viewName === extent && this.sameView(view, this.view)
    this.view = view
    this.viewName = extent
    this.svg?.setAttribute('data-view', extent)
    if (same) return
    for (const [gid, entry] of this.rendered) {
      this.renderLayer(gid, entry.def, entry.data)
    }
    this.renderRoute()
    this.renderMarker()
    this.highlightRoad(this.highlighted)
    this.setToilets(this.toilets)
    this.reorder()
  }

  setViewport(x: number, y: number, zoom: number): void {
    this.svg?.setAttribute('viewBox', `${x} ${y} ${MAP_W / zoom} ${MAP_H / zoom}`)
    if (this.zoom === zoom) return
    this.zoom = zoom
    if (this.comparison) this.renderMarker()
  }

  setLayer(def: MapLayerDef, data: LayerCollection): void {
    const gid = layerGroupId(def)
    const cached = this.rendered.get(gid)
    if (cached && cached.def.id === def.id && cached.data === data && cached.view === this.view) {
      return
    }
    this.renderLayer(gid, def, data)
    this.reorder()
  }

  clearLayer(groupId: string): void {
    const group = this.groups.get(groupId)
    if (group) {
      group.remove()
      this.groups.delete(groupId)
    }
    this.rendered.delete(groupId)
  }

  setRoute(loop: LoopFeature | null): void {
    this.loop = loop
    const points = loop?.geometry.coordinates
    const start = points?.[0]
    const end = points?.[points.length - 1]
    this.end = start && end && (start[0] !== end[0] || start[1] !== end[1])
      ? { lng: end[0], lat: end[1] } : null
    this.renderRoute()
    this.renderMarker()
  }

  setOrigin(origin: MapOrigin | null): void {
    this.origin = origin
    this.renderMarker()
  }

  setComparison(marks: ComparisonMark[]): void {
    this.comparison = marks
    this.renderRoute()
    this.renderMarker()
  }

  highlightRoad(coordinates: [number, number][] | null): void {
    this.highlighted = coordinates
    const group = this.ensureGroup('selection')
    group.replaceChildren()
    if (coordinates) group.append(svgEl('path', {
      d: this.lineD(coordinates), fill: 'none', stroke: '#1569a6', 'stroke-width': 4,
      'vector-effect': 'non-scaling-stroke',
    }))
    this.reorder()
  }

  setToilets(data: LayerCollection | null): void {
    this.toilets = data
    const group = this.ensureGroup('toilets')
    group.replaceChildren()
    for (const feature of data?.features ?? []) {
      if (feature.geometry.type !== 'Point') continue
      const [x, y] = project(this.view, ...feature.geometry.coordinates)
      const dot = svgEl('circle', {
        cx: fmt(x), cy: fmt(y), r: 2.8,
        fill: feature.properties.accessible ? '#166ab0' : '#784b97',
        stroke: '#fff', 'stroke-width': 0.6,
      })
      const title = svgEl('title', {})
      title.textContent = [feature.properties.name, feature.properties.address].filter(Boolean).join(' · ')
      dot.append(title)
      group.append(dot)
    }
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
  }

  /* ------------------------------------------------------------------ */

  private sameView(a: ViewBox, b: ViewBox): boolean {
    return a.lon0 === b.lon0 && a.lat0 === b.lat0 && a.lon1 === b.lon1 && a.lat1 === b.lat1
  }

  private reorder(): void {
    const svg = this.svg
    if (!svg) return
    for (const gid of LAYER_ORDER) {
      const group = this.groups.get(gid)
      if (group) svg.appendChild(group)
    }
    for (const gid of ['toilets', 'selection']) {
      const group = this.groups.get(gid)
      if (group) svg.appendChild(group)
    }
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

  private renderLayer(gid: string, def: MapLayerDef, data: LayerCollection): void {
    const group = this.ensureGroup(gid)
    if (def.style === 'score') group.setAttribute('data-file', def.file)
    else group.removeAttribute('data-file')

    const frag = document.createDocumentFragment()
    this.appendLayer(frag, def, data)
    if (frag.childNodes.length === 0) {
      // 数据为空时不留空组（契约：组只在启用且加载完成时存在，且至少 1 个子节点）
      group.remove()
      this.groups.delete(gid)
      this.rendered.delete(gid)
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
        this.appendRoads(frag, data)
        break
      case 'metroRoute':
        this.appendLines(frag, data, LINE_STYLES.metroRoute)
        break
      case 'busRoute':
        this.appendLines(frag, data, LINE_STYLES.busRoute)
        break
      case 'metroStop':
      case 'busStop':
      case 'facility':
      case 'hotspot':
      case 'air':
        this.appendPoints(frag, data, POINT_STYLES[def.style])
        break
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
    }
    frag.appendChild(svgEl('path', attrs))
  }

  /* ------------------------------ 线 ------------------------------ */

  private appendRoads(frag: DocumentFragment, data: LayerCollection): void {
    // 先低分后高分；同一颜色合并为一条 path（与旧版视觉完全一致）
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
          'stroke-width': ROAD_STROKE.width,
          'stroke-linecap': 'round',
          'stroke-opacity': ROAD_STROKE.opacity,
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
      }),
    )
  }

  /* ------------------------------ 点 ------------------------------ */

  private appendPoints(
    frag: DocumentFragment,
    data: LayerCollection,
    style: { fill: string; r: number; opacity?: number; stroke?: string; strokeWidth?: number },
  ): void {
    const parts: string[] = []
    for (const f of data.features) {
      const g = f.geometry
      if (!g) continue
      if (g.type === 'Point') parts.push(this.pointArc(g, style.r))
      else if (g.type === 'MultiPoint') {
        for (const coord of g.coordinates) parts.push(this.pointArc({ type: 'Point', coordinates: coord }, style.r))
      }
    }
    if (parts.length === 0) return
    const attrs: Record<string, string | number> = { d: parts.join(''), fill: style.fill }
    if (style.opacity !== undefined) attrs['fill-opacity'] = style.opacity
    if (style.stroke) {
      attrs.stroke = style.stroke
      attrs['stroke-width'] = style.strokeWidth ?? 0
    }
    frag.appendChild(svgEl('path', attrs))
  }

  /** 单个圆点 → 两段半圆弧 subpath */
  private pointArc(point: PointGeometry, r: number): string {
    const [x, y] = project(this.view, point.coordinates[0], point.coordinates[1])
    const rr = fmt(r)
    return `M${fmt(x - r)},${fmt(y)}a${rr},${rr} 0 1,0 ${fmt(r * 2)},0a${rr},${rr} 0 1,0 ${fmt(-r * 2)},0`
  }

  /* --------------------------- 几何 → path --------------------------- */

  /** LineString 坐标 → path d */
  private lineD(coords: [number, number][]): string {
    const out: string[] = []
    for (let i = 0; i < coords.length; i++) {
      const [x, y] = project(this.view, coords[i][0], coords[i][1])
      out.push(`${i ? 'L' : 'M'}${fmt(x)},${fmt(y)}`)
    }
    return out.join('')
  }

  /** Polygon 的所有环 → path d（配合 fill-rule=evenodd 才能挖洞） */
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

  /* --------------------------- 路线 / 起点 --------------------------- */

  private renderRoute(): void {
    if (!this.routeGroup) return
    this.routeGroup.replaceChildren()
    if (this.comparison) {
      for (const { side, route } of this.comparison) {
        if (!route) continue
        const d = this.lineD(route.geometry.coordinates)
        const attrs = { d, fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round',
          'vector-effect': 'non-scaling-stroke', 'stroke-dasharray': side === 'B' ? '8 6' : 'none' }
        this.routeGroup.append(
          svgEl('path', { ...attrs, stroke: '#fff', 'stroke-width': 6 }),
          svgEl('path', { ...attrs, stroke: comparisonColors[side], 'stroke-width': 3, 'data-side': side }),
        )
      }
      return
    }
    if (!this.loop) return
    const d = this.lineD(this.loop.geometry.coordinates)
    this.routeGroup.append(
      svgEl('path', {
        d,
        fill: 'none',
        stroke: '#FFFFFF',
        'stroke-width': 9.2,
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        'stroke-opacity': 0.95,
      }),
      svgEl('path', {
        d,
        fill: 'none',
        stroke: '#141414',
        'stroke-width': 5.3,
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
      }),
    )
  }

  private renderMarker(): void {
    if (!this.markerGroup) return
    this.markerGroup.replaceChildren()
    if (this.comparison) {
      for (const { side, origin } of this.comparison) {
        const [x, y] = project(this.view, origin.lng, origin.lat)
        const label = svgEl('text', {
          x: fmt(x), y: fmt(y), 'text-anchor': 'middle', 'dominant-baseline': 'central',
          'font-size': 42 / this.zoom, 'font-weight': 700, fill: comparisonColors[side],
          stroke: '#fff', 'stroke-width': 7 / this.zoom, 'paint-order': 'stroke',
        })
        label.textContent = side
        this.markerGroup.append(label)
      }
      return
    }
    if (this.end) {
      const [x, y] = project(this.view, this.end.lng, this.end.lat)
      const label = svgEl('text', { x: fmt(x), y: fmt(y), fill: '#9b491c',
        'font-size': 20, 'font-weight': 700, stroke: '#fff', 'stroke-width': 4, 'paint-order': 'stroke' })
      label.textContent = '终'
      this.markerGroup.append(label)
    }
    if (!this.origin) return
    const [x, y] = project(this.view, this.origin.lng, this.origin.lat)
    this.markerGroup.appendChild(
      svgEl('circle', {
        cx: fmt(x),
        cy: fmt(y),
        r: 6,
        fill: '#fff',
        stroke: '#15503C',
        'stroke-width': 3,
      }),
    )
  }
}
