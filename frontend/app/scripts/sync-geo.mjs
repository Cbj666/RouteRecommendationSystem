/**
 * 把前端可渲染的静态空间数据同步到 public/geo/，并生成 manifest.json。
 *
 * 为什么需要这一步：Vite 的 root 是 frontend/app，`fetch('../../data/...')`
 * 在 dev 下会被 fs 限制、在 build 后也不存在。复制进 public/ 后：
 *   - dev:  /geo/<file>
 *   - build: dist/geo/<file>
 * 数据真源仍然是仓库 data/ 下的文件，public/geo/ 只是可再生的复制品（已 gitignore）。
 *
 * 产物：
 *   - 13 个渲染层 GeoJSON（water / green / boundary / roads / metro / bus / facilities / hotspots / air）
 *   - manifest.json：驱动前端图层；同时盘点仓库里 16 个空间数据文件
 *     （8 GeoJSON + 3 GeoPackage 文件 + 5 CSV；gpkg 与 loops.geojson 只盘点、不渲染）。
 *
 * 约定：
 *   - 目标文件 mtime >= 源文件 mtime 且非空 → 跳过重写（30 MB 的路网不重复复制）；
 *   - 写文件先写 .tmp 再 rename，避免进程中断留下半截文件；
 *   - manifest.json 每次重写（generated_at / bytes 等随源数据变化）；
 *   - 坐标统一 WGS84(EPSG:4326) 经纬度；点坐标保留 6 位小数，整文件复制保留原精度。
 *
 * 触发：npm run sync:geo（predev / prebuild 自动执行）。
 */
