/**
 * 等距投影：与 frontend/reference/index.html 完全一致。
 *
 * 视图范围是 PPT 原型图的视野。这个 bbox 乘 cos(30.5°) 后经纬比正好
 * 1600/1000 = 1.6，所以简单线性投影不会变形；换成别的 bbox 要重新调。
 */
export const VIEW = {
  lon0: 114.305,
  lat0: 30.508,
  lon1: 114.405,
  lat1: 30.562,
} as const

export const MAP_W = 1600
export const MAP_H = 1000

export function projectX(lon: number): number {
  return ((lon - VIEW.lon0) / (VIEW.lon1 - VIEW.lon0)) * MAP_W
}

export function projectY(lat: number): number {
  return ((VIEW.lat1 - lat) / (VIEW.lat1 - VIEW.lat0)) * MAP_H
}

export function project(coord: [number, number]): [number, number] {
  return [projectX(coord[0]), projectY(coord[1])]
}

/** 画布像素 → WGS84；地图点击选起点用 */
export function unproject(x: number, y: number): [number, number] {
  const lon = VIEW.lon0 + (x / MAP_W) * (VIEW.lon1 - VIEW.lon0)
  const lat = VIEW.lat1 - (y / MAP_H) * (VIEW.lat1 - VIEW.lat0)
  return [lon, lat]
}
