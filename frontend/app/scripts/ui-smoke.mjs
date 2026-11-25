/**
 * 前端交付冒烟，使用 Edge headless 与 CDP。
 * 覆盖 F1（统一单图 + 视口路段加载 + 路线视野联动）、
 * F2（单行线两步点选 A/B + 绕行系数 + 选点报错）、
 * F3（两页签：环线推荐 / 热点地图）、
 * F4（运动场馆/公厕分符号、独立开关、整城聚合、无障碍筛选与图例）、
 * F5（地点搜索：环线模式设为起点、单行线模式依次落 A/B）、
 * F6（全城热点网格：离线数据经 /api/hotspot 提供，榜单与格子联动）。
 *
 * UI_REAL=1 连接真实后端（热点网格 1,853 格、地点搜索走高德）；默认 mock 用内置
 * 500 格网格与 4 条地点。UI_URL 指向开发服务器；UI_SCREENSHOTS=1 可选截图。
 * 记录写入 data/output/ui/<UI_OUT>，默认 frontend-delivery。
 */
import { spawn } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const OUT = resolve(HERE, '../../../data/output/ui', process.env.UI_OUT || 'frontend-delivery')
const REAL = process.env.UI_REAL === '1'
const SCREENSHOTS = process.env.UI_SCREENSHOTS === '1'
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
    'about:blank',
  ],
  { stdio: 'ignore' },
)

