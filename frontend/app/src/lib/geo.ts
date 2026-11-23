/** 读取 public/geo/ 下的静态底图 */
export async function loadGeoJSON<P, G>(url: string): Promise<import('../types').GeoCollection<P, G>> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${url} → HTTP ${res.status}`)
  return (await res.json()) as import('../types').GeoCollection<P, G>
}
