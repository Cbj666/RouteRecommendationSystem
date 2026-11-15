import type { LoopFeature, SegmentGeoCollection, WaterGreenCollection } from '../types'
import { segmentColor } from '../lib/color'
import { projectX, projectY, MAP_W, MAP_H } from '../lib/projection'
import type { MapAdapter, MapOrigin } from './adapter'

const NS = 'http://www.w3.org/2000/svg'

function svgEl<K extends keyof SVGElementTagNameMap>(
  tag: K,
  attrs: Record<string, string | number> = {},
): SVGElementTagNameMap[K] {
  const el = document.createElementNS(NS, tag)
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v))
  return el
}

/** LineString 坐标 → path d */
function lineD(coords: [number, number][]): string {
  const out: string[] = []
  for (let i = 0; i < coords.length; i++) {
    const [lon, lat] = coords[i]
    out.push(`${i ? 'L' : 'M'}${projectX(lon).toFixed(1)},${projectY(lat).toFixed(1)}`)
  }
  return out.join('')
}

/** 一个 Polygon 的所有环 → path d（配合 fill-rule=evenodd 才能挖洞） */
function polygonD(rings: [number, number][][]): string {
  const out: string[] = []
  for (const ring of rings) {
    for (let i = 0; i < ring.length; i++) {
      const [lon, lat] = ring[i]
      out.push(`${i ? 'L' : 'M'}${projectX(lon).toFixed(1)},${projectY(lat).toFixed(1)}`)
    }
    out.push('Z')
  }
  return out.join('')
}

/**
 * SVG 版地图适配器：复刻 frontend/reference/index.html 的绘制顺序与参数。
 *
 * 与 reference 的唯一差别是「按颜色分桶」：8,005 条路网只有 53 种分数，
 * 同色合并成一个 path，DOM 从 8,005 降到 53，视觉不变（同色、同线宽、同顺序）。
 */
export class SvgAdapter implements MapAdapter {
  private host: HTMLElement | null = null
  private svg: SVGSVGElement | null = null
  private baseGroup: SVGGElement | null = null
  private routeGroup: SVGGElement | null = null
  private markerGroup: SVGGElement | null = null

  mount(host: HTMLElement): void {
    this.host = host
    const svg = svgEl('svg', {
      width: MAP_W,
      height: MAP_H,
      viewBox: `0 0 ${MAP_W} ${MAP_H}`,
      'aria-hidden': 'true',
    })
    const base = svgEl('g', { 'data-layer': 'base' })
    const route = svgEl('g', { 'data-layer': 'route' })
    const marker = svgEl('g', { 'data-layer': 'marker' })
    svg.append(base, route, marker)
    host.replaceChildren(svg)
    this.svg = svg
    this.baseGroup = base
    this.routeGroup = route
    this.markerGroup = marker
  }

  setBase(segments: SegmentGeoCollection, waterGreen?: WaterGreenCollection): void {
    if (!this.baseGroup) return
    const frag = document.createDocumentFragment()

    // 1) 水体与绿地：可选图层（PPT 未画，默认不传），半透明压在路网下面
    if (waterGreen) {
      for (const f of waterGreen.features) {
        const g = f.geometry
        if (!g) continue
        const kind = (f.properties.kind ?? f.properties.type ?? '').toLowerCase()
        const water = kind.includes('water') || kind.includes('水')
        const polygons = g.type === 'Polygon' ? [g.coordinates] : g.coordinates
        for (const rings of polygons) {
          frag.appendChild(
            svgEl('path', {
              d: polygonD(rings),
              fill: water ? '#CFE3F0' : '#DCEBDA',
              'fill-opacity': 0.55,
              'fill-rule': 'evenodd',
              stroke: 'none',
            }),
          )
        }
      }
    }

    // 2) 路网：先低分后高分；同一颜色合并为一条 path
    const sorted = [...segments.features].sort(
      (a, b) => a.properties.score - b.properties.score,
    )
    const buckets = new Map<string, { t: number; parts: string[] }>()
    for (const f of sorted) {
      const g = f.geometry
      if (!g) continue
      const score = f.properties.score
      const color = segmentColor(score)
      let bucket = buckets.get(color)
      if (!bucket) {
        bucket = { t: (score - 30) / 42, parts: [] }
        buckets.set(color, bucket)
      }
      if (g.type === 'LineString') {
        bucket.parts.push(lineD(g.coordinates))
      } else {
        for (const c of g.coordinates) bucket.parts.push(lineD(c))
      }
    }
    for (const [color, bucket] of [...buckets.entries()].sort((a, b) => a[1].t - b[1].t)) {
      frag.appendChild(
        svgEl('path', {
          d: bucket.parts.join(''),
          fill: 'none',
          stroke: color,
          'stroke-width': 1.25,
          'stroke-linecap': 'round',
          'stroke-opacity': 0.95,
        }),
      )
    }

    this.baseGroup.replaceChildren(frag)
  }

  setRoute(loop: LoopFeature | null): void {
    if (!this.routeGroup) return
    this.routeGroup.replaceChildren()
    if (!loop) return
    const d = lineD(loop.geometry.coordinates)
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

  setOrigin(origin: MapOrigin | null): void {
    if (!this.markerGroup) return
    this.markerGroup.replaceChildren()
    if (!origin) return
    this.markerGroup.appendChild(
      svgEl('circle', {
        cx: projectX(origin.lng).toFixed(1),
        cy: projectY(origin.lat).toFixed(1),
        r: 6,
        fill: '#fff',
        stroke: '#15503C',
        'stroke-width': 3,
      }),
    )
  }

  destroy(): void {
    this.host?.replaceChildren()
    this.host = null
    this.svg = null
    this.baseGroup = null
    this.routeGroup = null
    this.markerGroup = null
  }
}