import { copyFile, mkdir, readFile, rename, rm, stat, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const appRoot = resolve(here, '..')
const repoRoot = resolve(appRoot, '..', '..')
const outDir = resolve(appRoot, 'public', 'geo')
const fromRepo = (relPath) => resolve(repoRoot, relPath)

// ---------------------------------------------------------------------------
// 源文件（仓库相对路径，正斜杠；manifest 里用同一套路径）
// ---------------------------------------------------------------------------
const SRC = {
  waterGreen: 'data/output/running/v1/web/water_green.geojson',
  segmentsCity: 'data/output/running/v1/web/segments_city.geojson',
  segmentsArterial: 'data/output/running/v1/web/segments_arterial.geojson',
  boundary: 'data/processed/v1/wuhan_boundary.geojson',
  routesMetro: 'data/processed/v1/routes_metro.geojson',
  routesBus: 'data/processed/v1/routes_bus.geojson',
  stopsMetro: 'data/processed/v1/stops_metro.csv',
  stopsBus: 'data/processed/v1/stops_bus.csv',
  facilities: 'data/processed/running/v1/amap_sport_poi.csv',
  toilets: 'data/processed/running/v1/amap_toilet_poi.csv',
  hotspots: 'data/output/running/v1/demo/hotspots_kept.csv',
  airStations: 'data/processed/running/v1/air_quality_stations.csv',
  loops: 'data/output/running/v1/loops.geojson',
  // 热点页的分析产物（1 km 全城网格，JSON）；不在图层清单里，单独复制
  hotspotGrid: 'data/output/running/v1/hotspot/grid_1000m.json',
}

// ---------------------------------------------------------------------------
// 渲染层定义（顺序即前端图层叠放/清单顺序）
// ---------------------------------------------------------------------------
const LAYERS = [
  {
    id: 'water',
    label: '水体',
    group: '底图',
    file: 'water.geojson',
    geometry: 'polygon',
    source: `${SRC.waterGreen}#kind=water`,
    style: 'water',
    default: true,
    extent: 'both',
    variant: null,
    variantLevel: null,
  },
  {
    id: 'green',
    label: '绿地',
    group: '底图',
    file: 'green.geojson',
    geometry: 'polygon',
    source: `${SRC.waterGreen}#kind=green`,
    style: 'green',
    default: true,
    extent: 'both',
    variant: null,
    variantLevel: null,
  },
  {
    id: 'boundary',
    label: '行政边界',
    group: '底图',
    file: 'boundary.geojson',
    geometry: 'polygon',
    source: SRC.boundary,
    style: 'boundary',
    default: true,
    extent: 'both',
    variant: null,
    variantLevel: null,
  },
  {
    id: 'roads_arterial',
    label: '适宜性路网',
    group: '路网',
    file: 'segments_arterial.geojson',
    geometry: 'line',
    source: SRC.segmentsArterial,
    style: 'score',
    default: true,
    extent: 'both',
    variant: 'roads',
    variantLevel: 'city',
  },
  {
    id: 'metro_routes',
    label: '地铁线路',
    group: '交通',
    file: 'metro_routes.geojson',
    geometry: 'line',
    source: SRC.routesMetro,
    style: 'metroRoute',
    default: true,
    extent: 'both',
    variant: null,
    variantLevel: null,
  },
  {
    id: 'metro_stops',
    label: '地铁站',
    group: '交通',
    file: 'metro_stops.geojson',
    geometry: 'point',
    source: SRC.stopsMetro,
    style: 'metroStop',
    default: true,
    extent: 'both',
    variant: null,
    variantLevel: null,
  },
  {
    id: 'bus_routes',
    label: '公交线路',
    group: '交通',
    file: 'bus_routes.geojson',
    geometry: 'line',
    source: SRC.routesBus,
    style: 'busRoute',
    default: false,
    extent: 'both',
    variant: null,
    variantLevel: null,
  },
  {
    id: 'bus_stops',
    label: '公交站点',
    group: '交通',
    file: 'bus_stops.geojson',
    geometry: 'point',
    source: SRC.stopsBus,
    style: 'busStop',
    default: false,
    extent: 'both',
    variant: null,
    variantLevel: null,
  },
  {
    id: 'facilities',
    label: '运动场馆',
    group: '设施',
    file: 'facilities.geojson',
    geometry: 'point',
    source: SRC.facilities,
    style: 'facility',
    default: true,
    extent: 'both',
    variant: null,
    variantLevel: null,
  },
  {
    id: 'toilets',
    label: '公共厕所',
    group: '设施',
    file: 'toilets.geojson',
    geometry: 'point',
    source: SRC.toilets,
    style: 'toilet',
    default: true,
    extent: 'both',
    variant: null,
    variantLevel: null,
  },
  {
    id: 'hotspots',
    label: '推荐热点',
    group: '分析',
    file: 'hotspots.geojson',
    geometry: 'point',
    source: SRC.hotspots,
    style: 'hotspot',
    default: false,
    extent: 'both',
    variant: null,
    variantLevel: null,
  },
  {
    id: 'air_stations',
    label: '空气质量站',
    group: '分析',
    file: 'air_stations.geojson',
    geometry: 'point',
    source: SRC.airStations,
    style: 'air',
    default: false,
    extent: 'both',
    variant: null,
    variantLevel: null,
  },
]

// 水路边界等整文件复制的图层（复制保留原坐标精度；不再复制 30 MB 的 segments_all.geojson）
const COPY_FILES = [
  { file: 'boundary.geojson', source: SRC.boundary },
  { file: 'segments_city.geojson', source: SRC.segmentsCity },
  { file: 'segments_arterial.geojson', source: SRC.segmentsArterial },
  { file: 'metro_routes.geojson', source: SRC.routesMetro },
  { file: 'bus_routes.geojson', source: SRC.routesBus },
]

// CSV → 点图层
const POINT_LAYERS = [
  {
    file: 'metro_stops.geojson',
    source: SRC.stopsMetro,
    lonColumn: 'lng',
    latColumn: 'lat',
    properties: (row) => ({
      name: row.name,
      line_count: toNumberOrNull(row.line_count),
    }),
  },
  {
    file: 'bus_stops.geojson',
    source: SRC.stopsBus,
    lonColumn: 'lng',
    latColumn: 'lat',
    properties: (row) => ({
      name: row.name,
      line_count: toNumberOrNull(row.line_count),
    }),
  },
  {
    file: 'facilities.geojson',
    source: SRC.facilities,
    lonColumn: 'lng',
    latColumn: 'lat',
    properties: (row) => ({
      name: row.name || '',
      type: row.type || '',
      address: row.address || '',
      adname: row.adname || '',
      in_boundary: row.in_boundary === 'True' || row.in_boundary === 'true' || row.in_boundary === '1',
    }),
  },
  {
    file: 'toilets.geojson',
    source: SRC.toilets,
    lonColumn: 'lng',
    latColumn: 'lat',
    filter: (row) => /公共厕所|洗手间/.test(row.type || ''),
    properties: (row) => ({
      name: row.name || '',
      type: row.type || '',
      address: row.address || '',
      adname: row.adname || '',
      in_boundary: row.in_boundary === 'True' || row.in_boundary === 'true' || row.in_boundary === '1',
      accessible: /无障碍|残障/.test(`${row.type || ''}|${row.name || ''}`),
    }),
  },
  {
    file: 'hotspots.geojson',
    source: SRC.hotspots,
    lonColumn: 'lng',
    latColumn: 'lat',
    properties: (row) => ({
      lng: round6(toFiniteNumber(row.lng, 'hotspots_kept.lng')),
      lat: round6(toFiniteNumber(row.lat, 'hotspots_kept.lat')),
      n: toNumberOrNull(row.n),
      best: toNumberOrNull(row.best),
      top3: toNumberOrNull(row.top3),
      len_m: toNumberOrNull(row.len_m),
    }),
  },
  {
    file: 'air_stations.geojson',
    source: SRC.airStations,
    lonColumn: 'lon', // 注意：空气质量站表头顺序是 lat,lon
    latColumn: 'lat',
    properties: (row) => ({
      name: row.name,
      aqi: toNumberOrNull(row.aqi),
    }),
  },
]

// manifest.view：中心区（PPT 原型那一屏）与全市视野
const VIEW = {
  central: { lon0: 114.305, lat0: 30.508, lon1: 114.405, lat1: 30.562 },
  city: { lon0: 113.698077, lat0: 29.971928, lon1: 115.076651, lat1: 31.362866 },
}

// manifest.inventory 里 GeoPackage 的已知元数据（不参与渲染）
const GPKG_BBOX_CITY = [113.442879, 29.795648, 115.212007, 31.613508]
const GPKG_BBOX_POI = [113.697681, 29.971868, 115.079109, 31.356541]

// ---------------------------------------------------------------------------
// 小工具
// ---------------------------------------------------------------------------
function round6(value) {
  return Math.round(value * 1e6) / 1e6
}

function toFiniteNumber(value, context) {
  const num = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(num)) {
    throw new Error(`无效数值（${context}）：${JSON.stringify(value)}`)
  }
  return num
}

