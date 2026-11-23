/**
 * 接口类型 —— 与 `docs/接口契约.md` 一一对应。
 * 字段名就是后端返回的字段名（下划线），不要在这里改成驼峰。
 */

/** POST /api/loops 请求体 */
export interface LoopRequest {
  mode?: 'loop' | 'oneway'
  lng: number
  lat: number
  /** 1000–20000（接口上限 20 km，算法侧支持 1–42 km） */
  target_m: number
  /** 各 0–1；不传则用后端默认 {green:1.0, safe:1.0, flat:0.6} */
  prefs?: { green: number; safe: number; flat: number }
  /** 2–16，默认 8 */
  max_candidates?: number
}

/** /api/loops 返回的每条环线属性（真实字段，共 9 个） */
export interface LoopProps {
  mode?: 'loop' | 'oneway'
  pref_score?: number
  mean_segment_score?: number
  rank: number
  length_m: number
  minutes: number
  /** 偏好匹配分（只含 safety / green / slope），与 /api/segments 的 score 不同口径 */
  score: number
  tree_share: number
  slope_mean_pct: number
  facility_m: number
  /** 起点吸附到路网的距离（米）；> 100 建议在 UI 上提示 */
  origin_snap_m: number
  /** JSON 字符串！要 JSON.parse 才能拿到子分 */
  sub: string
}

export interface LoopSubScores {
  s_safety: number
  s_green: number
  s_slope: number
}

export interface LoopFeature {
  type: 'Feature'
  properties: LoopProps
  geometry: { type: 'LineString'; coordinates: [number, number][] }
}

export interface LoopCollection {
  type: 'FeatureCollection'
  features: LoopFeature[]
  message?: string
  notice?: string
}

/** /api/segments 每要素的属性（12 个，不含 s_air） */
export interface SegmentProps {
  osm_id: number
  fclass: string
  name: string
  length_m: number
  score: number
  grade: string
  s_safety: number
  s_green: number
  s_slope: number
  s_cross: number
  s_fac: number
}

export interface SegmentFeature {
  type: 'Feature'
  properties: SegmentProps
  geometry: { type: 'LineString'; coordinates: [number, number][] }
}

export interface SegmentCollection {
  type: 'FeatureCollection'
  features: SegmentFeature[]
  /** true 表示 bbox 内超过 limit，被截断 */
  truncated: boolean
}

/** /api/facilities 每点的属性 */
export interface FacilityProps {
  name: string
  /** 高德三级分号码，多标签用 | 连接 */
  type: string
}

/** GET /api/meta 的返回 */
export interface MetaResponse {
  dataset: string
  weights: { safety: number; green: number; slope: number; cross: number; fac: number; air: number }
  score_stats: Record<string, number>
  speed_mps: number
  notes: string[]
}

/** GET /health 的返回 */
export interface HealthResponse {
  status: string
  nodes: number
  edges: number
  graph_loaded_at: number
}

/* ------------------------------------------------------------------
 * 静态底图（data/output/running/v1/web/*.geojson）
 * 这些文件由 scripts/sync-geo.mjs 复制到 public/geo/，由前端直接 fetch。
 * ------------------------------------------------------------------ */

export interface LineGeometry {
  type: 'LineString'
  coordinates: [number, number][]
}

export interface MultiLineGeometry {
  type: 'MultiLineString'
  coordinates: [number, number][][]
}

export interface PolygonGeometry {
  type: 'Polygon'
  coordinates: [number, number][][]
}

export interface MultiPolygonGeometry {
  type: 'MultiPolygon'
  coordinates: [number, number][][][]
}

export type LineLikeGeometry = LineGeometry | MultiLineGeometry
export type PolygonLikeGeometry = PolygonGeometry | MultiPolygonGeometry

export interface WaterGreenProps {
  /** 'water' | 'green'，个别要素还可能带 type */
  kind?: string
  type?: string
}

export interface GeoFeature<P, G> {
  type: 'Feature'
  properties: P
  geometry: G
}

export interface GeoCollection<P, G> {
  type: 'FeatureCollection'
  features: GeoFeature<P, G>[]
}

export type SegmentGeoCollection = GeoCollection<SegmentProps, LineLikeGeometry>
export type WaterGreenCollection = GeoCollection<WaterGreenProps, PolygonLikeGeometry>

/** POST /api/loops 返回空结果时附带的说明（HTTP 200） */
export interface LoopEmptyResponse {
  type: 'FeatureCollection'
  features: []
  message?: string
}

/* ------------------------------------------------------------------
 * 动态视图 + 数据图层清单（public/geo/manifest.json，由 scripts/sync-geo.mjs 生成）
 * ------------------------------------------------------------------ */

/** 视图范围：线性投影到 1600×1000 的经纬度 bbox */
export interface ViewBox {
  lon0: number
  lat0: number
  lon1: number
  lat1: number
}

/** 地图范围：片区（central）/ 全城（city） */
export type Extent = 'central' | 'city'

export type LayerGeometry = 'polygon' | 'line' | 'point'

export type LayerStyle =
  | 'water'
  | 'green'
  | 'boundary'
  | 'score'
  | 'metroRoute'
  | 'metroStop'
  | 'busRoute'
  | 'busStop'
  | 'facility'
  | 'hotspot'
  | 'air'

/** manifest.layers 里的单个图层定义（字段由数据管线固定） */
export interface MapLayerDef {
  id: string
  label: string
  /** 面板分组：底图 / 路网 / 交通 / 设施 / 分析 */
  group: string
  file: string
  geometry: LayerGeometry
  count: number
  /** [minLon, minLat, maxLon, maxLat] */
  bbox: [number, number, number, number]
  bytes: number
  source: string
  style: LayerStyle
  default: boolean
  extent: 'both' | Extent
  variant: 'roads' | null
  variantLevel: Extent | 'all' | null
}

/** manifest.inventory 里的一个数据源（含不参与渲染的 gpkg / csv） */
export interface InventoryItem {
  path: string
  format: string
  count: number
  bbox?: [number, number, number, number] | null
  rendered_as: string[]
}

export interface ManifestView {
  central: ViewBox
  city: ViewBox
}

export interface ManifestSummary {
  spatial_files: number
  layers: number
  features: number
}

export interface GeoManifest {
  generated_at: string
  crs: string
  view: ManifestView
  summary: ManifestSummary
  layers: MapLayerDef[]
  inventory: InventoryItem[]
}

/* ---------------- 图层 GeoJSON 数据集 ---------------- */

export interface PointGeometry {
  type: 'Point'
  coordinates: [number, number]
}

export interface MultiPointGeometry {
  type: 'MultiPoint'
  coordinates: [number, number][]
}

export type AnyGeometry =
  | LineLikeGeometry
  | PolygonLikeGeometry
  | PointGeometry
  | MultiPointGeometry

/**
 * 图层要素属性：只声明渲染/图例真正用到的字段，
 * 其余属性（name/type/adname/…）保留为未知字段。
 */
export interface LayerProps {
  score?: number
  kind?: string
  type?: string
  name?: string
  aqi?: number
  [key: string]: unknown
}

export type LayerCollection = GeoCollection<LayerProps, AnyGeometry>
