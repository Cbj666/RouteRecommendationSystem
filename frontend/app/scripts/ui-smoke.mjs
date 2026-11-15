/**
 * UI 冒烟测试：用 Edge headless + CDP 打开页面，模拟真实点击/输入，断言关键 DOM。
 * 仅开发期使用；不依赖任何 npm 包（Node 24 自带 fetch / WebSocket）。
 *
 *   node scripts/ui-smoke.mjs                 # 默认 http://127.0.0.1:5173/
 *   $env:UI_URL='http://127.0.0.1:5173/'; node scripts/ui-smoke.mjs
 *
 * 产出：data/output/ui/m2/ 下 search-open.png / custom-origin.png（截图）
 */
import { spawn } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const OUT = resolve(HERE, '../../../data/output/ui', process.env.UI_OUT || 'm2')
const REAL = process.env.UI_REAL === '1'
const URL_APP = process.env.UI_URL || 'http://127.0.0.1:5173/'
const PORT = Number(process.env.CDP_PORT || 9333)
const EDGE =
  process.env.EDGE ||
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function waitForJson(url, tries = 60) {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(url)
      if (r.ok) return await r.json()
    } catch {
      /* 浏览器还没起来 */
    }
    await sleep(250)
  }
  throw new Error(`CDP 没有就绪：${url}`)
}

