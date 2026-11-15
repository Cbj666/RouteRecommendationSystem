/**
 * 把前端要用的静态底图从 data/output/running/v1/web/ 复制到 public/geo/。
 *
 * 为什么需要这一步：Vite 的 root 是 frontend/app，`fetch('../../data/...')`
 * 在 dev 下会被 fs 限制、在 build 后也不存在。复制进 public/ 后：
 *   - dev:  /geo/segments_city.geojson
 *   - build: dist/geo/segments_city.geojson
 *
 * 触发：npm run predev / prebuild（见 package.json），也可手动 npm run sync:geo。
 * public/geo/ 已在 .gitignore 里，数据本身仍以 data/ 为唯一来源。
 */
import { copyFile, mkdir, stat } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const appRoot = resolve(here, '..')
const repoRoot = resolve(appRoot, '..', '..')
const srcDir = resolve(repoRoot, 'data', 'output', 'running', 'v1', 'web')
const outDir = resolve(appRoot, 'public', 'geo')

// segments_all.geojson 29 MB，默认不复制；需要全城视野时再手动加进来。
const FILES = ['segments_city.geojson', 'segments_arterial.geojson', 'water_green.geojson']

await mkdir(outDir, { recursive: true })

let copied = 0
let skipped = 0

for (const name of FILES) {
  const src = resolve(srcDir, name)
  const dest = resolve(outDir, name)

  if (!existsSync(src)) {
    console.warn(`[sync-geo] 源文件不存在，跳过：${src}`)
    skipped += 1
    continue
  }

  if (existsSync(dest)) {
    const [s, d] = await Promise.all([stat(src), stat(dest)])
    if (d.size === s.size && d.mtimeMs >= s.mtimeMs) {
      skipped += 1
      continue
    }
  }

  await copyFile(src, dest)
  copied += 1
  console.log(`[sync-geo] 已复制 ${name}`)
}

console.log(`[sync-geo] 完成：复制 ${copied} 个，跳过 ${skipped} 个 → ${outDir}`)
