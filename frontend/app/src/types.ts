/**
 * 接口类型 —— 与 `docs/接口契约.md` 一一对应。
 * 字段名就是后端返回的字段名（下划线），不要在这里改成驼峰。
 */

/** POST /api/routes 请求体 */
export interface LoopRequest {
  mode?: 'loop' | 'oneway'
  lng: number
  lat: number
  /** 1000–42000；仅 loop 模式传，oneway 指定终点时不传 */
  target_m?: number
  /** 仅 oneway 模式传 */
  end_lng?: number
  end_lat?: number
  /** 各 0–1；不传则用后端默认 {green:1.0, safe:1.0, flat:0.6} */
  prefs?: { green: number; safe: number; flat: number }
  /** 2–16，默认 8 */
  max_candidates?: number
}

/** /api/routes 返回的每条路线属性 */
export interface LoopProps {
  mode?: 'loop' | 'oneway'
  pref_score?: number
  mean_segment_score?: number
  rank: number
  target_m?: number
  target_ok?: boolean
  length_m: number
  length_error_m?: number
  length_error_pct?: number
  minutes: number
  /** 偏好匹配分（只含 safety / green / slope），与 /api/segments 的 score 不同口径 */
  score: number
  tree_share: number
  slope_mean_pct: number
  facility_m: number
  /** 起点吸附到路网的距离（米）；> 100 建议在 UI 上提示 */
  origin_snap_m: number
  destination_snap_m?: number
  start_lng?: number
  start_lat?: number
  end_lng?: number
  end_lat?: number
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

export interface SnappedEndpoint {
  lng: number
  lat: number
  snap_m: number
  snapped_lng: number
  snapped_lat: number
}

export interface LoopCollection {
  type: 'FeatureCollection'
  features: LoopFeature[]
  mode?: 'loop' | 'oneway'
  origin?: SnappedEndpoint
  destination?: SnappedEndpoint
  message?: string
  notice?: string
}

/** /api/segments 每要素的属性 */
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
  s_air?: number
  no2_ugm3?: number
  pm25_ugm3?: number
}

export interface SegmentFeature {
  type: 'Feature'
  properties: SegmentProps
  geometry: { type: 'LineString'; coordinates: [number, number][] }
}

export interface SegmentCollection {
  type: 'FeatureCollection'
  features: SegmentFeature[]
  total?: number
  /** true 表示 bbox 内超过 limit，被截断 */
  truncated: boolean
  bbox?: [number, number, number, number]
}

/** /api/facilities 每点的属性 */
export interface FacilityProps {
  name: string
  /** 高德三级分类，多标签用 | 连接 */
  type: string
  address?: string
  adname?: string
}

/** GET /api/places/search 返回的单个地点；lng/lat 已由后端转成 WGS84 */
export interface Place {
  /** 高德 POI id；高德缺 id 时后端用「名称@坐标」兜底，保证稳定 */
  id: string
  name: string
  address: string
  province: string
  city: string
  district: string
  /** 高德三级分类，例如「科教文化服务;学校;高等院校」 */
  type: string
  typecode: string
  /** WGS84，可直接交给地图与路线接口 */
  lng: number
  lat: number
  /** 高德原始 GCJ-02 坐标，仅用于排错 */
  amap_lng?: number
  amap_lat?: number
}

/** GET /api/places/search 的返回 */
export interface PlaceSearchResponse {
  provider: string
  query: string
  count: number
  places: Place[]
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
 * 静态底图（public/geo/*.geojson）
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

/* ------------------------------------------------------------------
 * 动态视图 + 数据图层清单（public/geo/manifest.json）
 * ------------------------------------------------------------------ */

/** 视图范围：线性投影到 1600×1000 的经纬度 bbox */
export interface ViewBox {
  lon0: number
  lat0: number
  lon1: number
  lat1: number
}

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
  | 'toilet'
  | 'hotspot'
  | 'air'

/** manifest.layers 里的单个图层定义 */
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
  extent: string
  variant: 'roads' | null
  variantLevel: string | null
}

/** manifest.inventory 里的一个数据源 */
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

export interface LayerProps {
  score?: number
  grade?: string
  kind?: string
  type?: string
  name?: string
  address?: string
  adname?: string
  accessible?: boolean
  aqi?: number
  [key: string]: unknown
}

export type LayerCollection = GeoCollection<LayerProps, AnyGeometry>

/** 设施点悬浮/点击信息 */
export interface PoiInfo {
  kind: 'facility' | 'toilet'
  name: string
  type: string
  address: string
  adname: string
  accessible?: boolean
  lng: number
  lat: number
  /** 画布内像素位置（供悬浮/弹窗定位） */
  screenX: number
  screenY: number
}