const proc = spawn(
  EDGE,
  [
    '--headless=new',
    '--disable-gpu',
    '--hide-scrollbars',
    '--force-device-scale-factor=1',
    '--window-size=1600,1000',
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${resolve(process.env.TEMP || '/tmp', `dsh-ui-smoke-${PORT}`)}`,
    URL_APP,
  ],
  { stdio: 'ignore' },
)

let ws
const pageErrors = []
const consoleErrors = []
const failedRequests = []
try {
  const list = await waitForJson(`http://127.0.0.1:${PORT}/json/list`)
  const page = list.find((t) => t.type === 'page' && t.url.startsWith('http'))
  if (!page) throw new Error('没有找到页面 target')

  ws = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise((res, rej) => {
    ws.onopen = res
    ws.onerror = () => rej(new Error('WebSocket 连接失败'))
  })

  let seq = 0
  const pending = new Map()
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.id && pending.has(msg.id)) {
      const { res, rej } = pending.get(msg.id)
      pending.delete(msg.id)
      msg.error ? rej(new Error(msg.error.message)) : res(msg.result)
      return
    }
    if (msg.method === 'Runtime.exceptionThrown') {
      const d = msg.params.exceptionDetails
      pageErrors.push(d.exception?.description || d.text)
    } else if (msg.method === 'Log.entryAdded' && msg.params.entry.level === 'error') {
      consoleErrors.push(msg.params.entry.text)
    } else if (msg.method === 'Network.loadingFailed') {
      failedRequests.push(msg.params.errorText)
    }
  }
  const send = (method, params = {}) =>
    new Promise((res, rej) => {
      const id = ++seq
      pending.set(id, { res, rej })
      ws.send(JSON.stringify({ id, method, params }))
    })

  const evalJs = async (expression) => {
    const r = await send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
    })
    if (r.exceptionDetails) {
      throw new Error(r.exceptionDetails.exception?.description || 'evaluate 失败')
    }
    return r.result.value
  }

  await send('Runtime.enable')
  await send('Page.enable')
  await send('Log.enable')
  await send('Network.enable')
  // headless 窗口含边框，实际视口会小几像素；固定成 1600×1000 再截图
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1600,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  })
  await send('Page.reload', { ignoreCache: false })
  await send('Page.bringToFront')

  const waitUntil = async (expr, timeout = 30000) => {
    const t0 = Date.now()
    while (Date.now() - t0 < timeout) {
      if (await evalJs(expr)) return true
      await sleep(150)
    }
    return false
  }
  const ready = await waitUntil(
    `(document.querySelector('.score b')?.textContent || '').trim().length > 0`,
  )
  if (!ready) console.log('WARN  首屏分数 30 s 内没有出现')

  const checks = []
  const check = (name, got, want) => {
    const ok =
      typeof want === 'function' ? want(got) : JSON.stringify(got) === JSON.stringify(want)
    checks.push({ name, ok, got, want: typeof want === 'function' ? '(fn)' : want })
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}  got=${JSON.stringify(got)}`)
  }

  async function shot(name) {
    const r = await send('Page.captureScreenshot', { format: 'png' })
    await mkdir(OUT, { recursive: true })
    await writeFile(resolve(OUT, name), Buffer.from(r.data, 'base64'))
  }

  const score = () => evalJs(`document.querySelector('.score b')?.textContent ?? ''`)
  const heading = () => evalJs(`document.querySelector('.rt')?.textContent?.trim() ?? ''`)
  const originName = () => evalJs(`document.querySelector('.origin-text b')?.textContent ?? ''`)

  if (REAL) {
    const api = await (
      await fetch('http://127.0.0.1:8000/api/loops', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          lng: 114.3547,
          lat: 30.5342,
          target_m: 5000,
          prefs: { green: 1, safe: 1, flat: 0 },
        }),
      })
    ).json()
    const p0 = api.features[0].properties
    check('真实分数与接口一致', await score(), String(p0.score))
    check(
      '真实候选数一致',
      await evalJs(`document.querySelector('.cidx')?.textContent ?? ''`),
      `1/${api.features.length}`,
    )
    const apiMs = await evalJs(
      `(()=>{const e=performance.getEntriesByType('resource').filter(x=>x.name.includes('/api/loops'));return e.length?Math.round(e[e.length-1].duration):-1})()`,
    )
    check('环线接口耗时 < 8 s', apiMs, (v) => v > 0 && v < 8000)
    check('首屏无错误提示', await evalJs(`!!document.querySelector('.box.err')`), false)
    await shot('real-1600.png')
  } else {
    check('首屏分数 78.5', await score(), '78.5')
    check('首屏候选 1/3', await evalJs(`document.querySelector('.cidx')?.textContent ?? ''`), '1/3')
  }

  // 1) 目标距离 10 km → 10km mock
  await evalJs(`[...document.querySelectorAll('.seg')].find(b => b.textContent.trim() === '10 km').click()`)
  const pill = await evalJs(`document.querySelector('.pill')?.textContent ?? ''`)
  check('加载提示出现', pill, (v) => v.includes('正在生成'))
  await waitUntil(`!document.querySelector('.pill')`, 20000)
  await sleep(120)
  check('10 km 后距离 8.51 km', await evalJs(`document.querySelector('.cell b')?.textContent ?? ''`), '8.51 km')
  check(
    '10 km 后选中态',
    await evalJs(`document.querySelectorAll('.segs')[1].querySelector('.seg.on')?.textContent.trim() ?? ''`),
    '10 km',
  )

  // 2) 下一条候选
  await evalJs(`document.querySelectorAll('.cand .cbtn')[1].click()`)
  await sleep(200)
  check('下一候选 → 第 2 条', await heading(), (v) => v.includes('第 2 条'))

  // 3) 键盘 ← 回到第 1 条
  await evalJs(
    `document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }))`,
  )
  await sleep(150)
  check('← 键回第 1 条', await heading(), (v) => v.includes('第 1 条'))

  // 4) 搜索「东湖」并选中（用 CDP 真实鼠标点击聚焦，headless 下 element.focus() 可能不触发 focus）
  const box = await evalJs(
    `(()=>{const r=document.querySelector('input.search').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`,
  )
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: box.x, y: box.y, button: 'left', clickCount: 1 })
  await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: box.x, y: box.y, button: 'left', clickCount: 1 })
  await sleep(120)
  await evalJs(`(() => { const i = document.querySelector('input.search'); const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(i, '东湖'); i.dispatchEvent(new Event('input', { bubbles: true })); })()`)
  await sleep(200)
  console.log(
    'DBG  搜索状态',
    await evalJs(
      `JSON.stringify({v:document.querySelector('input.search')?.value,open:!!document.querySelector('.options'),n:document.querySelectorAll('.options .option').length})`,
    ),
  )
  const options = await evalJs(`[...document.querySelectorAll('.options .option b')].map(e => e.textContent)`)
  check('搜索过滤出东湖', options, (v) => Array.isArray(v) && v.some((s) => s.includes('东湖')))
  await shot('search-open.png')
  await evalJs(
    `document.querySelector('.options .option').dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))`,
  )
  await waitUntil(`!document.querySelector('.pill')`, 20000)
  await sleep(150)
  check('选东湖后起点', await originName(), (v) => v.includes('东湖'))

  // 5) 地图点击选起点
  await evalJs(
    `document.querySelector('.map-host').dispatchEvent(new MouseEvent('click', { clientX: 800, clientY: 500, bubbles: true }))`,
  )
  await sleep(150)
  check('地图选点', await originName(), '地图选点')
  const marker = await evalJs(`document.querySelectorAll('.map-host svg g')[2]?.children.length ?? 0`)
  check('起点标记已画', marker, 1)
  await shot('custom-origin.png')

  // 6) 回到预设起点（搜索「武汉」）
  await evalJs(`(() => { const i = document.querySelector('input.search'); i.focus(); const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(i, '武汉'); i.dispatchEvent(new Event('input', { bubbles: true })); })()`)
  await sleep(150)
  await evalJs(
    `document.querySelector('.options .option').dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))`,
  )
  await waitUntil(`!document.querySelector('.pill')`, 20000)
  await sleep(150)
  check('回预设起点', await originName(), (v) => v.includes('武汉大学'))

  // 7) 四态自测：?mock=empty / error / slow（mock 专用钩子）
  if (REAL) {
    console.log('SKIP  四态自测（真实后端模式没有 mock 钩子）')
  } else {
    await send('Page.navigate', { url: `${URL_APP}?mock=empty` })
    await sleep(1800)
    check(
      '无结果态',
      await evalJs(`document.querySelector('.notice')?.textContent ?? ''`),
      (v) => v.includes('没有可用的环线'),
    )
    await shot('empty-state.png')

    await send('Page.navigate', { url: `${URL_APP}?mock=error` })
    await sleep(1800)
    check(
      '失败态（区分 500）',
      await evalJs(`document.querySelector('.box.err')?.textContent ?? ''`),
      (v) => v.includes('500'),
    )
    await shot('error-state.png')

    await send('Page.navigate', { url: `${URL_APP}?mock=slow` })
    await sleep(700)
    check(
      '加载态',
      await evalJs(`document.querySelector('.pill')?.textContent ?? ''`),
      (v) => v.includes('正在生成'),
    )
    await shot('loading-state.png')
  }

  // 8) 移动端 390×844：单列、地图 16:10、无横向滚动
  await send('Emulation.setDeviceMetricsOverride', {
    width: 390,
    height: 844,
    deviceScaleFactor: 1,
    mobile: true,
  })
  await send('Page.navigate', { url: URL_APP })
  await waitUntil(
    `(document.querySelector('.score b')?.textContent || '').trim().length > 0`,
    25000,
  )
  await sleep(300)
  check('移动端单列', await evalJs(`!!document.querySelector('.stage.mobile')`), true)
  check(
    '移动端地图 16:10',
    await evalJs(
      `(()=>{const r=document.querySelector('.map-host')?.getBoundingClientRect(); return r ? Math.round((r.width/r.height)*100)/100 : 0})()`,
    ),
    (v) => Math.abs(v - 1.6) < 0.02,
  )
  check(
    '移动端无横向滚动',
    await evalJs(`document.documentElement.scrollWidth <= 390`),
    true,
  )
  await shot('mobile-390.png')

  // 移动端整页（超出 844 的部分也截下来，便于检查下方面板）
  const metrics = await send('Page.getLayoutMetrics')
  const pageH = await evalJs(`document.documentElement.scrollHeight`)
  const layout = await evalJs(
    `JSON.stringify([...document.querySelectorAll('.stage > *')].map((el) => {const s=getComputedStyle(el);const r=el.getBoundingClientRect();return el.className+':'+s.position+':'+Math.round(r.top)+':'+Math.round(r.height)}))`,
  )
  console.log(
    `INFO  mobile layout: cssContentSize=${metrics.cssContentSize.height} scrollHeight=${pageH}`,
  )
  console.log(`INFO  layout: ${layout}`)
  const full = await send('Page.captureScreenshot', {
    format: 'png',
    captureBeyondViewport: true,
    clip: {
      x: 0,
      y: 0,
      width: 390,
      height: Math.min(2600, Math.ceil(metrics.cssContentSize.height)),
      scale: 1,
    },
  })
  await writeFile(resolve(OUT, 'mobile-390-full.png'), Buffer.from(full.data, 'base64'))

  check('无 JS 运行时异常', pageErrors, (v) => v.length === 0)
  check('无 console 错误', consoleErrors, (v) => v.length === 0)
  check(
    '无网络失败请求',
    failedRequests.filter((t) => !/ERR_ABORTED/.test(t)),
    (v) => v.length === 0,
  )
  const badFinal = checks.filter((c) => !c.ok)
  console.log(`\n${checks.length - badFinal.length}/${checks.length} passed`)
  if (badFinal.length) process.exitCode = 1
} finally {
  try {
    ws?.close()
  } catch {
    /* ignore */
  }
  proc.kill()
  spawn('taskkill', ['/PID', String(proc.pid), '/T', '/F'], { stdio: 'ignore' })
}