function toNumberOrNull(value) {
  if (value === undefined || value === null || value === '') return null
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

async function statOrNull(filePath) {
  try {
    return await stat(filePath)
  } catch (err) {
    if (err && err.code === 'ENOENT') return null
    throw err
  }
}

async function readText(filePath) {
  return (await readFile(filePath, 'utf8')).replace(/^\uFEFF/, '')
}

async function readJson(filePath) {
  return JSON.parse(await readText(filePath))
}

/** 目标文件是否需要重写：不存在 / 空文件 / 比源文件旧 */
async function needsRewrite(dest, srcStat) {
  const current = await statOrNull(dest)
  if (!current || current.size === 0) return true
  return current.mtimeMs < srcStat.mtimeMs
}

async function atomicWrite(dest, content) {
  const tmp = `${dest}.tmp`
  await writeFile(tmp, content)
  await rename(tmp, dest)
}

async function atomicCopy(src, dest) {
  const tmp = `${dest}.tmp`
  await copyFile(src, tmp)
  await rename(tmp, dest)
}

/**
 * 最小 CSV 解析器：支持 BOM、CRLF/LF、引号字段（字段内含逗号、"" 转义），忽略空行。
 * 返回二维数组（第一行是表头）。
 */
function parseCsv(text) {
  const src = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text
  const rows = []
  let row = []
  let field = ''
  let quoted = false

  const pushRow = () => {
    if (row.length > 1 || (row.length === 1 && row[0] !== '')) rows.push(row)
    row = []
  }

  for (let i = 0; i < src.length; i += 1) {
    const ch = src[i]
    if (quoted) {
      if (ch === '"') {
        if (src[i + 1] === '"') {
          field += '"'
          i += 1
        } else {
          quoted = false
        }
      } else {
        field += ch
      }
      continue
    }
    if (ch === '"') {
      quoted = true
    } else if (ch === ',') {
      row.push(field)
      field = ''
    } else if (ch === '\n') {
      row.push(field)
      field = ''
      pushRow()
    } else if (ch === '\r') {
      if (src[i + 1] !== '\n') {
        row.push(field)
        field = ''
        pushRow()
      }
    } else {
      field += ch
    }
  }
  row.push(field)
  pushRow()
  return rows
}

/** 读 CSV 为对象数组（按表头映射列名） */
async function readCsvObjects(relPath) {
  const rows = parseCsv(await readText(fromRepo(relPath)))
  if (rows.length === 0) throw new Error(`CSV 为空：${relPath}`)
  const header = rows[0]
  const objects = []
  for (let i = 1; i < rows.length; i += 1) {
    const cells = rows[i]
    const object = {}
    for (let c = 0; c < header.length; c += 1) object[header[c]] = cells[c] ?? ''
    objects.push(object)
  }
  return objects
}

function featureCollection(features) {
  return { type: 'FeatureCollection', features }
}

function pointFeature(lon, lat, properties) {
  return {
    type: 'Feature',
    properties,
    geometry: { type: 'Point', coordinates: [round6(lon), round6(lat)] },
  }
}

/** 递归遍历任意 GeoJSON geometry 坐标，返回保留 6 位小数的 [minLon,minLat,maxLon,maxLat] */
function bboxOfFeatures(features) {
  let minLon = Infinity
  let minLat = Infinity
  let maxLon = -Infinity
  let maxLat = -Infinity

  const walk = (coords) => {
    if (!Array.isArray(coords) || coords.length === 0) return
    if (typeof coords[0] === 'number') {
      const lon = coords[0]
      const lat = coords[1]
      if (Number.isFinite(lon) && Number.isFinite(lat)) {
        if (lon < minLon) minLon = lon
        if (lat < minLat) minLat = lat
        if (lon > maxLon) maxLon = lon
        if (lat > maxLat) maxLat = lat
      }
      return
    }
    for (const child of coords) walk(child)
  }

  for (const feature of features) {
    if (feature && feature.geometry) walk(feature.geometry.coordinates)
  }
  if (!Number.isFinite(minLon)) return null
  return [round6(minLon), round6(minLat), round6(maxLon), round6(maxLat)]
}

function unionBbox(boxes) {
  const valid = boxes.filter(Boolean)
  if (valid.length === 0) return null
  return [
    round6(Math.min(...valid.map((box) => box[0]))),
    round6(Math.min(...valid.map((box) => box[1]))),
    round6(Math.max(...valid.map((box) => box[2]))),
    round6(Math.max(...valid.map((box) => box[3]))),
  ]
}

function formatBytes(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

// ---------------------------------------------------------------------------
// 主流程
// ---------------------------------------------------------------------------
async function main() {
  const startedAt = Date.now()
  await mkdir(outDir, { recursive: true })

  // 0. 源文件体检：缺任何一个都直接失败（宁可报错，不要产出残缺 manifest）
  const sourcePaths = [...new Set([...Object.values(SRC)])]
  const sourceStats = new Map()
  const missing = []
  for (const relPath of sourcePaths) {
    const info = await statOrNull(fromRepo(relPath))
    if (info) sourceStats.set(relPath, info)
    else missing.push(relPath)
  }
  if (missing.length > 0) {
    throw new Error(`缺少源文件：\n  ${missing.join('\n  ')}`)
  }

  // 1. water_green.geojson → water.geojson / green.geojson
  {
    const source = sourceStats.get(SRC.waterGreen)
    const waterPath = join(outDir, 'water.geojson')
    const greenPath = join(outDir, 'green.geojson')
    const waterStale = await needsRewrite(waterPath, source)
    const greenStale = await needsRewrite(greenPath, source)
    if (waterStale || greenStale) {
      const geojson = await readJson(fromRepo(SRC.waterGreen))
      if (geojson.type !== 'FeatureCollection' || !Array.isArray(geojson.features)) {
        throw new Error(`源文件不是 FeatureCollection：${SRC.waterGreen}`)
      }
      const groups = { water: [], green: [] }
      let ignored = 0
      for (const feature of geojson.features) {
        const kind = feature && feature.properties ? feature.properties.kind : undefined
        if (kind === 'water' || kind === 'green') groups[kind].push(feature)
        else ignored += 1
      }
      if (ignored > 0) console.warn(`[sync-geo] water_green 有 ${ignored} 个要素 kind 非 water/green，已忽略`)
      if (waterStale) {
        await atomicWrite(waterPath, JSON.stringify(featureCollection(groups.water)))
        console.log(`[sync-geo] 写入 water.geojson（${groups.water.length} 面）`)
      }
      if (greenStale) {
        await atomicWrite(greenPath, JSON.stringify(featureCollection(groups.green)))
        console.log(`[sync-geo] 写入 green.geojson（${groups.green.length} 面）`)
      }
    } else {
      console.log('[sync-geo] 跳过 water/green（已是最新）')
    }
  }

  // 2. 整文件复制（保留原始坐标精度）
  for (const { file, source: relSource } of COPY_FILES) {
    const dest = join(outDir, file)
    if (await needsRewrite(dest, sourceStats.get(relSource))) {
      await atomicCopy(fromRepo(relSource), dest)
      console.log(`[sync-geo] 复制 ${file} ← ${relSource}`)
    } else {
      console.log(`[sync-geo] 跳过 ${file}（已是最新）`)
    }
  }

  const scriptStat = await stat(fileURLToPath(import.meta.url))
  // 清理旧版 30 MB 全量路网文件
  await rm(join(outDir, 'segments_all.geojson'), { force: true })

  // 2b. 热点网格：离线分析产物（JSON），只给热点页当后端不可用时的静态兜底
  const hotspotPath = join(outDir, 'hotspot', 'grid_1000m.json')
  if (await needsRewrite(hotspotPath, sourceStats.get(SRC.hotspotGrid))) {
    await mkdir(dirname(hotspotPath), { recursive: true })
    await atomicCopy(fromRepo(SRC.hotspotGrid), hotspotPath)
    console.log(`[sync-geo] 复制 hotspot/grid_1000m.json ← ${SRC.hotspotGrid}`)
  } else {
    console.log('[sync-geo] 跳过 hotspot/grid_1000m.json（已是最新）')
  }
  const hotspot = await readJson(hotspotPath)
  const hotspotCells = Array.isArray(hotspot.cells) ? hotspot.cells : []
  if (hotspotCells.length === 0) throw new Error('热点网格 cells 为空')

  // 3. CSV → 点图层
  for (const config of POINT_LAYERS) {
    const dest = join(outDir, config.file)
    const srcStat = sourceStats.get(config.source)
    const newestMtime = Math.max(srcStat.mtimeMs, scriptStat.mtimeMs)
    if (!(await needsRewrite(dest, { mtimeMs: newestMtime }))) {
      console.log(`[sync-geo] 跳过 ${config.file}（已是最新）`)
      continue
    }
    const rawRows = await readCsvObjects(config.source)
    const rows = config.filter ? rawRows.filter(config.filter) : rawRows
    const features = rows.map((row, index) => {
      const lon = toFiniteNumber(row[config.lonColumn], `${config.source}[${index}].${config.lonColumn}`)
      const lat = toFiniteNumber(row[config.latColumn], `${config.source}[${index}].${config.latColumn}`)
      return pointFeature(lon, lat, config.properties(row))
    })
    await atomicWrite(dest, JSON.stringify(featureCollection(features)))
    console.log(`[sync-geo] 写入 ${config.file}（${features.length} 点）`)
  }

  // 4. 统计渲染层（count / bbox / bytes 全部从最终产物读，保证 manifest 与文件一致）
  const metrics = new Map()
  for (const layer of LAYERS) {
    const filePath = join(outDir, layer.file)
    const info = await stat(filePath)
    const geojson = await readJson(filePath)
    if (geojson.type !== 'FeatureCollection' || !Array.isArray(geojson.features)) {
      throw new Error(`产物不是 FeatureCollection：${layer.file}`)
    }
    metrics.set(layer.id, {
      count: geojson.features.length,
      bbox: bboxOfFeatures(geojson.features),
      bytes: info.size,
    })
  }
  const metricOf = (id) => metrics.get(id)

  // 5. 盘点空间数据文件
  const loops = await readJson(fromRepo(SRC.loops))
  const loopsFeatures = Array.isArray(loops.features) ? loops.features : []
  const loopsBbox = bboxOfFeatures(loopsFeatures)

  const inventory = [
    {
      path: SRC.segmentsArterial,
      format: 'GeoJSON LineString',
      count: metricOf('roads_arterial').count,
      bbox: metricOf('roads_arterial').bbox,
      rendered_as: ['roads_arterial'],
    },
    {
      path: SRC.waterGreen,
      format: 'GeoJSON Polygon',
      count: metricOf('water').count + metricOf('green').count,
      bbox: unionBbox([metricOf('water').bbox, metricOf('green').bbox]),
      rendered_as: ['water', 'green'],
    },
    {
      path: SRC.routesBus,
      format: 'GeoJSON LineString',
      count: metricOf('bus_routes').count,
      bbox: metricOf('bus_routes').bbox,
      rendered_as: ['bus_routes'],
    },
    {
      path: SRC.routesMetro,
      format: 'GeoJSON LineString',
      count: metricOf('metro_routes').count,
      bbox: metricOf('metro_routes').bbox,
      rendered_as: ['metro_routes'],
    },
    {
      path: SRC.boundary,
      format: 'GeoJSON MultiPolygon',
      count: metricOf('boundary').count,
      bbox: metricOf('boundary').bbox,
      rendered_as: ['boundary'],
    },
    {
      path: SRC.loops,
      format: 'GeoJSON LineString',
      count: loopsFeatures.length,
      bbox: loopsBbox,
      rendered_as: [],
    },
    {
      path: 'data/processed/running/v1/segments.gpkg#segments',
      format: 'GeoPackage',
      count: 91203,
      bbox: GPKG_BBOX_CITY.slice(),
      rendered_as: [],
    },
    {
      path: 'data/processed/v1/osm_walk_roads.gpkg#walk_roads',
      format: 'GeoPackage',
      count: 91203,
      bbox: GPKG_BBOX_CITY.slice(),
      rendered_as: [],
    },
    {
      path: 'data/processed/v1/poi.gpkg#poi_points+poi_areas',
      format: 'GeoPackage',
      count: 14154 + 7768,
      bbox: GPKG_BBOX_POI.slice(),
      rendered_as: [],
    },
    {
      path: SRC.facilities,
      format: 'CSV',
      count: metricOf('facilities').count,
      bbox: metricOf('facilities').bbox,
      rendered_as: ['facilities'],
    },
    {
      path: SRC.toilets,
      format: 'CSV',
      count: metricOf('toilets').count,
      bbox: metricOf('toilets').bbox,
      rendered_as: ['toilets'],
    },
    {
      path: SRC.stopsBus,
      format: 'CSV',
      count: metricOf('bus_stops').count,
      bbox: metricOf('bus_stops').bbox,
      rendered_as: ['bus_stops'],
    },
    {
      path: SRC.stopsMetro,
      format: 'CSV',
      count: metricOf('metro_stops').count,
      bbox: metricOf('metro_stops').bbox,
      rendered_as: ['metro_stops'],
    },
    {
      path: SRC.airStations,
      format: 'CSV',
      count: metricOf('air_stations').count,
      bbox: metricOf('air_stations').bbox,
      rendered_as: ['air_stations'],
    },
    {
      path: SRC.hotspots,
      format: 'CSV',
      count: metricOf('hotspots').count,
      bbox: metricOf('hotspots').bbox,
      rendered_as: ['hotspots'],
    },
    {
      path: SRC.hotspotGrid,
      format: 'JSON 1 km 网格',
      count: hotspotCells.length,
      bbox: Array.isArray(hotspot.view) ? hotspot.view : null,
      rendered_as: ['hotspot'],
    },
  ]

  // 6. manifest.json
  const layers = LAYERS.map((layer) => {
    const layerMetric = metricOf(layer.id)
    return {
      id: layer.id,
      label: layer.label,
      group: layer.group,
      file: layer.file,
      geometry: layer.geometry,
      count: layerMetric.count,
      bbox: layerMetric.bbox,
      bytes: layerMetric.bytes,
      source: layer.source,
      style: layer.style,
      default: layer.default,
      extent: layer.extent,
      variant: layer.variant,
      variantLevel: layer.variantLevel,
    }
  })

  const manifest = {
    generated_at: new Date().toISOString(),
    crs: 'WGS84',
    view: VIEW,
    summary: {
      spatial_files: inventory.length,
      layers: layers.length,
      features: layers.reduce((sum, layer) => sum + layer.count, 0),
    },
    hotspot: {
      file: 'hotspot/grid_1000m.json',
      cells: hotspotCells.length,
      view: hotspot.view ?? null,
      generated_at: hotspot.generated_at ?? null,
      note: hotspot.note ?? '',
    },
    layers,
    inventory,
  }

  await atomicWrite(join(outDir, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`)

  // 7. 汇总日志
  const layerBytes = layers.reduce((sum, layer) => sum + layer.bytes, 0)
  const seconds = ((Date.now() - startedAt) / 1000).toFixed(1)
  for (const layer of layers) {
    console.log(`[sync-geo]   ${layer.id.padEnd(12)} ${String(layer.count).padStart(6)}  ${formatBytes(layer.bytes)}`)
  }
  console.log(
    `[sync-geo] 完成：${layers.length} 层 / ${inventory.length} 个空间文件，` +
      `features=${manifest.summary.features}，渲染层合计 ${formatBytes(layerBytes)}，耗时 ${seconds}s → ${outDir}`,
  )
}

try {
  await main()
} catch (err) {
  console.error(`[sync-geo] 失败：${err && err.message ? err.message : err}`)
  process.exitCode = 1
}