let ws
const pageErrors = []
const consoleErrors = []
const failedRequests = []
try {
  const list = await waitForJson(`http://127.0.0.1:${PORT}/json/list`)
  const page = list.find((t) => t.type === 'page' && t.url === 'about:blank')
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
      const timeout = setTimeout(() => {
        pending.delete(id)
        rej(new Error(`CDP 命令超时：${method}`))
      }, 20000)
      pending.set(id, {
        res: (result) => {
          clearTimeout(timeout)
          res(result)
        },
        rej: (error) => {
          clearTimeout(timeout)
          rej(error)
        },
      })
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
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1600,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  })
  await send('Page.navigate', { url: URL_APP })
  await send('Page.bringToFront')

  const waitUntil = async (expr, timeout = 30000) => {
    const t0 = Date.now()
    while (Date.now() - t0 < timeout) {
      if (await evalJs(expr)) return true
      await sleep(150)
    }
    return false
  }

  const checks = []
  async function check(name, expression) {
    const ok = await waitUntil('Boolean(' + expression + ')', 30000)
    checks.push({ name, ok })
    console.log((ok ? 'PASS  ' : 'FAIL  ') + name)
    if (!ok) {
      throw new Error(
        name +
          '\n' +
          (await evalJs(
            "JSON.stringify({text:document.body.innerText.slice(0,800),width:document.documentElement.scrollWidth})",
          )),
      )
    }
  }

  const click = (selector) => evalJs(`document.querySelector(${JSON.stringify(selector)}).click()`)
  const clickLngLat = (lng, lat) =>
    evalJs(`(async()=>{
      const manifest = await (await fetch('/geo/manifest.json')).json();
      const { project, fitViewBBox } = await import('/src/lib/projection.ts');
      const c = manifest.view.city;
      const [x, y] = project(fitViewBBox([c.lon0, c.lat0, c.lon1, c.lat1], 24), ${lng}, ${lat});
      const host = document.querySelector('.map-host');
      const svg = host.querySelector('svg');
      const vb = svg.viewBox.baseVal;
      const rect = host.getBoundingClientRect();
      const clientX = rect.x + ((x - vb.x) / vb.width) * rect.width;
      const clientY = rect.y + ((y - vb.y) / vb.height) * rect.height;
      host.dispatchEvent(new MouseEvent('click', { clientX, clientY, bubbles: true }));
    })()`)

  const tab = async (index) => {
    await evalJs(`document.querySelectorAll('.tabs .tab')[${index}].click()`)
    await check(
      '页签 ' + index + ' 高亮',
      `document.querySelectorAll('.tabs .tab')[${index}].classList.contains('on')`,
    )
  }

  const capture = async (name) => {
    if (!SCREENSHOTS) return
    await mkdir(OUT, { recursive: true })
    const result = await send('Page.captureScreenshot', { format: 'png' })
    await writeFile(resolve(OUT, name + '.png'), Buffer.from(result.data, 'base64'))
  }

  // 搜索框交互：输入关键词、选中下拉第一项、切换路线模式
  const typeSearch = async (text) => {
    await evalJs(
      `(()=>{const input=document.querySelector('.search');input.focus();input.value=${JSON.stringify(text)};input.dispatchEvent(new Event('input',{bubbles:true}))})()`,
    )
  }

  const pickFirstOption = async () => {
    await evalJs(
      "document.querySelector('#origin-list .option[role=option]').dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true}))",
    )
  }

  const setModeSeg = async (index) => {
    await evalJs(`document.querySelectorAll('.mode-segs .seg')[${index}].click()`)
  }

  // F3: 顶部两页签（适宜性地图页已从前端移除，只保留环线推荐与热点地图）
  await check(
    'F3 两页签（环线推荐 / 热点地图）',
    "document.querySelectorAll('.tabs .tab').length === 2 && document.body.innerText.includes('环线推荐') && document.body.innerText.includes('热点地图') && !document.body.innerText.includes('适宜性地图')",
  )

  // F1: 默认进入环线页并自动生成路线；单图、图层面板就绪，无片区/全城开关
  await check(
    'F1 环线自动生成并缩放至路线范围',
    "document.querySelector('.score b') && document.querySelector('g[data-layer=route] path') && !document.querySelector('.pill') && document.querySelector('g[data-layer=roads] path') && document.querySelector('.layers') && !document.querySelector('.extent') && !document.querySelector('[data-layer=roads_all]') && document.querySelector('.map-host svg').viewBox.baseVal.width < 400",
  )

  // 放大到 5 km 视野：展开运动场馆圆角方块 & 公厕圆点，且加载视口细粒度路网
  await check(
    'F4 放大后场馆与公厕分开绘制',
    "document.querySelector('g[data-layer=facilities] path') && document.querySelector('g[data-layer=toilets] path') && !document.querySelector('g[data-layer=poi_clusters]')",
  )
  await check(
    'F1 放大后加载视口细粒度路网',
    "document.querySelector('g[data-layer=roads]')?.getAttribute('data-file') === 'viewport'",
  )
  await capture('loop-zoomed')

  await click('.cand .cbtn:last-child')
  await check('切换候选环线', "document.querySelector('.cidx').textContent.startsWith('2/')")
  await evalJs("document.body.dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowLeft',bubbles:true}))")
  await check('键盘候选切换', "document.querySelector('.cidx').textContent.startsWith('1/')")

  // 复位到全城视野：验证整城设施聚合与图层开关
  await evalJs(
    "[...document.querySelectorAll('.map-controls button')].find((b) => b.textContent.includes('复位')).click()",
  )
  await check(
    'F4 整城设施聚合与独立开关默认开启',
    "document.querySelector('g[data-layer=poi_clusters] path') && document.querySelector('[data-layer=facilities] .layer-check')?.getAttribute('aria-checked') === 'true' && document.querySelector('[data-layer=toilets] .layer-check')?.getAttribute('aria-checked') === 'true'",
  )
  await click('[data-layer="water"] .layer-check')
  await check('关闭水体', "!document.querySelector('g[data-layer=water]')")
  await click('[data-layer="water"] .layer-check')
  await check('恢复水体', "document.querySelector('g[data-layer=water] path')")
  await capture('city-overview')

  // F2: 单行线两步点选 A/B
  await evalJs("document.querySelectorAll('.mode-segs .seg')[1].click()")
  await check(
    'F2 进入单行线：清空路线、隐藏距离、显示 A/B 选点卡',
    "!document.querySelector('g[data-layer=route] path') && !document.body.innerText.includes('目标距离') && document.querySelector('[data-point=A]') && document.querySelector('[data-point=B]') && document.querySelector('.oneway-hint')?.textContent.includes('先点地图选起点')",
  )

  // 点两下地图选 A（武大）和 B（街道口）
  await clickLngLat(114.3547, 30.5342)
  await check(
    'F2 点第一下设置起点 A',
    "document.querySelector('[data-point=A]').textContent.includes('114.35') && document.querySelector('[data-point=B]').classList.contains('active')",
  )
  await clickLngLat(114.349, 30.5256)
  await check(
    'F2 点第二下设置终点 B 并自动生成 A→B 路线',
    "document.querySelector('.rt')?.textContent.includes('单行线') && document.querySelector('g[data-layer=route] path') && document.body.innerText.includes('直线距离') && document.body.innerText.includes('绕行系数') && !document.querySelector('.cand') && !document.querySelector('.pill')",
  )
  await capture('oneway-ab')

  if (REAL) {
    // 测试落水 422 错误提示显示在 B 卡下方且保留 A/B
    await clickLngLat(114.385, 30.553)
    await check(
      'F2 选点落水在 B 卡下方展示错误并保留已选点',
      "document.querySelector('.oneway-err')?.textContent.includes('水体') && document.querySelector('[data-point=A]').textContent.includes('114.35')",
    )
    // 重选 B 到陆地恢复
    await clickLngLat(114.349, 30.5256)
    await check(
      'F2 重选 B 后恢复路线',
      "document.querySelector('g[data-layer=route] path') && !document.querySelector('.oneway-err')",
    )
  }
  // 地点搜索：REAL 走 /api/places/search（需后端与高德 Key）；mock 只有 4 条内置地点
  // 主流程是「搜索地点当环线起点」；前面的单行线用例把模式切走了，先切回环线
  await setModeSeg(0)
  await check(
    '切回环线模式',
    "document.querySelectorAll('.mode-segs .seg')[0].classList.contains('on') && Boolean(document.querySelector('.origin-text b'))",
  )

  const loopKeyword = REAL ? '武汉大学' : '东湖'
  const loopPicked = REAL ? '武汉大学' : '东湖绿道'
  await typeSearch(loopKeyword)
  await check(
    REAL ? '地点搜索真实结果' : '地点搜索 mock 兜底',
    REAL
      ? "document.querySelectorAll('#origin-list .option[role=option]').length >= 3 && document.querySelector('#origin-list').textContent.includes('水利水电学院')"
      : "document.querySelectorAll('#origin-list .option[role=option]').length >= 1 && document.querySelector('#origin-list').textContent.includes('东湖')",
  )
  await pickFirstOption()
  await check(
    '选中地点设为环线起点',
    `document.querySelector('.search').value === ${JSON.stringify(loopPicked)} && document.querySelector('.origin-text b').textContent.startsWith(${JSON.stringify(loopKeyword)}) && Boolean(document.querySelector('g[data-layer=route] path'))`,
  )
  if (REAL) {
    await check(
      '搜索结果编号标记上地图',
      "document.querySelectorAll('g[data-layer=places] g[data-place-index]').length >= 3 && document.querySelector('g[data-layer=places] text').textContent === '1'",
    )
    await capture('place-search')
  }

  // 单行线模式下同样能搜索选点：先落 A，再落 B 并生成 A→B 路线（A/B 用不同地点）
  const onewayKeyword = REAL ? '东湖绿道' : '武汉大学'
  await setModeSeg(1)
  await check(
    '切到单行线模式',
    "document.querySelectorAll('.mode-segs .seg')[1].classList.contains('on')",
  )
  await typeSearch(loopKeyword)
  await check(
    '单行线搜索出候选',
    "document.querySelectorAll('#origin-list .option[role=option]').length >= 1",
  )
  await pickFirstOption()
  await check(
    '搜索选中起点 A',
    `document.querySelector('.point-card[data-point=A] b').textContent.startsWith(${JSON.stringify(loopKeyword)})`,
  )
  await typeSearch(onewayKeyword)
  await check(
    '单行线搜索出终点候选',
    "document.querySelectorAll('#origin-list .option[role=option]').length >= 1",
  )
  await pickFirstOption()
  await check(
    '搜索选中终点 B 并生成路线',
    `document.querySelector('.point-card[data-point=B] b').textContent.startsWith(${JSON.stringify(onewayKeyword)}) && Boolean(document.querySelector('g[data-layer=route] path'))`,
  )

  // F6: 热点地图页签 —— 全城 2 km 网格（/api/hotspot 离线产物；mock 为 500 格示例）
  await tab(1)
  await check(
    'F6 热点页签与全城网格',
    `document.querySelector('.hotspot-rank h3')?.textContent.includes('武汉跑步热点地图') && Number(document.querySelector('.hotspot-overlay').getAttribute('data-cells')) >= ${REAL ? 1200 : 400} && document.querySelector('.hotspot-detail') && document.querySelector('.hotspot-rank header p')?.textContent.includes('2 km')`,
  )
  await check(
    'F6 榜单与六维详情联动',
    "document.querySelectorAll('.hotspot-rank .rank-list li').length >= 10 && Boolean(document.querySelector('.hotspot-detail .num'))",
  )
  await capture('hotspot-desktop')
  await click('.hotspot-rank .rank-list li:nth-child(2)')
  await check(
    'F6 点击榜单切换选中格',
    "document.querySelector('.hotspot-rank .rank-list li:nth-child(2)').classList.contains('on')",
  )

  // 窄屏响应式检查
  await send('Emulation.setDeviceMetricsOverride', {
    width: 390,
    height: 844,
    deviceScaleFactor: 1,
    mobile: false,
  })
  await check(
    '390 px 无横向溢出且两页签',
    "document.documentElement.scrollWidth <= 390 && document.querySelectorAll('.tabs .tab').length === 2",
  )
  await check(
    '390 px 热点页可读',
    "document.querySelector('.hotspot-rank') && document.querySelector('.hotspot-detail') && document.documentElement.scrollWidth <= 390",
  )
  await capture('hotspot-mobile')
  await tab(0)
  await check(
    '390 px 推荐页无横向溢出',
    "document.querySelector('.left') && document.documentElement.scrollWidth <= 390",
  )
  await send('Emulation.setDeviceMetricsOverride', {
    width: 320,
    height: 568,
    deviceScaleFactor: 1,
    mobile: false,
  })
  await check('320 px 无横向溢出', 'document.documentElement.scrollWidth <= 320')

  if (!REAL) {
    for (const scenario of ['empty', 'error', 'slow']) {
      await send('Page.navigate', { url: URL_APP + '?mock=' + scenario })
      await check('场景导航 ' + scenario, "document.querySelectorAll('.tabs .tab').length === 2")
      await check(
        '路线状态 ' + scenario,
        scenario === 'empty'
          ? "document.querySelector('.box.notice')"
          : scenario === 'error'
            ? "document.querySelector('.box.err')"
            : "document.querySelector('.pill')",
      )
    }
  }

  if (pageErrors.length) throw new Error(pageErrors.join('\n'))
  await mkdir(OUT, { recursive: true })
  await writeFile(
    resolve(OUT, 'checks.json'),
    JSON.stringify({ real: REAL, checks, pageErrors, consoleErrors, failedRequests }, null, 2),
  )
  console.log(checks.length + '/' + checks.length + ' passed')
} finally {
  ws?.close()
  proc.kill()
}
